"""
LangGuard Policy Engine — Starter Pack
Enforces all 7 starter policies for the Lead Gen Assistant.

This is a local simulation of the LangGuard Control Plane.
In production, policy.check() calls the LangGuard Cloud API.

Usage in agents:
    from policy_packs.starter.enforcement.policy_engine import policy_engine

    # Before LLM call
    result = policy_engine.check("spend_guard", context)
    if result.action == "deny":
        raise PolicyViolation(result.message)

    # After decision
    policy_engine.log_decision("decision_audit", context)

    # Wrap tool calls
    with policy_engine.track_tool("claude_api", agent_name, lead_id):
        response = call_claude(...)
"""

import re
import json
import time
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from contextlib import contextmanager
from dataclasses import dataclass, field

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()

# Load policy definitions
_policy_path = Path(__file__).parent.parent / "policies.yaml"
with open(_policy_path) as f:
    POLICY_CONFIG = yaml.safe_load(f)

# Build policy lookup
POLICIES = {p["id"]: p for p in POLICY_CONFIG["policies"]}


# ============================================================
# Data Classes
# ============================================================

@dataclass
class PolicyResult:
    policy_id:  str
    action:     str          # allow | deny | escalate
    triggered:  bool         # Whether policy fired
    message:    str = ""
    details:    dict = field(default_factory=dict)


@dataclass
class ToolCall:
    tool:        str
    agent:       str
    lead_id:     str
    started_at:  datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at:    Optional[datetime] = None
    duration_ms: Optional[int] = None
    status:      str = "running"
    inputs:      Optional[dict] = None
    outputs:     Optional[dict] = None
    tokens_used: Optional[int] = None


# ============================================================
# Policy Engine
# ============================================================

class PolicyEngine:
    """
    LangGuard Policy Engine (local simulation).
    Enforces all starter pack policies and builds
    a real-time tool access map per lead.
    """

    def __init__(self):
        self.spend_tracker:  dict[str, float] = {}   # lead_id → total cost
        self.tool_access_map:dict[str, list]  = {}   # lead_id → [ToolCall]
        self.processed_emails: dict[str, dict] = {}  # email → lead record
        self.audit_log:      list[dict]        = []
        self.active_tool_calls: list[ToolCall] = []

    # ------------------------------------------------------------------
    # Main check interface
    # ------------------------------------------------------------------

    def check(self, policy_id: str, context: dict) -> PolicyResult:
        """
        Run a policy check. Returns PolicyResult with action.

        Args:
            policy_id: Policy to check e.g. "spend_guard"
            context:   Dict with lead_id, agent, cost, data etc.
        """
        policy = POLICIES.get(policy_id)
        if not policy or not policy.get("enabled", True):
            return PolicyResult(policy_id=policy_id, action="allow", triggered=False)

        # Route to correct handler
        handlers = {
            "spend_guard":       self._check_spend_guard,
            "pii_detection":     self._check_pii_detection,
            "approval_gate":     self._check_approval_gate,
            "retry_fallback":    self._check_retry_fallback,
            "decision_audit":    self._check_decision_audit,
            "duplicate_detection": self._check_duplicate,
            "tool_transparency": self._check_tool_transparency,
        }

        handler = handlers.get(policy_id)
        if not handler:
            return PolicyResult(policy_id=policy_id, action="allow", triggered=False)

        result = handler(policy, context)
        self._log_policy_result(result, context)
        return result

    # ------------------------------------------------------------------
    # Policy 1 — Spend Guard
    # ------------------------------------------------------------------

    def _check_spend_guard(self, policy: dict, context: dict) -> PolicyResult:
        lead_id   = context.get("lead_id", "unknown")
        cost      = float(context.get("estimated_cost_usd", 0.0))
        cfg       = policy["config"]
        max_run   = cfg["max_cost_per_run_usd"]
        max_agent = cfg["max_cost_per_agent_usd"]
        warn_pct  = cfg["warn_at_pct"] / 100

        # Track cumulative cost per lead
        current = self.spend_tracker.get(lead_id, 0.0)
        new_total = current + cost
        self.spend_tracker[lead_id] = new_total

        # Per-agent check
        if cost > max_agent:
            msg = f"Spend Guard: Agent cost ${cost:.3f} exceeds per-agent limit ${max_agent}"
            self._display_policy_alert("spend_guard", "DENY", msg, lead_id)
            return PolicyResult(
                policy_id="spend_guard", action="deny",
                triggered=True, message=msg,
                details={"cost": cost, "limit": max_agent, "lead_id": lead_id}
            )

        # Total run check
        if new_total > max_run:
            msg = f"Spend Guard: Total run cost ${new_total:.3f} exceeds limit ${max_run}"
            self._display_policy_alert("spend_guard", "DENY", msg, lead_id)
            return PolicyResult(
                policy_id="spend_guard", action="deny",
                triggered=True, message=msg,
                details={"total_cost": new_total, "limit": max_run}
            )

        # Warning threshold
        if new_total >= max_run * warn_pct:
            console.print(
                f"  [yellow]💰 Spend Guard:[/yellow] "
                f"${new_total:.3f} of ${max_run} budget used for lead {lead_id}"
            )

        return PolicyResult(policy_id="spend_guard", action="allow", triggered=False,
                            details={"total_cost": new_total})

    def record_spend(self, lead_id: str, cost_usd: float) -> None:
        """Record actual spend after LLM call completes."""
        current = self.spend_tracker.get(lead_id, 0.0)
        self.spend_tracker[lead_id] = current + cost_usd

    def get_lead_spend(self, lead_id: str) -> float:
        return self.spend_tracker.get(lead_id, 0.0)

    # ------------------------------------------------------------------
    # Policy 2 — PII Detection
    # ------------------------------------------------------------------

    def _check_pii_detection(self, policy: dict, context: dict) -> PolicyResult:
        lead_id = context.get("lead_id", "unknown")
        data    = context.get("data", {})
        cfg     = policy["config"]

        scan_fields = cfg["scan_fields"]
        patterns    = cfg["pii_patterns"]

        findings = []
        worst_severity = "clean"
        worst_action   = "allow"

        severity_order = {"clean": 0, "low": 1, "high": 2, "critical": 3}
        action_order   = {"allow": 0, "escalate": 1, "deny": 2}

        for field_name in scan_fields:
            value = str(data.get(field_name, ""))
            if not value:
                continue

            for pii_type, pii_cfg in patterns.items():
                if re.search(pii_cfg["pattern"], value, re.IGNORECASE):
                    severity = pii_cfg["severity"]
                    action   = pii_cfg["action"]
                    findings.append({
                        "field":    field_name,
                        "pii_type": pii_type,
                        "severity": severity,
                        "action":   action,
                    })

                    if severity_order.get(severity, 0) > severity_order.get(worst_severity, 0):
                        worst_severity = severity
                    if action_order.get(action, 0) > action_order.get(worst_action, 0):
                        worst_action = action

        if not findings or worst_severity == "clean":
            return PolicyResult(policy_id="pii_detection", action="allow",
                                triggered=False, details={"findings": []})

        # Filter out low severity from display (phone, email are expected)
        notable = [f for f in findings if f["severity"] != "low"]
        if notable:
            msg = f"PII Detection: {', '.join(f['pii_type'] for f in notable)} found in lead {lead_id}"
            self._display_policy_alert("pii_detection", worst_action.upper(), msg, lead_id)
            return PolicyResult(
                policy_id="pii_detection", action=worst_action,
                triggered=True, message=msg, details={"findings": notable}
            )

        return PolicyResult(policy_id="pii_detection", action="allow",
                            triggered=False, details={"findings": findings})

    # ------------------------------------------------------------------
    # Policy 3 — Approval Gate
    # ------------------------------------------------------------------

    def _check_approval_gate(self, policy: dict, context: dict) -> PolicyResult:
        lead_id    = context.get("lead_id", "unknown")
        sql_id     = context.get("sql_id", "unknown")
        deal_size  = context.get("estimated_deal_size", "")
        bant_score = int(context.get("bant_score", 0))
        rep_name   = context.get("assigned_rep_name", "unknown")
        cfg        = policy["config"]

        # Check deal size
        needs_approval = False
        if deal_size == "$200K+":
            needs_approval = True

        # Check BANT confidence
        bant_cfg = cfg["bant_score_thresholds"]
        if bant_score < bant_cfg["low_confidence"]["max_bant"]:
            needs_approval = True

        if needs_approval:
            msg = (
                f"Approval Gate: SQL lead {sql_id} requires approval — "
                f"Deal: {deal_size}, BANT: {bant_score}/100, Rep: {rep_name}"
            )
            self._display_policy_alert("approval_gate", "ESCALATE", msg, lead_id)

            # Show approval prompt
            approved = self._prompt_approval(sql_id, deal_size, bant_score, rep_name)
            if approved:
                return PolicyResult(policy_id="approval_gate", action="allow",
                                    triggered=True, message="Approved by operator",
                                    details={"approved": True})
            else:
                return PolicyResult(policy_id="approval_gate", action="deny",
                                    triggered=True, message="Rejected by operator",
                                    details={"approved": False})

        return PolicyResult(policy_id="approval_gate", action="allow", triggered=False)

    def _prompt_approval(self, sql_id: str, deal_size: str,
                         bant_score: int, rep_name: str) -> bool:
        import sys, threading
        console.print(Panel(
            f"[bold]✋ APPROVAL REQUIRED[/bold]\n\n"
            f"  SQL ID:     [cyan]{sql_id}[/cyan]\n"
            f"  Deal Size:  [yellow]{deal_size}[/yellow]\n"
            f"  BANT Score: [green]{bant_score}/100[/green]\n"
            f"  Assign to:  [white]{rep_name}[/white]\n\n"
            f"  [dim]Auto-approves in 120s[/dim]",
            title="[bold yellow]🛡️ LangGuard Approval Gate[/bold yellow]",
            box=box.DOUBLE_EDGE
        ))

        user_input     = [None]
        input_received = threading.Event()

        def get_input():
            try:
                sys.stdout.write("\n  Approve this handoff? [y/n] > ")
                sys.stdout.flush()
                val = sys.stdin.readline().strip().lower()
                user_input[0] = val
                input_received.set()
            except Exception:
                input_received.set()

        thread = threading.Thread(target=get_input, daemon=True)
        thread.start()

        for remaining in range(120, 0, -1):
            if input_received.wait(timeout=1):
                break
            if remaining % 30 == 0:
                sys.stdout.write(f"\r  Auto-approving in {remaining}s...  ")
                sys.stdout.flush()

        if not input_received.is_set() or user_input[0] is None:
            console.print("\n  [yellow]⏱ Auto-approved[/yellow]")
            return True

        return user_input[0] in ("y", "yes", "")

    # ------------------------------------------------------------------
    # Policy 4 — Retry & Fallback
    # ------------------------------------------------------------------

    def _check_retry_fallback(self, policy: dict, context: dict) -> PolicyResult:
        lead_id   = context.get("lead_id", "unknown")
        agent     = context.get("agent", "unknown")
        error     = context.get("error", "unknown error")
        attempt   = int(context.get("attempt", 1))
        cfg       = policy["config"]

        if attempt <= cfg["max_retries"]:
            console.print(
                f"  [yellow]⚡ Retry/Fallback:[/yellow] "
                f"{agent} failed for lead {lead_id} — retrying (attempt {attempt}/{cfg['max_retries']})"
            )
            time.sleep(cfg["retry_delay_seconds"] * (cfg["backoff_multiplier"] ** (attempt - 1)))
            return PolicyResult(
                policy_id="retry_fallback", action="allow",
                triggered=True, message=f"Retrying attempt {attempt}",
                details={"attempt": attempt, "error": error}
            )
        else:
            msg = f"Retry/Fallback: {agent} exhausted retries for lead {lead_id} — routing to human"
            self._display_policy_alert("retry_fallback", "ESCALATE", msg, lead_id)
            return PolicyResult(
                policy_id="retry_fallback", action="escalate",
                triggered=True, message=msg,
                details={"attempts": attempt, "error": error}
            )

    # ------------------------------------------------------------------
    # Policy 5 — Decision Audit
    # ------------------------------------------------------------------

    def _check_decision_audit(self, policy: dict, context: dict) -> PolicyResult:
        """Always logs — never blocks."""
        lead_id    = context.get("lead_id", "unknown")
        agent      = context.get("agent", "unknown")
        decision   = context.get("decision", "unknown")
        reasoning  = context.get("reasoning", "")
        confidence = context.get("confidence_score", 0)
        duration   = context.get("duration_ms", 0)
        model      = context.get("llm_model", "unknown")
        tokens     = context.get("tokens_used", 0)

        # Hash input data for audit without storing PII
        input_hash = hashlib.sha256(
            json.dumps(context.get("input_data", {}), sort_keys=True).encode()
        ).hexdigest()[:16]

        audit_entry = {
            "audit_id":       str(uuid.uuid4())[:8],
            "timestamp_utc":  datetime.now(timezone.utc).isoformat(),
            "lead_id":        lead_id,
            "agent":          agent,
            "decision":       decision,
            "reasoning":      reasoning[:200] if reasoning else "",
            "confidence_pct": int(float(confidence) * 100),
            "duration_ms":    duration,
            "llm_model":      model,
            "tokens_used":    tokens,
            "input_hash":     input_hash,
            "policy_pack":    "starter/1.0.0",
        }

        self.audit_log.append(audit_entry)

        console.print(
            f"  [dim]📋 Audit:[/dim] [{agent}] {decision.upper()} "
            f"— confidence {int(float(confidence)*100)}% "
            f"| {duration}ms | tokens: {tokens}"
        )

        return PolicyResult(policy_id="decision_audit", action="allow",
                            triggered=True, details=audit_entry)

    # ------------------------------------------------------------------
    # Policy 6 — Duplicate Detection
    # ------------------------------------------------------------------

    def _check_duplicate(self, policy: dict, context: dict) -> PolicyResult:
        email   = (context.get("email") or "").lower().strip()
        lead_id = context.get("lead_id", "unknown")
        cfg     = policy["config"]

        if not email:
            return PolicyResult(policy_id="duplicate_detection", action="allow",
                                triggered=False)

        existing = self.processed_emails.get(email)
        if existing:
            days_ago = (datetime.now(timezone.utc) - existing["submitted_at"]).days
            status   = existing.get("status", "unknown")

            # Allow resubmission for certain statuses
            if status in cfg.get("allow_resubmit_statuses", []):
                return PolicyResult(policy_id="duplicate_detection", action="allow",
                                    triggered=False)

            if days_ago <= cfg["lookback_days"]:
                msg = (
                    f"Duplicate: {email} already submitted {days_ago} days ago "
                    f"as {existing['lead_id']} (status: {status})"
                )
                self._display_policy_alert("duplicate_detection", "DENY", msg, lead_id)
                return PolicyResult(
                    policy_id="duplicate_detection", action="deny",
                    triggered=True, message=msg,
                    details={"existing_lead_id": existing["lead_id"],
                             "days_ago": days_ago, "status": status}
                )

        # Register this email
        self.processed_emails[email] = {
            "lead_id":     lead_id,
            "submitted_at": datetime.now(timezone.utc),
            "status":      "processing",
        }

        return PolicyResult(policy_id="duplicate_detection", action="allow",
                            triggered=False)

    def update_lead_status(self, email: str, status: str) -> None:
        """Update tracked email status as lead progresses."""
        email = email.lower().strip()
        if email in self.processed_emails:
            self.processed_emails[email]["status"] = status

    # ------------------------------------------------------------------
    # Policy 7 — Tool Transparency
    # ------------------------------------------------------------------

    def _check_tool_transparency(self, policy: dict, context: dict) -> PolicyResult:
        """Validates tool access against expected tools per agent."""
        agent    = context.get("agent", "unknown")
        tool     = context.get("tool", "unknown")
        lead_id  = context.get("lead_id", "unknown")
        cfg      = policy["config"]

        expected = cfg.get("expected_tools_per_agent", {}).get(agent, [])

        if tool not in expected and cfg.get("alert_on_unexpected_tool", True):
            msg = f"Tool Transparency: {agent} accessed unexpected tool '{tool}'"
            self._display_policy_alert("tool_transparency", "ESCALATE", msg, lead_id)
            return PolicyResult(
                policy_id="tool_transparency", action="escalate",
                triggered=True, message=msg,
                details={"agent": agent, "tool": tool, "expected": expected}
            )

        return PolicyResult(policy_id="tool_transparency", action="allow",
                            triggered=False)

    @contextmanager
    def track_tool(self, tool: str, agent: str, lead_id: str,
                   inputs: Optional[dict] = None):
        """
        Context manager to track a tool call in real time.

        Usage:
            with policy_engine.track_tool("claude_api", "MQLAgent", lead_id):
                response = call_claude(...)
        """
        tool_call = ToolCall(
            tool=tool, agent=agent, lead_id=lead_id, inputs=inputs
        )

        # Initialize tool access map for this lead
        if lead_id not in self.tool_access_map:
            self.tool_access_map[lead_id] = []

        console.print(
            f"  [dim]🔧 {agent}[/dim] → [cyan]{tool}[/cyan] [dim]starting...[/dim]"
        )

        try:
            yield tool_call
            tool_call.ended_at   = datetime.now(timezone.utc)
            tool_call.duration_ms= int((tool_call.ended_at - tool_call.started_at).total_seconds() * 1000)
            tool_call.status     = "success"

            console.print(
                f"  [dim]🔧 {agent}[/dim] → [cyan]{tool}[/cyan] "
                f"[green]✓[/green] [dim]{tool_call.duration_ms}ms[/dim]"
            )

        except Exception as e:
            tool_call.ended_at   = datetime.now(timezone.utc)
            tool_call.duration_ms= int((tool_call.ended_at - tool_call.started_at).total_seconds() * 1000)
            tool_call.status     = f"error: {str(e)[:50]}"

            console.print(
                f"  [dim]🔧 {agent}[/dim] → [cyan]{tool}[/cyan] "
                f"[red]✗[/red] [dim]{tool_call.duration_ms}ms — {str(e)[:50]}[/dim]"
            )
            raise

        finally:
            self.tool_access_map[lead_id].append(tool_call)

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def _display_policy_alert(self, policy_id: str, action: str,
                               message: str, lead_id: str) -> None:
        color = {"ALLOW": "green", "DENY": "red",
                 "ESCALATE": "yellow"}.get(action, "white")
        console.print(
            f"  [bold {color}]🛡️ LangGuard [{policy_id}][/bold {color}] "
            f"[{color}]{action}[/{color}] — {message}"
        )

    def _log_policy_result(self, result: PolicyResult, context: dict) -> None:
        """Add policy result to audit log."""
        if result.triggered:
            self.audit_log.append({
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "policy_id":     result.policy_id,
                "action":        result.action,
                "lead_id":       context.get("lead_id", "unknown"),
                "agent":         context.get("agent", "unknown"),
                "message":       result.message,
                "details":       result.details,
            })

    # ------------------------------------------------------------------
    # Tool Access Map Report
    # ------------------------------------------------------------------

    def display_tool_access_map(self, lead_id: str) -> None:
        """Display the full tool access map for a lead."""
        calls = self.tool_access_map.get(lead_id, [])
        if not calls:
            return

        table = Table(
            title=f"🔧 Agent Tool Access Map — {lead_id}",
            box=box.ROUNDED, show_header=True
        )
        table.add_column("Agent",    style="cyan",  width=20)
        table.add_column("Tool",     style="white", width=22)
        table.add_column("Status",   style="green", width=10)
        table.add_column("Duration", style="dim",   width=10)
        table.add_column("Time",     style="dim",   width=12)

        for tc in calls:
            status_str = "[green]✓[/green]" if tc.status == "success" else f"[red]{tc.status}[/red]"
            table.add_row(
                tc.agent,
                tc.tool,
                status_str,
                f"{tc.duration_ms}ms" if tc.duration_ms else "—",
                tc.started_at.strftime("%H:%M:%S") if tc.started_at else "—",
            )

        console.print(table)

    def display_audit_summary(self, lead_id: str) -> None:
        """Display audit log entries for a specific lead."""
        entries = [e for e in self.audit_log if e.get("lead_id") == lead_id]
        if not entries:
            return

        console.print(Panel(
            "\n".join([
                f"  [{e.get('policy_id','?')}] {e.get('action','?').upper()} — {e.get('message') or e.get('decision','')}"
                for e in entries
            ]),
            title=f"[bold]📋 LangGuard Policy Audit — {lead_id}[/bold]",
            box=box.ROUNDED,
        ))


# ============================================================
# Singleton — import this in agents
# ============================================================
policy_engine = PolicyEngine()
