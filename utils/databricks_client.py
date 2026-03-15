"""
Lead Gen Assistant - Databricks Connection Utility
Handles all Databricks SQL Warehouse connections and operations
"""

import os
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Any
from dotenv import load_dotenv

from databricks import sql as databricks_sql
from databricks.sdk import WorkspaceClient
from rich.console import Console

load_dotenv()
console = Console()


class DatabricksClient:
    """
    Manages Databricks SQL connections and CRUD operations
    for the Lead Gen Assistant pipeline tables.
    """

    CATALOG = "lead_gen"
    SCHEMA  = "sales_pipeline"

    def __init__(self):
        self.host  = os.getenv("DATABRICKS_HOST", "").rstrip("/")
        self.token = os.getenv("DATABRICKS_TOKEN", "")
        self.http_path = os.getenv(
            "DATABRICKS_HTTP_PATH",
            "/sql/1.0/warehouses/auto"
        )

        if not self.host or not self.token:
            raise ValueError(
                "DATABRICKS_HOST and DATABRICKS_TOKEN must be set in .env"
            )

        self._connection = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def get_connection(self):
        """Return (or create) a persistent SQL warehouse connection."""
        if self._connection is None:
            self._connection = databricks_sql.connect(
                server_hostname=self.host.replace("https://", ""),
                http_path=self.http_path,
                access_token=self.token,
            )
        return self._connection

    def execute(self, query: str, params: Optional[list] = None) -> list[dict]:
        """Execute a SQL query and return results as a list of dicts."""
        conn   = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(query, params or [])
            if cursor.description:
                cols = [d[0] for d in cursor.description]
                return [dict(zip(cols, row)) for row in cursor.fetchall()]
            return []
        finally:
            cursor.close()

    def execute_script(self, sql_path: str) -> None:
        """Execute a multi-statement SQL script file."""
        with open(sql_path, "r") as f:
            raw = f.read()

        # Split on semicolons, skip blanks and comment-only blocks
        statements = [
            s.strip() for s in raw.split(";")
            if s.strip() and not s.strip().startswith("--")
        ]

        conn   = self.get_connection()
        cursor = conn.cursor()
        try:
            for stmt in statements:
                if stmt:
                    cursor.execute(stmt)
                    console.print(f"  [green]✓[/green] {stmt[:60]}...")
        finally:
            cursor.close()

    def close(self):
        if self._connection:
            self._connection.close()
            self._connection = None

    # ------------------------------------------------------------------
    # Table helpers
    # ------------------------------------------------------------------

    def _tbl(self, table: str) -> str:
        return f"{self.CATALOG}.{self.SCHEMA}.{table}"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _gen_id(self, prefix: str) -> str:
        date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
        uid       = str(uuid.uuid4())[:8].upper()
        return f"{prefix}-{date_part}-{uid}"

    # ------------------------------------------------------------------
    # raw_leads
    # ------------------------------------------------------------------

    def insert_raw_lead(self, lead: dict) -> str:
        """Insert a new raw lead. Returns the generated lead_id."""
        lead_id = self._gen_id("LD")
        now     = self._now()

        # Build interests as SQL array literal — ARRAY<STRING> cannot use ? params
        interests = lead.get("interests", [])
        if isinstance(interests, str):
            interests = []
        interests_sql = "array(" + ",".join(f"'{i}'" for i in interests) + ")" if interests else "array()"

        self.execute(
            f"""
            INSERT INTO {self._tbl('raw_leads')}
            (lead_id, created_at, updated_at,
             source_channel, source_campaign, source_url, form_type,
             utm_source, utm_medium, utm_campaign,
             first_name, last_name, email, phone, linkedin_url,
             company, job_title, department, company_size, industry,
             country, state_region, message, interests, opt_in_marketing,
             status, raw_payload)
            VALUES (
              ?, ?, ?,
              ?, ?, ?, ?,
              ?, ?, ?,
              ?, ?, ?, ?, ?,
              ?, ?, ?, ?, ?,
              ?, ?, ?, {interests_sql}, ?,
              'new', ?
            )
            """,
            [
                lead_id, now, now,
                lead.get("source_channel", "web_form"),
                lead.get("source_campaign"), lead.get("source_url"),
                lead.get("form_type", "contact_us"),
                lead.get("utm_source"), lead.get("utm_medium"),
                lead.get("utm_campaign"),
                lead.get("first_name"), lead.get("last_name"),
                lead.get("email"), lead.get("phone"),
                lead.get("linkedin_url"),
                lead.get("company"), lead.get("job_title"),
                lead.get("department"), lead.get("company_size"),
                lead.get("industry"), lead.get("country"),
                lead.get("state_region"), lead.get("message"),
                lead.get("opt_in_marketing", True),
                json.dumps(lead),
            ],
        )
        return lead_id

    def update_lead_status(self, lead_id: str, status: str,
                           rejection_reason: Optional[str] = None) -> None:
        self.execute(
            f"""
            UPDATE {self._tbl('raw_leads')}
            SET status = ?, updated_at = ?,
                rejection_reason = COALESCE(?, rejection_reason)
            WHERE lead_id = ?
            """,
            [status, self._now(), rejection_reason, lead_id],
        )

    def get_raw_lead(self, lead_id: str) -> Optional[dict]:
        rows = self.execute(
            f"SELECT * FROM {self._tbl('raw_leads')} WHERE lead_id = ?",
            [lead_id],
        )
        return rows[0] if rows else None

    # ------------------------------------------------------------------
    # mql_leads
    # ------------------------------------------------------------------

    def insert_mql_lead(self, mql: dict) -> str:
        mql_id = self._gen_id("MQL")
        now    = self._now()

        def to_array_sql(val):
            """Convert a list to a SQL array() literal."""
            if not val or not isinstance(val, list):
                return "array()"
            return "array(" + ",".join(f"'{str(v)}'" for v in val) + ")"

        tech_sql     = to_array_sql(mql.get("technologies_used", []))
        interest_sql = to_array_sql(mql.get("product_interest", []))
        pain_sql     = to_array_sql(mql.get("pain_points", []))

        self.execute(
            f"""
            INSERT INTO {self._tbl('mql_leads')}
            (mql_id, lead_id, created_at, updated_at, qualified_at,
             mql_score, score_breakdown,
             enriched_company, enriched_industry, enriched_employees,
             enriched_revenue, technologies_used,
             persona, buying_stage, product_interest, pain_points,
             agent_version, agent_reasoning, confidence_score,
             human_reviewed, status, nurture_track)
            VALUES (?, ?, ?, ?, ?,
                    ?, ?,
                    ?, ?, ?,
                    ?, {tech_sql},
                    ?, ?, {interest_sql}, {pain_sql},
                    ?, ?, ?,
                    false, ?, ?)
            """,
            [
                mql_id, mql["lead_id"], now, now, now,
                mql.get("mql_score"), json.dumps(mql.get("score_breakdown", {})),
                mql.get("enriched_company"), mql.get("enriched_industry"),
                mql.get("enriched_employees"), mql.get("enriched_revenue"),
                mql.get("persona"), mql.get("buying_stage"),
                mql.get("agent_version", "1.0.0"),
                mql.get("agent_reasoning"), mql.get("confidence_score", 0.8),
                "mql_new", mql.get("nurture_track"),
            ],
        )
        return mql_id

    def get_mql_lead(self, mql_id: str) -> Optional[dict]:
        rows = self.execute(
            f"SELECT * FROM {self._tbl('mql_leads')} WHERE mql_id = ?",
            [mql_id],
        )
        return rows[0] if rows else None

    # ------------------------------------------------------------------
    # sql_leads
    # ------------------------------------------------------------------

    def insert_sql_lead(self, sql_lead: dict) -> str:
        sql_id = self._gen_id("SQL")
        now    = self._now()

        self.execute(
            f"""
            INSERT INTO {self._tbl('sql_leads')}
            (sql_id, mql_id, lead_id, created_at, updated_at, qualified_at,
             sql_score,
             bant_score_budget, bant_score_authority,
             bant_score_need, bant_score_timeline,
             estimated_deal_size, estimated_close_date,
             use_case_summary, competitive_context, next_step,
             assigned_team, assigned_rep_id, assigned_rep_name,
             assigned_rep_email, assignment_reason,
             agent_version, agent_reasoning, confidence_score,
             status, handoff_confirmed)
            VALUES (?, ?, ?, ?, ?, ?,
                    ?,
                    ?, ?, ?, ?,
                    ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?,
                    ?, ?, ?,
                    'sql_new', false)
            """,
            [
                sql_id, sql_lead["mql_id"], sql_lead["lead_id"],
                now, now, now,
                sql_lead.get("sql_score"),
                sql_lead.get("bant_score_budget"),
                sql_lead.get("bant_score_authority"),
                sql_lead.get("bant_score_need"),
                sql_lead.get("bant_score_timeline"),
                sql_lead.get("estimated_deal_size"),
                sql_lead.get("estimated_close_date"),
                sql_lead.get("use_case_summary"),
                sql_lead.get("competitive_context"),
                sql_lead.get("next_step"),
                sql_lead.get("assigned_team"),
                sql_lead.get("assigned_rep_id"),
                sql_lead.get("assigned_rep_name"),
                sql_lead.get("assigned_rep_email"),
                sql_lead.get("assignment_reason"),
                sql_lead.get("agent_version", "1.0.0"),
                sql_lead.get("agent_reasoning"),
                sql_lead.get("confidence_score", 0.8),
            ],
        )
        return sql_id

    # ------------------------------------------------------------------
    # lead_events  (append-only audit log)
    # ------------------------------------------------------------------

    def log_event(
        self,
        lead_id: str,
        event_type: str,
        agent_name: str,
        from_status: Optional[str] = None,
        to_status:   Optional[str] = None,
        score: Optional[int]       = None,
        details: Optional[dict]    = None,
        duration_seconds: Optional[int] = None,
        error_message: Optional[str]    = None,
    ) -> None:
        event_id = self._gen_id("EVT")
        self.execute(
            f"""
            INSERT INTO {self._tbl('lead_events')}
            (event_id, lead_id, event_timestamp, event_type,
             from_status, to_status, agent_name,
             score_at_event, event_details,
             duration_seconds, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                event_id, lead_id, self._now(), event_type,
                from_status, to_status, agent_name,
                score, json.dumps(details or {}),
                duration_seconds, error_message,
            ],
        )

    # ------------------------------------------------------------------
    # analytics helpers
    # ------------------------------------------------------------------

    def get_funnel_stats(self, days: int = 30) -> dict:
        rows = self.execute(
            f"""
            SELECT
              status,
              COUNT(*) AS count
            FROM {self._tbl('raw_leads')}
            WHERE created_at >= DATEADD(DAY, -{days}, CURRENT_TIMESTAMP())
            GROUP BY status
            """
        )
        return {r["status"]: r["count"] for r in rows}

    def get_lead_timeline(self, lead_id: str) -> list[dict]:
        return self.execute(
            f"""
            SELECT event_timestamp, event_type, agent_name,
                   from_status, to_status, score_at_event
            FROM {self._tbl('lead_events')}
            WHERE lead_id = ?
            ORDER BY event_timestamp ASC
            """,
            [lead_id],
        )
