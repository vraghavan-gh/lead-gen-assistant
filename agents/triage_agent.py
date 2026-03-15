"""
Lead Gen Assistant - Triage Agent
First agent in the pipeline. Evaluates raw leads and decides:
  - Accept → route to MQL Agent
  - Reject → log reason, end pipeline
  - Needs Review → flag for human
"""

import json
import time
from typing import Optional

from agents.base_agent import BaseAgent
from utils.models import RawLeadInput, TriageResult
from utils.databricks_client import DatabricksClient
from rich.console import Console

console = Console()


TRIAGE_SYSTEM_PROMPT = """
You are the Triage Agent for an enterprise Lead Generation Assistant pipeline.

Your job is to evaluate raw inbound leads from web forms and decide:
1. ACCEPT  - Lead is legitimate, has business potential, route to MQL Agent
2. REJECT  - Lead is spam, invalid, duplicate, or clearly unqualified
3. REVIEW  - Lead is borderline and needs a human to decide

Rejection criteria (use sparingly — when in doubt, accept):
- Missing email address
- Clearly fake data (test@test.com, asdf, 12345)
- Spam/bot signals in message field
- Personal email with no company name
- Obvious competitors (if detectable)
- Profanity or abusive content

You MUST use the triage_decision tool to return your structured decision.
Be concise in your reasoning — 1-2 sentences max.
"""

TRIAGE_TOOL = {
    "name": "triage_decision",
    "description": "Record the triage decision for this lead",
    "input_schema": {
        "type": "object",
        "properties": {
            "decision": {
                "type": "string",
                "enum": ["accepted", "rejected", "needs_review"],
                "description": "The triage decision"
            },
            "next_agent": {
                "type": "string",
                "enum": ["mql_agent", "human_review", "none"],
                "description": "Next agent or action"
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of the decision"
            },
            "rejection_reason": {
                "type": "string",
                "description": "Specific rejection category if rejected: invalid_email | spam | duplicate | incomplete_data | competitor | abusive"
            },
            "confidence": {
                "type": "number",
                "description": "Confidence score 0.0-1.0"
            }
        },
        "required": ["decision", "next_agent", "reasoning", "confidence"]
    }
}


class TriageAgent(BaseAgent):
    """
    Triage Agent — Entry point of the lead qualification pipeline.

    Responsibilities:
    - Validate lead data completeness
    - Detect spam, bots, and fake submissions
    - Route legitimate leads to MQL Agent
    - Log all decisions to Databricks lead_events table
    """

    def process(self, lead_input: RawLeadInput) -> TriageResult:
        """
        Process a raw lead through triage.

        Args:
            lead_input: RawLeadInput pydantic model from web form

        Returns:
            TriageResult with decision and routing
        """
        start_time = time.time()

        self.log(f"Processing lead from [cyan]{lead_input.email}[/cyan]")

        # 1. Store raw lead in Databricks
        lead_data = lead_input.model_dump()
        lead_id   = self.db.insert_raw_lead(lead_data)
        self.log(f"Stored raw lead → [yellow]{lead_id}[/yellow]")

        # Log capture event
        self.db.log_event(
            lead_id    = lead_id,
            event_type = "lead_captured",
            agent_name = self.name,
            to_status  = "new",
            details    = {"source": lead_input.source_channel, "form": lead_input.form_type}
        )

        # 2. Update status to processing
        self.db.update_lead_status(lead_id, "processing")
        self.db.log_event(
            lead_id    = lead_id,
            event_type = "triage_started",
            agent_name = self.name,
            from_status= "new",
            to_status  = "processing"
        )

        # 3. Call Claude for triage decision
        user_message = f"""
Evaluate this raw lead and make a triage decision:

Lead Data:
{json.dumps(lead_data, indent=2, default=str)}

Apply the triage rules and use the triage_decision tool to return your decision.
"""
        response = self.call_claude(
            system_prompt = TRIAGE_SYSTEM_PROMPT,
            user_message  = user_message,
            tools         = [TRIAGE_TOOL],
        )

        duration = int((time.time() - start_time) * 1000)

        # 4. Parse tool_use result
        if not response["tool_use"]:
            # Fallback if Claude didn't use tool
            decision_data = {
                "decision":         "needs_review",
                "next_agent":       "human_review",
                "reasoning":        "Agent did not return structured decision",
                "rejection_reason": None,
                "confidence":       0.5,
            }
        else:
            decision_data = response["tool_use"]["input"]

        triage_result = TriageResult(
            lead_id          = lead_id,
            decision         = decision_data["decision"],
            next_agent       = decision_data.get("next_agent"),
            reasoning        = decision_data["reasoning"],
            rejection_reason = decision_data.get("rejection_reason"),
            confidence       = decision_data.get("confidence", 0.8),
        )

        # 5. Update Databricks with triage outcome
        new_status = "accepted" if triage_result.decision == "accepted" else \
                     "rejected" if triage_result.decision == "rejected" else "processing"

        self.db.update_lead_status(
            lead_id,
            new_status,
            triage_result.rejection_reason
        )

        self.db.log_event(
            lead_id         = lead_id,
            event_type      = "triage_completed",
            agent_name      = self.name,
            from_status     = "processing",
            to_status       = new_status,
            details         = decision_data,
            duration_seconds= int(duration / 1000),
        )

        # 6. Console output
        status_color = "green" if triage_result.decision == "accepted" else \
                       "red"   if triage_result.decision == "rejected"  else "yellow"
        self.log(
            f"Decision: [{status_color}]{triage_result.decision.upper()}[/{status_color}] "
            f"— {triage_result.reasoning}"
        )

        return triage_result
