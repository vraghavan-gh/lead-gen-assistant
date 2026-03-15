"""
Lead Gen Assistant - Web Form Agent
First agent in the pipeline. Watches for incoming web form submissions,
enriches and validates the lead using configurable rules, then presents
it for human review with a timeout.

Flow:
  1. Receives raw form submission from Flask webhook
  2. Loads rules from config/web_form_rules.yaml
  3. Rule-based pre-checks (no LLM cost)
  4. Claude enrichment and bot risk scoring
  5. Displays enriched lead in terminal
  6. Waits for human y/n — auto-accepts or auto-rejects per config
  7. Hands off to Triage Agent if accepted
"""

import json
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from agents.base_agent import BaseAgent
from utils.models import RawLeadInput

console = Console()

# Load rules config
_rules_path = Path(__file__).parent.parent / "config" / "web_form_rules.yaml"
with open(_rules_path) as f:
    RULES = yaml.safe_load(f)

# Shortcuts
SENSITIVITY         = RULES["sensitivity"]
BOT_THRESHOLDS      = RULES["bot_risk_thresholds"]
AUTO_RULES          = RULES["auto_rules"]
TIMING_RULES        = RULES["timing"]
PERSONAL_DOMAINS    = set(RULES["personal_email_domains"])
SPAM_KEYWORDS       = [kw.lower() for kw in RULES["spam_keywords"]]
GIBBERISH_RULES     = RULES["gibberish_names"]
BLOCKED_NAMES       = set(n.lower() for n in RULES["gibberish_names"]["blocked_names"])
COMMON_NAMES        = RULES["common_names"]
REQUIRED_FIELDS     = RULES["required_fields"]
MESSAGE_QUALITY     = RULES["message_quality"]
BOT_WEIGHTS         = RULES["bot_risk_weights"]
QUALITY_WEIGHTS     = RULES["quality_weights"]
SENIOR_TITLES       = [t.lower() for t in RULES["senior_title_keywords"]]
TIMEOUT_SECONDS     = AUTO_RULES["human_review_timeout_seconds"]
MIN_FILL_SECONDS    = TIMING_RULES["min_human_fill_seconds"][SENSITIVITY]


WEB_FORM_SYSTEM_PROMPT = """
You are the Web Form Agent for an enterprise Lead Generation pipeline.

Your job is to analyze a raw web form submission and:
1. Enrich and normalize the data (fix typos, expand abbreviations, standardize formats)
2. Assess bot/spam risk on a scale of 0-100 (0=definitely human, 100=definitely bot)
3. Score lead quality on a scale of 0-100
4. Extract intent signals from the message
5. Identify red flags

Consider the pre-screening flags already detected by rule-based checks.
Be concise. Use the web_form_analysis tool to return structured results.
"""

WEB_FORM_TOOL = {
    "name": "web_form_analysis",
    "description": "Return enriched lead data with quality and bot risk assessment",
    "input_schema": {
        "type": "object",
        "properties": {
            "normalized_first_name":  {"type": "string"},
            "normalized_last_name":   {"type": "string"},
            "normalized_company":     {"type": "string"},
            "normalized_job_title":   {"type": "string", "description": "Full title, expanded from abbreviations"},
            "normalized_industry":    {"type": "string"},
            "detected_intent": {
                "type": "string",
                "enum": ["high", "medium", "low", "unclear"]
            },
            "intent_signals": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific signals e.g. mentions budget, has timeline, evaluating vendors"
            },
            "bot_risk_score":  {"type": "integer", "description": "0=human, 100=bot"},
            "bot_risk_level": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"]
            },
            "bot_risk_reasons": {
                "type": "array",
                "items": {"type": "string"}
            },
            "lead_quality_score": {"type": "integer", "description": "0-100"},
            "red_flags": {
                "type": "array",
                "items": {"type": "string"}
            },
            "enrichment_notes": {"type": "string"},
            "recommendation": {
                "type": "string",
                "enum": ["accept", "reject", "review"]
            }
        },
        "required": [
            "normalized_first_name", "normalized_last_name",
            "normalized_company", "normalized_job_title",
            "detected_intent", "intent_signals",
            "bot_risk_score", "bot_risk_level", "bot_risk_reasons",
            "lead_quality_score", "red_flags", "recommendation"
        ]
    }
}


class WebFormAgent(BaseAgent):
    """
    Web Form Agent — Human-in-the-loop entry point for live web form submissions.
    All detection rules loaded from config/web_form_rules.yaml.
    """

    def process(self, raw_form_data: dict, submitted_at: Optional[str] = None) -> Optional[RawLeadInput]:
        self.log(
            f"New submission from [cyan]{raw_form_data.get('email')}[/cyan] "
            f"| Sensitivity: [yellow]{SENSITIVITY}[/yellow]"
        )

        # Step 1 — Rule-based pre-checks
        pre_flags, rule_bot_score, rule_quality_score = self._rule_based_checks(
            raw_form_data, submitted_at
        )

        # Step 2 — Auto-reject if clearly a bot
        if rule_bot_score >= AUTO_RULES["auto_reject_above_bot_risk"]:
            self.log(f"[red]✗ Auto-rejected — bot risk score {rule_bot_score}/100 exceeds threshold[/red]")
            return None

        # Step 3 — Claude enrichment
        analysis = self._analyze_with_claude(raw_form_data, pre_flags, rule_bot_score)

        # Step 4 — Display in terminal
        self._display_lead(raw_form_data, analysis, pre_flags)

        # Step 5 — Human review
        accepted = self._human_review(analysis)

        if accepted:
            lead = RawLeadInput(
                first_name     = analysis.get("normalized_first_name") or raw_form_data.get("first_name"),
                last_name      = analysis.get("normalized_last_name")  or raw_form_data.get("last_name"),
                email          = raw_form_data.get("email"),
                company        = analysis.get("normalized_company")    or raw_form_data.get("company"),
                job_title      = analysis.get("normalized_job_title")  or raw_form_data.get("job_title"),
                industry       = analysis.get("normalized_industry")   or raw_form_data.get("industry"),
                company_size   = raw_form_data.get("company_size"),
                country        = raw_form_data.get("country", "US"),
                phone          = raw_form_data.get("phone"),
                form_type      = raw_form_data.get("form_type", "contact_us"),
                source_channel = "web_form",
                message        = raw_form_data.get("message"),
            )
            self.log("[green]✓ Lead accepted — handing off to Triage Agent[/green]")
            return lead
        else:
            self.log("[red]✗ Lead rejected[/red]")
            return None

    # ------------------------------------------------------------------
    # Rule-based pre-checks
    # ------------------------------------------------------------------

    def _rule_based_checks(self, data: dict, submitted_at: Optional[str]) -> tuple[list, int, int]:
        """
        Fast rule-based checks using web_form_rules.yaml.
        Returns (flags, bot_risk_score, quality_score)
        """
        flags      = []
        bot_score  = 0
        qual_score = 0

        # Email domain check
        email  = data.get("email", "")
        domain = email.split("@")[-1].lower() if "@" in email else ""
        if domain in PERSONAL_DOMAINS:
            flags.append(f"Personal email domain: {domain}")
            bot_score += BOT_WEIGHTS["personal_email"]
        elif domain:
            qual_score += QUALITY_WEIGHTS["business_email"]

        # Required fields
        for rule in REQUIRED_FIELDS:
            if not data.get(rule["field"]):
                flags.append(rule["flag_message"])
                bot_score += rule["penalty"]
            elif rule["field"] == "company":
                qual_score += QUALITY_WEIGHTS["has_company"]
            elif rule["field"] == "job_title":
                qual_score += QUALITY_WEIGHTS["has_job_title"]

        # Spam keywords
        message = (data.get("message") or "").lower()
        for kw in SPAM_KEYWORDS:
            if kw in message:
                flags.append(f"Spam keyword: '{kw}'")
                bot_score += BOT_WEIGHTS["spam_keyword"]
                break

        # Gibberish / blocked names
        for name_field in ["first_name", "last_name"]:
            name = (data.get(name_field) or "").strip().lower()
            if not name:
                continue
            if name in BLOCKED_NAMES:
                flags.append(f"Blocked name: '{name}'")
                bot_score += BOT_WEIGHTS["blocked_name"]
            elif len(name) < GIBBERISH_RULES["min_length"]:
                flags.append(f"Name too short: '{name}'")
                bot_score += BOT_WEIGHTS["gibberish_name"]
            elif len(set(name)) < GIBBERISH_RULES["min_unique_chars"]:
                flags.append(f"Gibberish name: '{name}'")
                bot_score += BOT_WEIGHTS["gibberish_name"]

        # Common name check — only on high sensitivity
        if (COMMON_NAMES["enabled_on_sensitivity"] == SENSITIVITY or SENSITIVITY == "high"):
            first = (data.get("first_name") or "").lower()
            last  = (data.get("last_name") or "").lower()
            for combo in COMMON_NAMES["common_combinations"]:
                if [first, last] == combo:
                    flags.append(f"Common name combination: {first} {last}")
                    bot_score += BOT_WEIGHTS["common_name"]
                    break

        # Form timing
        if submitted_at and TIMING_RULES["use_browser_timestamp"]:
            try:
                sub_time = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
                if sub_time.tzinfo is None:
                    sub_time = sub_time.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - sub_time).total_seconds()
                if elapsed < MIN_FILL_SECONDS:
                    flags.append(f"Form submitted in {elapsed:.1f}s (min: {MIN_FILL_SECONDS}s)")
                    bot_score += BOT_WEIGHTS["fast_submission"]
            except Exception:
                pass

        # Message quality
        word_count = len(message.split()) if message else 0
        form_type  = data.get("form_type", "contact_us")
        min_words  = MESSAGE_QUALITY["min_words"].get(SENSITIVITY, 3)
        form_min   = MESSAGE_QUALITY["form_type_minimums"].get(form_type, 3)
        effective_min = max(min_words, form_min)
        if word_count < effective_min and effective_min > 0:
            flags.append(f"Short message ({word_count} words, min {effective_min} for {form_type})")
            bot_score += BOT_WEIGHTS["short_message"]
        elif word_count >= 20:
            qual_score += QUALITY_WEIGHTS["detailed_message"]

        # Senior title bonus
        title = (data.get("job_title") or "").lower()
        if any(kw in title for kw in SENIOR_TITLES):
            qual_score += QUALITY_WEIGHTS["senior_title_keywords"]

        # Company size bonus
        company_size = data.get("company_size", "")
        if company_size in ("1001-5000", "5000+"):
            qual_score += QUALITY_WEIGHTS["enterprise_company_size"]

        # Form type quality
        if form_type == "demo_request":
            qual_score += QUALITY_WEIGHTS["demo_request_form"]

        # Phone/LinkedIn bonuses
        if data.get("phone"):
            qual_score += QUALITY_WEIGHTS["has_phone"]
        if data.get("linkedin_url"):
            qual_score += QUALITY_WEIGHTS["has_linkedin"]

        # Cap scores at 0-100
        bot_score  = min(max(bot_score, 0), 100)
        qual_score = min(max(qual_score, 0), 100)

        return flags, bot_score, qual_score

    # ------------------------------------------------------------------
    # Claude enrichment
    # ------------------------------------------------------------------

    def _analyze_with_claude(self, data: dict, pre_flags: list, rule_bot_score: int) -> dict:
        """Use Claude to enrich, normalize and refine the scores."""
        user_message = f"""
Analyze this web form submission.

Sensitivity profile: {SENSITIVITY}
Pre-screening bot risk score from rules: {rule_bot_score}/100
Pre-screening flags: {json.dumps(pre_flags) if pre_flags else "None"}

Form Data:
{json.dumps(data, indent=2, default=str)}

Use the pre-screening score as a baseline. Adjust up or down based on your analysis.
Use the web_form_analysis tool to return your assessment.
"""
        response = self.call_claude(
            system_prompt = WEB_FORM_SYSTEM_PROMPT,
            user_message  = user_message,
            tools         = [WEB_FORM_TOOL],
            max_tokens    = 1500,
        )

        if response.get("tool_use"):
            return response["tool_use"]["input"]

        # Fallback
        risk_level = self._score_to_level(rule_bot_score)
        return {
            "normalized_first_name": data.get("first_name", ""),
            "normalized_last_name":  data.get("last_name", ""),
            "normalized_company":    data.get("company", ""),
            "normalized_job_title":  data.get("job_title", ""),
            "normalized_industry":   data.get("industry", ""),
            "detected_intent":       "unclear",
            "intent_signals":        [],
            "bot_risk_score":        rule_bot_score,
            "bot_risk_level":        risk_level,
            "bot_risk_reasons":      pre_flags,
            "lead_quality_score":    50,
            "red_flags":             pre_flags,
            "recommendation":        "review",
        }

    def _score_to_level(self, score: int) -> str:
        for level, cfg in BOT_THRESHOLDS.items():
            if score <= cfg["max"]:
                return level
        return "critical"

    # ------------------------------------------------------------------
    # Terminal display
    # ------------------------------------------------------------------

    def _display_lead(self, raw: dict, analysis: dict, pre_flags: list) -> None:
        intent_color = {"high": "green", "medium": "yellow", "low": "red", "unclear": "white"}.get(
            analysis.get("detected_intent", "unclear"), "white"
        )
        risk_level = analysis.get("bot_risk_level", "medium")
        risk_color = {"low": "green", "medium": "yellow", "high": "red", "critical": "bold red"}.get(
            risk_level, "yellow"
        )
        rec_color = {"accept": "green", "reject": "red", "review": "yellow"}.get(
            analysis.get("recommendation", "review"), "yellow"
        )
        quality     = analysis.get("lead_quality_score", 0)
        quality_bar = "█" * (quality // 10) + "░" * (10 - quality // 10)

        console.print()
        console.print(Panel(
            f"[bold]📋 NEW WEB FORM SUBMISSION[/bold]\n"
            f"[dim]Received at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
            f"| Sensitivity: {SENSITIVITY.upper()}[/dim]",
            box=box.DOUBLE_EDGE, style="cyan"
        ))

        # Contact table
        t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        t.add_column("Field",      style="dim",   width=20)
        t.add_column("Raw",        style="white", width=25)
        t.add_column("→",          style="dim",   width=2)
        t.add_column("Normalized", style="cyan",  width=30)

        t.add_row("Name",
            f"{raw.get('first_name','')} {raw.get('last_name','')}",
            "→",
            f"{analysis.get('normalized_first_name','')} {analysis.get('normalized_last_name','')}"
        )
        t.add_row("Email",    raw.get("email","—"),        "→", raw.get("email","—"))
        t.add_row("Company",  raw.get("company","—"),      "→", analysis.get("normalized_company","—"))
        t.add_row("Job Title",raw.get("job_title","—"),    "→", analysis.get("normalized_job_title","—"))
        t.add_row("Industry", raw.get("industry","—"),     "→", analysis.get("normalized_industry","—"))
        t.add_row("Size",     raw.get("company_size","—"), "→", raw.get("company_size","—"))
        console.print(t)

        if raw.get("message"):
            console.print(f"  [dim]Message:[/dim] [white]{raw['message'][:200]}[/white]\n")

        # Scores
        s = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        s.add_column("Metric", style="dim",   width=20)
        s.add_column("Value",  style="white", width=40)
        s.add_row("Lead Quality",    f"[cyan]{quality_bar}[/cyan] [bold]{quality}/100[/bold]")
        s.add_row("Purchase Intent", f"[{intent_color}]{analysis.get('detected_intent','—').upper()}[/{intent_color}]")
        s.add_row("Bot Risk",
            f"[{risk_color}]{risk_level.upper()}[/{risk_color}] ({analysis.get('bot_risk_score',0)}/100)"
        )
        s.add_row("Recommendation",  f"[{rec_color}]{analysis.get('recommendation','—').upper()}[/{rec_color}]")
        console.print(s)

        if analysis.get("intent_signals"):
            signals = " · ".join(f"[green]{sig}[/green]" for sig in analysis["intent_signals"])
            console.print(f"  [dim]Intent signals:[/dim] {signals}")

        all_flags = list(set(
            (analysis.get("red_flags") or []) +
            (analysis.get("bot_risk_reasons") or []) +
            pre_flags
        ))
        if all_flags:
            console.print(f"\n  [yellow]⚠ Flags ({SENSITIVITY} sensitivity):[/yellow]")
            for flag in all_flags:
                console.print(f"    [yellow]• {flag}[/yellow]")

        console.print()

    # ------------------------------------------------------------------
    # Human review with timeout
    # ------------------------------------------------------------------

    def _human_review(self, analysis: dict) -> bool:
        bot_risk   = analysis.get("bot_risk_score", 50)
        quality    = analysis.get("lead_quality_score", 50)
        rec        = analysis.get("recommendation", "review")
        rec_color  = {"accept": "green", "reject": "red", "review": "yellow"}.get(rec, "yellow")

        # Auto-reject above threshold
        if bot_risk >= AUTO_RULES["auto_reject_above_bot_risk"]:
            console.print(f"  [red]✗ Auto-rejected — bot risk {bot_risk}/100[/red]")
            return False

        # Auto-accept high quality + low risk
        if quality >= AUTO_RULES["auto_accept_above_quality"] and bot_risk <= 20:
            console.print(f"  [green]✓ Auto-accepted — quality {quality}/100, bot risk {bot_risk}/100[/green]")
            return True

        console.print(f"  Agent recommendation: [{rec_color}]{rec.upper()}[/{rec_color}]\n")

        user_input     = [None]
        input_received = threading.Event()

        def get_input():
            try:
                val = input(
                    f"  Process this lead? [y/n] "
                    f"(auto-accepts in {TIMEOUT_SECONDS}s): "
                ).strip().lower()
                user_input[0] = val
                input_received.set()
            except Exception:
                input_received.set()

        thread = threading.Thread(target=get_input, daemon=True)
        thread.start()

        for remaining in range(TIMEOUT_SECONDS, 0, -1):
            if input_received.wait(timeout=1):
                break
            if remaining % 10 == 0:
                console.print(
                    f"  [dim]Auto-accepting in {remaining}s...[/dim]",
                    end="\r"
                )

        if not input_received.is_set() or user_input[0] is None:
            console.print(f"\n  [yellow]⏱ No response — auto-accepted[/yellow]")
            return True

        if user_input[0] in ("y", "yes", ""):
            console.print(f"  [green]✓ Accepted by operator[/green]")
            return True
        else:
            console.print(f"  [red]✗ Rejected by operator[/red]")
            return False
