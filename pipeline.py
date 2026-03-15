"""
Lead Gen Assistant - Pipeline Orchestrator
Coordinates the multi-agent pipeline:
  Raw Lead → Triage → MQL → SQL → Sales Handoff
"""

import time
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich import box

from agents.triage_agent    import TriageAgent
from agents.mql_agent       import MQLAgent
from agents.sql_agent       import SQLAgent
from agents.analytics_agent import AnalyticsAgent
from utils.models           import RawLeadInput
from utils.databricks_client import DatabricksClient

console = Console()


class LeadGenPipeline:
    """
    Orchestrates the full multi-agent lead qualification pipeline.

    Flow:
      1. Triage Agent    — validates raw lead, accept/reject
      2. MQL Agent       — scores and enriches accepted lead
      3. SQL Agent       — BANT qualifies MQL → SQL
      4. Analytics Agent — reports on any lead or full funnel
    """

    def __init__(self):
        self.db       = DatabricksClient()
        self.triage   = TriageAgent(self.db)
        self.mql      = MQLAgent(self.db)
        self.sql_ag   = SQLAgent(self.db)
        self.analytics= AnalyticsAgent(self.db)

    def process_lead(self, lead_input: RawLeadInput) -> dict:
        """
        Run a raw lead through the full pipeline.
        Returns a summary dict of all agent results.
        """
        start = time.time()

        console.print(Panel(
            f"[bold cyan]🚀 Lead Gen Pipeline Starting[/bold cyan]\n"
            f"Lead: [white]{lead_input.first_name} {lead_input.last_name}[/white] "
            f"< {lead_input.email} > @ [yellow]{lead_input.company}[/yellow]",
            box=box.DOUBLE_EDGE,
        ))

        result = {
            "lead_id":     None,
            "triage":      None,
            "mql":         None,
            "sql":         None,
            "final_status":"unknown",
        }

        # ── Stage 1: Triage ──────────────────────────────────────────
        console.rule("[bold]Stage 1 · Triage Agent[/bold]")
        triage_result = self.triage.process(lead_input)
        result["lead_id"] = triage_result.lead_id
        result["triage"]  = triage_result.model_dump()

        if triage_result.decision == "rejected":
            result["final_status"] = "rejected"
            self._summary(result, time.time() - start)
            return result

        if triage_result.decision == "needs_review":
            result["final_status"] = "needs_human_review"
            console.print("[yellow]⚠ Lead flagged for human review — pipeline paused[/yellow]")
            self._summary(result, time.time() - start)
            return result

        # ── Stage 2: MQL Agent ───────────────────────────────────────
        console.rule("[bold]Stage 2 · MQL Agent[/bold]")
        mql_result = self.mql.process(triage_result.lead_id)
        result["mql"] = mql_result.model_dump()

        if not mql_result.qualified:
            result["final_status"] = "nurture"
            self._summary(result, time.time() - start)
            return result

        # ── Stage 3: SQL Agent ───────────────────────────────────────
        console.rule("[bold]Stage 3 · SQL Agent[/bold]")
        sql_result = self.sql_ag.process(mql_result.mql_id)
        result["sql"] = sql_result.model_dump()

        if sql_result.qualified:
            result["final_status"] = "sales_owned"
        else:
            result["final_status"] = "mql_nurture"

        self._summary(result, time.time() - start)
        return result

    def get_analytics(self, days: int = 30) -> dict:
        """Run the analytics agent for a funnel report."""
        console.rule("[bold]Analytics Agent[/bold]")
        return self.analytics.process(days=days)

    def get_lead_status(self, lead_id: str) -> dict:
        """Get the full journey for a specific lead."""
        console.rule(f"[bold]Lead Status: {lead_id}[/bold]")
        return self.analytics.process(lead_id=lead_id)

    def _summary(self, result: dict, elapsed: float) -> None:
        """Print a final pipeline summary panel."""
        status = result["final_status"]
        color_map = {
            "rejected":           "red",
            "needs_human_review": "yellow",
            "nurture":            "yellow",
            "mql_nurture":        "yellow",
            "sales_owned":        "green",
        }
        color = color_map.get(status, "white")

        triage_str = ""
        mql_str    = ""
        sql_str    = ""

        if result.get("triage"):
            t = result["triage"]
            triage_str = f"  Triage: {t['decision'].upper()} (confidence: {t['confidence']:.0%})\n"

        if result.get("mql"):
            m = result["mql"]
            mql_str = f"  MQL Score: {m['mql_score']}/100 | Persona: {m.get('persona')} | Stage: {m.get('buying_stage')}\n"

        if result.get("sql"):
            s = result["sql"]
            sql_str = (
                f"  BANT Score: {s['sql_score']}/100 | Deal: {s.get('estimated_deal_size')}\n"
                f"  Assigned Rep: {s.get('assigned_rep_name')} ({s.get('assigned_team')})\n"
                f"  Next Step: {s.get('next_step')}\n"
            )

        console.print(Panel(
            f"[bold]Lead ID:[/bold]      {result['lead_id']}\n"
            f"[bold]Final Status:[/bold] [{color}]{status.upper().replace('_',' ')}[/{color}]\n"
            f"[bold]Duration:[/bold]     {elapsed:.2f}s\n\n"
            f"{triage_str}{mql_str}{sql_str}",
            title="[bold]Pipeline Complete[/bold]",
            box=box.DOUBLE_EDGE,
        ))
