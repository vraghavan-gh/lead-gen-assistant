"""
Lead Gen Assistant - MQL Agent
Converts an accepted raw lead into a Marketing Qualified Lead (MQL).
Uses scoring config + Claude to enrich, score, and classify.
"""

import json
import time
import yaml
from pathlib import Path
from typing import Optional

from agents.base_agent import BaseAgent
from utils.models import MQLResult, BuyingStage
from utils.databricks_client import DatabricksClient
from rich.console import Console

console = Console()

# Load scoring config
_config_path = Path(__file__).parent.parent / "config" / "scoring_config.yaml"
with open(_config_path) as f:
    SCORING_CONFIG = yaml.safe_load(f)

MQL_THRESHOLD = SCORING_CONFIG["mql"]["threshold"]


MQL_SYSTEM_PROMPT = f"""
You are the MQL Agent for an enterprise Lead Generation pipeline.

Your job is to evaluate an accepted lead and determine if it qualifies as a 
Marketing Qualified Lead (MQL) using the scoring rules provided.

MQL Qualification Threshold: {MQL_THRESHOLD} points (out of 100)

Scoring Dimensions:
1. Job Title / Seniority (max 20pts) — Director+ = 20, Manager = 10, Individual = 5
2. Company Size (max 15pts) — Enterprise 1000+ = 15, Mid-Market 200-999 = 10, SMB 50-199 = 5
3. Industry Fit (max 10pts) — Tech/FinServ/Healthcare = 10, Others = 3-7
4. Form Type Intent (max 20pts) — Demo Request = 20, Contact Us = 15, Content Download = 8-10
5. Email Domain (max 10pts) — Business email = 10, Personal email = 0
6. Message Intent (max 15pts) — Pricing/budget/urgency keywords = 3pts each, max 15
7. Data Completeness (max 10pts) — 2pts per completed required field

Also:
- Identify the buyer persona: Technical_Buyer | Economic_Buyer | End_User | Champion
- Identify buying stage: awareness | consideration | decision  
- Extract pain points from the message
- Suggest a nurture track: enterprise_track | smb_track | technical_track | general_track

You MUST use the mql_qualification tool to return your structured result.
"""

MQL_TOOL = {
    "name": "mql_qualification",
    "description": "Return the MQL qualification result with scores and enrichment",
    "input_schema": {
        "type": "object",
        "properties": {
            "qualified": {
                "type": "boolean",
                "description": f"True if total score >= {MQL_THRESHOLD}"
            },
            "mql_score": {
                "type": "integer",
                "description": "Total MQL score 0-100"
            },
            "score_breakdown": {
                "type": "object",
                "description": "Score per dimension: job_title, company_size, industry, form_type, email_domain, message_intent, completeness"
            },
            "enriched_company": {"type": "string"},
            "enriched_industry": {"type": "string"},
            "enriched_employees": {"type": "integer"},
            "enriched_revenue": {"type": "string"},
            "technologies_used": {
                "type": "array",
                "items": {"type": "string"}
            },
            "persona": {
                "type": "string",
                "enum": ["Technical_Buyer", "Economic_Buyer", "End_User", "Champion", "Unknown"]
            },
            "buying_stage": {
                "type": "string",
                "enum": ["awareness", "consideration", "decision"]
            },
            "product_interest": {
                "type": "array",
                "items": {"type": "string"}
            },
            "pain_points": {
                "type": "array",
                "items": {"type": "string"}
            },
            "nurture_track": {
                "type": "string",
                "enum": ["enterprise_track", "smb_track", "technical_track", "general_track"]
            },
            "reasoning": {
                "type": "string",
                "description": "2-3 sentence explanation of the qualification decision"
            },
            "confidence_score": {
                "type": "number",
                "description": "Confidence in this classification 0.0-1.0"
            }
        },
        "required": [
            "qualified", "mql_score", "score_breakdown",
            "persona", "buying_stage", "nurture_track",
            "reasoning", "confidence_score"
        ]
    }
}


class MQLAgent(BaseAgent):
    """
    MQL Agent — Converts accepted raw leads into Marketing Qualified Leads.

    Responsibilities:
    - Score lead against MQL criteria (configurable thresholds)
    - Enrich firmographic data
    - Classify buyer persona and buying stage
    - Assign to nurture track if not qualified
    - Write MQL record to Databricks
    - Hand off to SQL Agent if qualified
    """

    def process(self, lead_id: str) -> MQLResult:
        """
        Process an accepted lead through MQL qualification.

        Args:
            lead_id: The raw_leads.lead_id to qualify

        Returns:
            MQLResult with qualification decision and enrichment
        """
        start_time = time.time()

        # 1. Fetch raw lead from Databricks
        lead = self.db.get_raw_lead(lead_id)
        if not lead:
            raise ValueError(f"Lead {lead_id} not found in raw_leads table")

        self.log(f"Qualifying lead [yellow]{lead_id}[/yellow] — {lead.get('email')}")

        self.db.log_event(
            lead_id    = lead_id,
            event_type = "mql_scoring_started",
            agent_name = self.name,
            from_status= "accepted",
            to_status  = "processing",
        )

        # 2. Call Claude for MQL scoring
        user_message = f"""
Score and qualify this accepted lead for MQL status:

Lead Data:
{json.dumps(lead, indent=2, default=str)}

Apply the MQL scoring rubric. The MQL threshold is {MQL_THRESHOLD}/100.
Use the mql_qualification tool to return your structured result.
"""
        response = self.call_claude(
            system_prompt = MQL_SYSTEM_PROMPT,
            user_message  = user_message,
            tools         = [MQL_TOOL],
            max_tokens    = 3000,
        )

        duration = int((time.time() - start_time) * 1000)

        # 3. Parse tool response
        if not response["tool_use"]:
            self.log("[red]MQL Agent did not return tool_use — flagging for review[/red]")
            return MQLResult(
                lead_id         = lead_id,
                qualified       = False,
                mql_score       = 0,
                agent_reasoning = "Agent processing error — needs human review",
                confidence_score= 0.0,
            )

        data = response["tool_use"]["input"]

        mql_result = MQLResult(
            lead_id          = lead_id,
            qualified        = data["qualified"],
            mql_score        = data["mql_score"],
            score_breakdown  = data.get("score_breakdown", {}),
            enriched_company = data.get("enriched_company"),
            enriched_industry= data.get("enriched_industry"),
            enriched_employees=data.get("enriched_employees"),
            enriched_revenue = data.get("enriched_revenue"),
            technologies_used= data.get("technologies_used", []),
            persona          = data.get("persona"),
            buying_stage     = data.get("buying_stage"),
            product_interest = data.get("product_interest", []),
            pain_points      = data.get("pain_points", []),
            nurture_track    = data.get("nurture_track"),
            agent_reasoning  = data["reasoning"],
            confidence_score = data["confidence_score"],
            agent_version    = self.VERSION,
        )

        # 4. Write to Databricks
        if mql_result.qualified:
            mql_id = self.db.insert_mql_lead({
                **mql_result.model_dump(),
                "agent_reasoning": mql_result.agent_reasoning,
            })
            mql_result.mql_id = mql_id

            # Update raw lead status
            self.db.update_lead_status(lead_id, "mql")
            self.db.log_event(
                lead_id         = lead_id,
                event_type      = "mql_qualified",
                agent_name      = self.name,
                from_status     = "accepted",
                to_status       = "mql",
                score           = mql_result.mql_score,
                details         = data,
                duration_seconds= int(duration / 1000),
            )
            self.log(
                f"[green]✓ MQL QUALIFIED[/green] — Score: {mql_result.mql_score}/100 "
                f"| Persona: {mql_result.persona} | Stage: {mql_result.buying_stage} "
                f"| MQL ID: {mql_id}"
            )
        else:
            self.db.update_lead_status(lead_id, "accepted")  # stays accepted, enters nurture
            self.db.log_event(
                lead_id         = lead_id,
                event_type      = "mql_rejected",
                agent_name      = self.name,
                from_status     = "accepted",
                to_status       = "accepted",
                score           = mql_result.mql_score,
                details         = data,
                duration_seconds= int(duration / 1000),
            )
            self.log(
                f"[yellow]✗ MQL NOT QUALIFIED[/yellow] — Score: {mql_result.mql_score}/{MQL_THRESHOLD} "
                f"| Track: {mql_result.nurture_track} — {mql_result.agent_reasoning}"
            )

        return mql_result
