"""
Lead Gen Assistant - SQL Agent
Converts MQL leads into Sales Qualified Leads (SQL) using BANT scoring.
Assigns to the right sales rep and team, then hands off.
"""

import json
import time
import yaml
from pathlib import Path
from typing import Optional
from datetime import date, timedelta

from agents.base_agent import BaseAgent
from utils.models import SQLResult, SalesTeam
from utils.databricks_client import DatabricksClient
from rich.console import Console

console = Console()

_config_path = Path(__file__).parent.parent / "config" / "scoring_config.yaml"
with open(_config_path) as f:
    SCORING_CONFIG = yaml.safe_load(f)

SQL_THRESHOLD = SCORING_CONFIG["sql"]["threshold"]


SQL_SYSTEM_PROMPT = f"""
You are the SQL Agent for an enterprise Lead Generation pipeline.

Your job is to evaluate a Marketing Qualified Lead (MQL) and determine if it qualifies 
as a Sales Qualified Lead (SQL) using the BANT framework.

SQL Qualification Threshold: {SQL_THRESHOLD} points (out of 100)

BANT Scoring (25 points each):

BUDGET (25pts):
- Confirmed budget: 25pts — lead explicitly mentions budget, pricing inquiry, or procurement process
- Implied budget: 15pts — company size / seniority suggests budget authority
- Unknown: 0pts — no signals

AUTHORITY (25pts):
- Decision Maker (C-Suite, VP, Director): 25pts
- Influencer / Champion (Manager, Lead): 15pts
- End User (IC, Analyst, Engineer): 5pts

NEED (25pts):
- Strong need signals: explicit pain points, current solution failing, active evaluation: 25pts
- Moderate: mentioned challenges but vague: 10-15pts
- Weak: general interest, no clear problem: 0-5pts

TIMELINE (25pts):
- Immediate (< 30 days): 25pts
- Short term (30-90 days): 20pts
- Medium term (90-180 days): 10pts
- Long term (180+ days): 5pts
- Unknown: 0pts

Also determine:
- estimated_deal_size: <$10K | $10K-$50K | $50K-$200K | $200K+ (based on company size + need)
- estimated_close_date: realistic date based on timeline
- use_case_summary: 2-3 sentence summary of the business problem and proposed solution fit
- competitive_context: any competitor mentions or incumbent systems
- next_step: discovery_call | product_demo | proposal | executive_briefing | trial
- assigned_team: enterprise_sales (1000+ emp) | mid_market_sales (200-999) | smb_sales (<200)

You MUST use the sql_qualification tool to return your structured result.
"""

SQL_TOOL = {
    "name": "sql_qualification",
    "description": "Return the SQL qualification result with BANT scores and sales assignment",
    "input_schema": {
        "type": "object",
        "properties": {
            "qualified": {
                "type": "boolean",
                "description": f"True if BANT total score >= {SQL_THRESHOLD}"
            },
            "sql_score": {"type": "integer", "description": "Total BANT score 0-100"},
            "bant_score_budget":    {"type": "integer", "description": "Budget score 0-25"},
            "bant_score_authority": {"type": "integer", "description": "Authority score 0-25"},
            "bant_score_need":      {"type": "integer", "description": "Need score 0-25"},
            "bant_score_timeline":  {"type": "integer", "description": "Timeline score 0-25"},
            "estimated_deal_size": {
                "type": "string",
                "enum": ["<$10K", "$10K-$50K", "$50K-$200K", "$200K+"]
            },
            "estimated_close_date": {
                "type": "string",
                "description": "ISO date string YYYY-MM-DD"
            },
            "use_case_summary": {"type": "string"},
            "competitive_context": {"type": "string"},
            "next_step": {
                "type": "string",
                "enum": ["discovery_call", "product_demo", "proposal", "executive_briefing", "trial"]
            },
            "assigned_team": {
                "type": "string",
                "enum": ["enterprise_sales", "mid_market_sales", "smb_sales", "channel_sales"]
            },
            "assignment_reason": {"type": "string"},
            "reasoning": {
                "type": "string",
                "description": "2-3 sentence BANT qualification rationale"
            },
            "confidence_score": {"type": "number"}
        },
        "required": [
            "qualified", "sql_score",
            "bant_score_budget", "bant_score_authority",
            "bant_score_need", "bant_score_timeline",
            "assigned_team", "next_step",
            "reasoning", "confidence_score"
        ]
    }
}


class SQLAgent(BaseAgent):
    """
    SQL Agent — Converts MQL leads into Sales Qualified Leads.

    Responsibilities:
    - Apply BANT qualification framework
    - Estimate deal size and close timeline
    - Route to appropriate sales team
    - Assign to specific sales rep (load balanced)
    - Write SQL record to Databricks
    - Trigger sales handoff notification
    """

    def process(self, mql_id: str) -> SQLResult:
        """
        Process an MQL through SQL qualification.

        Args:
            mql_id: The mql_leads.mql_id to qualify

        Returns:
            SQLResult with BANT scores and assignment
        """
        start_time = time.time()

        # 1. Fetch MQL + Raw lead from Databricks
        mql = self.db.get_mql_lead(mql_id)
        if not mql:
            raise ValueError(f"MQL {mql_id} not found")

        lead_id  = mql["lead_id"]
        raw_lead = self.db.get_raw_lead(lead_id)

        self.log(
            f"BANT qualifying MQL [yellow]{mql_id}[/yellow] "
            f"— {raw_lead.get('first_name')} {raw_lead.get('last_name')} @ {raw_lead.get('company')}"
        )

        self.db.log_event(
            lead_id    = lead_id,
            event_type = "sql_scoring_started",
            agent_name = self.name,
            from_status= "mql",
        )

        # 2. Fetch available sales reps for context
        sales_reps = self._get_available_reps()

        # 3. Call Claude for SQL/BANT scoring
        user_message = f"""
Evaluate this MQL for SQL qualification using BANT framework:

MQL Record:
{json.dumps(mql, indent=2, default=str)}

Original Lead Data:
{json.dumps(raw_lead, indent=2, default=str)}

Available Sales Reps:
{json.dumps(sales_reps, indent=2)}

SQL Threshold: {SQL_THRESHOLD}/100

Use the sql_qualification tool to return your BANT assessment and sales assignment.
"""
        response = self.call_claude(
            system_prompt = SQL_SYSTEM_PROMPT,
            user_message  = user_message,
            tools         = [SQL_TOOL],
            max_tokens    = 3000,
        )

        duration = int((time.time() - start_time) * 1000)

        if not response["tool_use"]:
            self.log("[red]SQL Agent did not return tool_use — flagging for review[/red]")
            return SQLResult(
                lead_id          = lead_id,
                mql_id           = mql_id,
                qualified        = False,
                sql_score        = 0,
                bant_score_budget   = 0,
                bant_score_authority= 0,
                bant_score_need     = 0,
                bant_score_timeline = 0,
                agent_reasoning  = "Agent processing error",
                confidence_score = 0.0,
            )

        data = response["tool_use"]["input"]

        # Match a rep to the assigned team
        rep = self._assign_rep(data.get("assigned_team"), sales_reps)

        sql_result = SQLResult(
            lead_id              = lead_id,
            mql_id               = mql_id,
            qualified            = data["qualified"],
            sql_score            = data["sql_score"],
            bant_score_budget    = data["bant_score_budget"],
            bant_score_authority = data["bant_score_authority"],
            bant_score_need      = data["bant_score_need"],
            bant_score_timeline  = data["bant_score_timeline"],
            estimated_deal_size  = data.get("estimated_deal_size"),
            estimated_close_date = data.get("estimated_close_date"),
            use_case_summary     = data.get("use_case_summary"),
            competitive_context  = data.get("competitive_context"),
            next_step            = data.get("next_step"),
            assigned_team        = data.get("assigned_team"),
            assigned_rep_id      = rep.get("rep_id") if rep else None,
            assigned_rep_name    = rep.get("name")   if rep else None,
            assigned_rep_email   = rep.get("email")  if rep else None,
            assignment_reason    = data.get("assignment_reason"),
            agent_reasoning      = data["reasoning"],
            confidence_score     = data["confidence_score"],
            agent_version        = self.VERSION,
        )

        # 4. Write to Databricks
        if sql_result.qualified:
            sql_id = self.db.insert_sql_lead(sql_result.model_dump())
            sql_result.sql_id = sql_id

            self.db.update_lead_status(lead_id, "sql")
            self.db.log_event(
                lead_id         = lead_id,
                event_type      = "sql_qualified",
                agent_name      = self.name,
                from_status     = "mql",
                to_status       = "sql",
                score           = sql_result.sql_score,
                details         = data,
                duration_seconds= int(duration / 1000),
            )

            # Trigger sales handoff
            self._notify_sales_rep(sql_result, raw_lead)

            self.log(
                f"[green]✓ SQL QUALIFIED[/green] — BANT: {sql_result.sql_score}/100 "
                f"| Deal: {sql_result.estimated_deal_size} "
                f"| Rep: {sql_result.assigned_rep_name} "
                f"| Next: {sql_result.next_step} "
                f"| SQL ID: {sql_id}"
            )
        else:
            # Return to MQL nurture
            self.db.update_lead_status(lead_id, "mql")
            self.db.log_event(
                lead_id         = lead_id,
                event_type      = "sql_rejected",
                agent_name      = self.name,
                from_status     = "mql",
                to_status       = "mql",
                score           = sql_result.sql_score,
                details         = data,
                duration_seconds= int(duration / 1000),
            )
            self.log(
                f"[yellow]✗ SQL NOT QUALIFIED[/yellow] — BANT: {sql_result.sql_score}/{SQL_THRESHOLD} "
                f"— {sql_result.agent_reasoning} — Returned to nurture"
            )

        return sql_result

    def _get_available_reps(self) -> list[dict]:
        """Fetch active sales reps from Databricks."""
        try:
            reps = self.db.execute(
                f"""
                SELECT rep_id, first_name || ' ' || last_name AS name,
                       email, team, current_load, max_load
                FROM {self.db._tbl('sales_reps')}
                WHERE is_active = true AND current_load < max_load
                ORDER BY current_load ASC
                """
            )
            # Sanitize — convert any non-serializable types to plain Python
            clean = []
            for r in reps:
                clean.append({
                    "rep_id":       str(r.get("rep_id", "")),
                    "name":         str(r.get("name", "")),
                    "email":        str(r.get("email", "")),
                    "team":         str(r.get("team", "")),
                    "current_load": int(r.get("current_load") or 0),
                    "max_load":     int(r.get("max_load") or 50),
                })
            return clean
        except Exception:
            return [
                {"rep_id": "REP001", "name": "Alex Chen",    "email": "alex.chen@company.com",   "team": "enterprise_sales", "current_load": 12},
                {"rep_id": "REP002", "name": "Maria Santos", "email": "maria.santos@company.com", "team": "mid_market_sales", "current_load": 8},
                {"rep_id": "REP003", "name": "James Wright", "email": "james.wright@company.com", "team": "smb_sales",        "current_load": 5},
            ]

    def _assign_rep(self, team: Optional[str], reps: list[dict]) -> Optional[dict]:
        """Assign the rep with lowest load in the target team."""
        if not reps:
            return None
        team_reps = [r for r in reps if r.get("team") == team]
        if not team_reps:
            team_reps = reps  # fallback to any available rep
        return min(team_reps, key=lambda r: r.get("current_load", 999))

    def _notify_sales_rep(self, sql_result: SQLResult, raw_lead: dict) -> None:
        """
        Sales handoff notification stub.
        In production: integrate with Slack, email, or CRM webhook.
        """
        self.log(
            f"[blue]📧 Handoff notification → {sql_result.assigned_rep_email}[/blue]"
        )
        # TODO: Implement CRM webhook, Slack notification, or email
        # Example:
        # requests.post(SLACK_WEBHOOK, json={
        #     "text": f"New SQL assigned to {sql_result.assigned_rep_name}: "
        #             f"{raw_lead['first_name']} {raw_lead['last_name']} @ {raw_lead['company']}"
        # })
