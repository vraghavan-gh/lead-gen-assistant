"""
Lead Gen Assistant - Flask Web Server
Serves the lead capture web form and webhook endpoint.
Submissions go through the Web Form Agent before the main pipeline.

Usage:
    python web/app.py

Endpoints:
    GET  /              — Lead capture web form
    POST /webhook       — Receives form, runs Web Form Agent + pipeline
    GET  /status/<id>   — Check lead status
    GET  /dashboard     — Live pipeline dashboard
    GET  /api/results   — JSON results feed
    GET  /health        — Health check
"""

import sys
import json
import threading
from pathlib import Path
from datetime import datetime, timezone

from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

from pipeline import LeadGenPipeline
from agents.web_form_agent import WebFormAgent
from utils.llm_client import get_provider_info

app = Flask(__name__)

# In-memory store for recent results
recent_results = []
_pipeline      = None
_web_form_agent= None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = LeadGenPipeline()
    return _pipeline


def get_web_form_agent():
    global _web_form_agent
    if _web_form_agent is None:
        _web_form_agent = WebFormAgent(get_pipeline().db)
    return _web_form_agent


# ============================================================
# Routes
# ============================================================

@app.route("/")
def index():
    provider_info = get_provider_info()
    return render_template("index.html", provider=provider_info)


@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Receive form submission.
    Runs Web Form Agent (with human-in-the-loop) then full pipeline.
    Runs in background thread — returns immediately to browser.
    """
    try:
        data = request.get_json() if request.is_json else request.form.to_dict()

        if not data.get("email"):
            return jsonify({"error": "Email is required"}), 400

        submitted_at = datetime.now(timezone.utc).isoformat()

        def run(form_data, sub_at):
            try:
                # Stage 0: Web Form Agent — human review
                agent      = get_web_form_agent()
                lead_input = agent.process(form_data, submitted_at=sub_at)

                if lead_input is None:
                    # Rejected by operator or Web Form Agent
                    recent_results.insert(0, {
                        "lead_id":      None,
                        "name":         f"{form_data.get('first_name','')} {form_data.get('last_name','')}".strip(),
                        "company":      form_data.get("company"),
                        "email":        form_data.get("email"),
                        "final_status": "rejected",
                        "mql_score":    None,
                        "sql_score":    None,
                        "assigned_rep": None,
                        "submitted_at": sub_at,
                    })
                    return

                # Stage 1-3: Full pipeline
                p      = get_pipeline()
                result = p.process_lead(lead_input)

                recent_results.insert(0, {
                    "lead_id":      result.get("lead_id"),
                    "name":         f"{lead_input.first_name} {lead_input.last_name}",
                    "company":      lead_input.company,
                    "email":        lead_input.email,
                    "final_status": result.get("final_status"),
                    "mql_score":    result.get("mql", {}).get("mql_score") if result.get("mql") else None,
                    "sql_score":    result.get("sql", {}).get("sql_score") if result.get("sql") else None,
                    "assigned_rep": result.get("sql", {}).get("assigned_rep_name") if result.get("sql") else None,
                    "submitted_at": sub_at,
                })

                if len(recent_results) > 50:
                    recent_results.pop()

            except Exception as e:
                print(f"Pipeline error: {e}")

        thread = threading.Thread(target=run, args=(data, submitted_at), daemon=True)
        thread.start()

        return jsonify({
            "success": True,
            "message": "Thank you! Your request has been received and is being processed.",
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/status/<lead_id>")
def lead_status(lead_id):
    try:
        p        = get_pipeline()
        lead     = p.db.get_raw_lead(lead_id)
        if not lead:
            return jsonify({"error": "Lead not found"}), 404
        timeline = p.db.get_lead_timeline(lead_id)
        return jsonify({
            "lead_id":  lead_id,
            "status":   lead.get("status"),
            "email":    lead.get("email"),
            "company":  lead.get("company"),
            "timeline": [
                {
                    "event":     e.get("event_type"),
                    "agent":     e.get("agent_name"),
                    "from":      e.get("from_status"),
                    "to":        e.get("to_status"),
                    "score":     e.get("score_at_event"),
                    "timestamp": str(e.get("event_timestamp")),
                }
                for e in (timeline or [])
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", results=recent_results)


@app.route("/api/results")
def api_results():
    return jsonify(recent_results)


@app.route("/health")
def health():
    return jsonify({
        "status":          "ok",
        "provider":        get_provider_info(),
        "leads_processed": len(recent_results),
    })


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    print("\n🎯 Lead Gen Assistant — Web Server")
    info = get_provider_info()
    print(f"   Provider  : {info['provider']}")
    print(f"   Model     : {info['model']}")
    print(f"   Form      : http://127.0.0.1:5000")
    print(f"   Dashboard : http://127.0.0.1:5000/dashboard")
    print(f"   Webhook   : POST http://127.0.0.1:5000/webhook\n")
    app.run(host="0.0.0.0", debug=True, port=8080)
