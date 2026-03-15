"""
Lead Gen Assistant - Analytics Agent
Reports on lead pipeline health, funnel metrics, and lead status.
Powers the Genie-ready analytics_summary table.
"""

import json
import time
from datetime import datetime, timezone
from typing import Optional

from agents.base_agent import BaseAgent
from utils.models import FunnelMetrics
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


ANALYTICS_SYSTEM_PROMPT = """
You are the Analytics Agent for an enterprise Lead Generation pipeline.

Your job is to analyze lead funnel metrics and provide actionable insights.
You receive structured pipeline data and produce:
1. A concise executive summary (3-5 bullet points)
2. Key observations about conversion rates and pipeline health
3. Specific recommendations to improve funnel performance

Be data-driven, specific, and actionable. Reference actual numbers.
Format your response as clear prose with bullet points for recommendations.
"""


class AnalyticsAgent(BaseAgent):
    """
    Analytics Agent — Pipeline reporting and insights.

    Responsibilities:
    - Query all pipeline tables for funnel metrics
    - Calculate conversion rates and velocity
    - Generate AI-powered insights via Claude
    - Write summary to analytics_summary table
    - Display rich terminal reports
    - Support Genie table refresh
    """

    def process(self, days: int = 30, lead_id: Optional[str] = None) -> dict:
        """
        Generate analytics report.

        Args:
            days:    Lookback period in days for funnel metrics
            lead_id: Optional — report on a single lead's journey

        Returns:
            Dict with metrics and AI insights
        """
        if lead_id:
            return self._single_lead_report(lead_id)
        else:
            return self._funnel_report(days)

    # ------------------------------------------------------------------
    # Funnel Report
    # ------------------------------------------------------------------

    def _funnel_report(self, days: int) -> dict:
        self.log(f"Generating [cyan]{days}-day[/cyan] funnel analytics report...")

        # 1. Fetch metrics from Databricks
        metrics = self._fetch_funnel_metrics(days)

        # 2. Display rich terminal table
        self._display_funnel_table(metrics, days)

        # 3. Get AI insights from Claude
        insights = self._get_ai_insights(metrics, days)

        # 4. Write to analytics_summary table
        self._write_summary(metrics, insights)

        return {"metrics": metrics, "insights": insights}

    def _fetch_funnel_metrics(self, days: int) -> dict:
        """Query Databricks for funnel counts."""
        try:
            raw_stats = self.db.get_funnel_stats(days)

            captured     = sum(raw_stats.values())
            rejected     = raw_stats.get("rejected", 0)
            accepted     = raw_stats.get("accepted", 0)
            mql          = raw_stats.get("mql", 0)
            sql          = raw_stats.get("sql", 0)
            sales_owned  = raw_stats.get("sales_owned", 0)

            def safe_rate(num, den):
                return round(num / den, 4) if den > 0 else 0.0

            # Velocity from lead_events
            velocity = self._fetch_velocity(days)

        except Exception as e:
            self.log(f"[yellow]Using demo data — DB not connected: {e}[/yellow]")
            # Demo data for cookbook demonstration
            captured, rejected, accepted = 248, 42, 206
            mql, sql, sales_owned        = 87, 34, 28

            def safe_rate(num, den):
                return round(num / den, 4) if den > 0 else 0.0

            velocity = {
                "avg_time_to_mql":     4.2,
                "avg_time_to_sql":     18.5,
                "avg_time_to_handoff": 2.1,
            }

        return {
            "period_days":          days,
            "leads_captured":       captured,
            "leads_rejected":       rejected,
            "leads_accepted":       accepted,
            "leads_mql":            mql,
            "leads_sql":            sql,
            "leads_sales_owned":    sales_owned,
            "acceptance_rate":      safe_rate(accepted, captured),
            "mql_conversion_rate":  safe_rate(mql, accepted),
            "sql_conversion_rate":  safe_rate(sql, mql),
            "sales_conversion_rate":safe_rate(sales_owned, sql),
            "overall_funnel_rate":  safe_rate(sales_owned, captured),
            **velocity,
        }

    def _fetch_velocity(self, days: int) -> dict:
        """Calculate average time between pipeline stages."""
        try:
            rows = self.db.execute(
                f"""
                SELECT
                  AVG(DATEDIFF(HOUR, r.created_at, m.qualified_at)) AS avg_time_to_mql,
                  AVG(DATEDIFF(HOUR, m.qualified_at, s.qualified_at)) AS avg_time_to_sql
                FROM {self.db._tbl('raw_leads')} r
                LEFT JOIN {self.db._tbl('mql_leads')} m ON r.lead_id = m.lead_id
                LEFT JOIN {self.db._tbl('sql_leads')} s ON m.mql_id  = s.mql_id
                WHERE r.created_at >= DATEADD(DAY, -{days}, CURRENT_TIMESTAMP())
                """
            )
            row = rows[0] if rows else {}
            return {
                "avg_time_to_mql":     round(float(row.get("avg_time_to_mql", 0) or 0), 1),
                "avg_time_to_sql":     round(float(row.get("avg_time_to_sql", 0) or 0), 1),
                "avg_time_to_handoff": 2.0,
            }
        except Exception:
            return {"avg_time_to_mql": 0, "avg_time_to_sql": 0, "avg_time_to_handoff": 0}

    def _display_funnel_table(self, m: dict, days: int) -> None:
        """Print a rich formatted funnel report to terminal."""

        # Header panel
        console.print(Panel(
            f"[bold cyan]Lead Gen Pipeline Report — Last {days} Days[/bold cyan]\n"
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            box=box.DOUBLE_EDGE
        ))

        # Funnel volume table
        table = Table(title="Pipeline Funnel", box=box.ROUNDED, show_header=True)
        table.add_column("Stage",          style="cyan",  width=20)
        table.add_column("Count",          style="white", justify="right")
        table.add_column("Conversion",     style="green", justify="right")
        table.add_column("Status",         style="white")

        table.add_row(
            "📥 Leads Captured",
            str(m["leads_captured"]), "—", ""
        )
        table.add_row(
            "✅ Accepted",
            str(m["leads_accepted"]),
            f"{m['acceptance_rate']*100:.1f}%",
            self._bar(m["acceptance_rate"])
        )
        table.add_row(
            "❌ Rejected",
            str(m["leads_rejected"]),
            f"{(m['leads_rejected']/max(m['leads_captured'],1))*100:.1f}%",
            ""
        )
        table.add_row(
            "⭐ MQL",
            str(m["leads_mql"]),
            f"{m['mql_conversion_rate']*100:.1f}%",
            self._bar(m["mql_conversion_rate"])
        )
        table.add_row(
            "💼 SQL",
            str(m["leads_sql"]),
            f"{m['sql_conversion_rate']*100:.1f}%",
            self._bar(m["sql_conversion_rate"])
        )
        table.add_row(
            "🏆 Sales Owned",
            str(m["leads_sales_owned"]),
            f"{m['sales_conversion_rate']*100:.1f}%",
            self._bar(m["sales_conversion_rate"])
        )
        console.print(table)

        # Velocity table
        vel_table = Table(title="Pipeline Velocity", box=box.ROUNDED)
        vel_table.add_column("Metric", style="cyan")
        vel_table.add_column("Value",  style="green", justify="right")

        vel_table.add_row("Avg Time to MQL",      f"{m.get('avg_time_to_mql',0):.1f} hrs")
        vel_table.add_row("Avg Time to SQL",      f"{m.get('avg_time_to_sql',0):.1f} hrs")
        vel_table.add_row("Avg Time to Handoff",  f"{m.get('avg_time_to_handoff',0):.1f} hrs")
        vel_table.add_row(
            "Overall Funnel Rate",
            f"{m['overall_funnel_rate']*100:.2f}%"
        )
        console.print(vel_table)

    def _bar(self, rate: float, width: int = 20) -> str:
        filled = int(rate * width)
        return "█" * filled + "░" * (width - filled)

    def _get_ai_insights(self, metrics: dict, days: int) -> str:
        """Use Claude to generate insights from pipeline metrics."""
        self.log("Generating AI insights...")

        response = self.call_claude(
            system_prompt = ANALYTICS_SYSTEM_PROMPT,
            user_message  = f"""
Analyze these lead pipeline metrics for the last {days} days and provide insights:

{json.dumps(metrics, indent=2)}

Industry benchmarks for context:
- Average MQL conversion rate: 15-25%
- Average SQL conversion rate: 30-40%
- Average time to MQL: 2-6 hours (automated pipeline)
- Overall funnel rate (raw to sales): 5-15%

Provide:
1. Executive summary (3 bullet points)
2. What's working well
3. Areas of concern
4. Top 3 specific recommendations
""",
        )

        insights = response["text"]
        console.print(Panel(
            insights,
            title="[bold yellow]🤖 AI Pipeline Insights[/bold yellow]",
            box=box.ROUNDED,
        ))
        return insights

    def _write_summary(self, metrics: dict, insights: str) -> None:
        """Write analytics summary to Databricks."""
        try:
            import uuid
            summary_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()

            self.db.execute(
                f"""
                INSERT INTO {self.db._tbl('analytics_summary')}
                (summary_id, report_date, report_period,
                 leads_captured, leads_accepted, leads_rejected,
                 leads_mql, leads_sql, leads_sales_owned,
                 acceptance_rate, mql_conversion_rate, sql_conversion_rate,
                 sales_conversion_rate, overall_funnel_rate,
                 avg_time_to_mql, avg_time_to_sql, avg_time_to_handoff,
                 computed_at, computed_by)
                VALUES (?, CURRENT_DATE(), 'daily',
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?,
                        ?, ?, ?,
                        ?, 'analytics_agent')
                """,
                [
                    summary_id,
                    metrics["leads_captured"], metrics["leads_accepted"],
                    metrics["leads_rejected"], metrics["leads_mql"],
                    metrics["leads_sql"], metrics["leads_sales_owned"],
                    metrics["acceptance_rate"], metrics["mql_conversion_rate"],
                    metrics["sql_conversion_rate"], metrics["sales_conversion_rate"],
                    metrics["overall_funnel_rate"],
                    metrics.get("avg_time_to_mql", 0),
                    metrics.get("avg_time_to_sql", 0),
                    metrics.get("avg_time_to_handoff", 0),
                    now,
                ],
            )
            self.log("[green]✓ Analytics summary written to Databricks[/green]")
        except Exception as e:
            self.log(f"[yellow]Analytics write skipped: {e}[/yellow]")

    # ------------------------------------------------------------------
    # Single Lead Report
    # ------------------------------------------------------------------

    def _single_lead_report(self, lead_id: str) -> dict:
        """Report on a single lead's full journey."""
        self.log(f"Fetching journey for lead [yellow]{lead_id}[/yellow]")

        raw_lead = self.db.get_raw_lead(lead_id)
        if not raw_lead:
            console.print(f"[red]Lead {lead_id} not found[/red]")
            return {}

        timeline = self.db.get_lead_timeline(lead_id)

        # Display lead summary
        console.print(Panel(
            f"[bold]Lead ID:[/bold] {lead_id}\n"
            f"[bold]Name:[/bold] {raw_lead.get('first_name')} {raw_lead.get('last_name')}\n"
            f"[bold]Email:[/bold] {raw_lead.get('email')}\n"
            f"[bold]Company:[/bold] {raw_lead.get('company')}\n"
            f"[bold]Status:[/bold] [cyan]{raw_lead.get('status', 'unknown').upper()}[/cyan]\n"
            f"[bold]Source:[/bold] {raw_lead.get('source_channel')} / {raw_lead.get('form_type')}",
            title="[bold cyan]Lead Summary[/bold cyan]",
            box=box.ROUNDED,
        ))

        # Timeline table
        if timeline:
            tl_table = Table(title="Lead Journey Timeline", box=box.ROUNDED)
            tl_table.add_column("Timestamp",  style="dim",    width=22)
            tl_table.add_column("Event",      style="cyan",   width=25)
            tl_table.add_column("Agent",      style="yellow", width=18)
            tl_table.add_column("Status",     style="green",  width=20)
            tl_table.add_column("Score",      style="white",  width=8)

            for evt in timeline:
                status_str = f"{evt.get('from_status','—')} → {evt.get('to_status','—')}"
                tl_table.add_row(
                    str(evt.get("event_timestamp", ""))[:19],
                    evt.get("event_type", ""),
                    evt.get("agent_name", ""),
                    status_str,
                    str(evt.get("score_at_event") or "—"),
                )
            console.print(tl_table)
        else:
            console.print("[yellow]No timeline events found for this lead.[/yellow]")

        return {"lead": raw_lead, "timeline": timeline}
