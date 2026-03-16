"""
Lead Gen Assistant - Base Agent
All agents inherit from this class.
Uses the pluggable LLM client and LangGuard Policy Engine.
"""

import os
import time
from typing import Optional
from abc import ABC, abstractmethod

from rich.console import Console
from utils.llm_client import call_llm, get_provider_info, LLMResponse
from utils.databricks_client import DatabricksClient

console = Console()

# Load policy engine if LangGuard is enabled
LANGGUARD_ENABLED = os.getenv("LANGGUARD_ENABLED", "true").lower() == "true"

if LANGGUARD_ENABLED:
    from policy_packs.starter.enforcement.policy_engine import policy_engine
else:
    policy_engine = None


class BaseAgent(ABC):
    """
    Base class for all Lead Gen Assistant agents.
    Provides shared LLM client, Databricks client, and LangGuard policy hooks.
    """

    VERSION = "1.0.0"

    def __init__(self, db_client: Optional[DatabricksClient] = None):
        self.db           = db_client or DatabricksClient()
        self.name         = self.__class__.__name__
        self.policy_engine= policy_engine

        info = get_provider_info()
        self.log(
            f"LLM: [cyan]{info['provider']}[/cyan] / [yellow]{info['model']}[/yellow]"
            + (" | [green]🛡️ LangGuard ON[/green]" if LANGGUARD_ENABLED else "")
        )

    def call_claude(
        self,
        system_prompt: str,
        user_message:  str,
        tools:         Optional[list] = None,
        max_tokens:    int = 2048,
        lead_id:       Optional[str] = None,
        estimated_cost_usd: float = 0.05,
    ) -> dict:
        """
        Call the configured LLM provider.
        Runs spend_guard policy check before calling.
        Tracks tool call via tool_transparency policy.
        """
        # Policy: Spend Guard — check before LLM call
        if self.policy_engine and lead_id:
            result = self.policy_engine.check("spend_guard", {
                "lead_id":            lead_id,
                "agent":              self.name,
                "estimated_cost_usd": estimated_cost_usd,
            })
            if result.action == "deny":
                raise Exception(f"[LangGuard] Spend Guard blocked LLM call: {result.message}")

        # Policy: Tool Transparency — track LLM call
        start = time.time()
        if self.policy_engine and lead_id:
            with self.policy_engine.track_tool("claude_api", self.name, lead_id):
                response: LLMResponse = call_llm(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    tools=tools,
                    max_tokens=max_tokens,
                )
        else:
            response: LLMResponse = call_llm(
                system_prompt=system_prompt,
                user_message=user_message,
                tools=tools,
                max_tokens=max_tokens,
            )

        duration_ms = int((time.time() - start) * 1000)

        return {
            "text":        response.text,
            "tool_use":    response.tool_use,
            "duration_ms": duration_ms,
        }

    def db_read(self, query: str, params: Optional[list] = None,
                lead_id: Optional[str] = None) -> list:
        """Execute a DB read with tool transparency tracking."""
        if self.policy_engine and lead_id:
            with self.policy_engine.track_tool("databricks_read", self.name, lead_id):
                return self.db.execute(query, params)
        return self.db.execute(query, params)

    def db_write(self, query: str, params: Optional[list] = None,
                 lead_id: Optional[str] = None) -> list:
        """Execute a DB write with tool transparency tracking."""
        if self.policy_engine and lead_id:
            with self.policy_engine.track_tool("databricks_write", self.name, lead_id):
                return self.db.execute(query, params)
        return self.db.execute(query, params)

    def log_decision(self, lead_id: str, decision: str, reasoning: str,
                     confidence: float, duration_ms: int,
                     tokens_used: int = 0) -> None:
        """Log agent decision to LangGuard audit policy."""
        if self.policy_engine:
            self.policy_engine.check("decision_audit", {
                "lead_id":        lead_id,
                "agent":          self.name,
                "decision":       decision,
                "reasoning":      reasoning,
                "confidence_score": confidence,
                "duration_ms":    duration_ms,
                "tokens_used":    tokens_used,
                "agent_version":  self.VERSION,
            })

    def log(self, message: str, style: str = "white") -> None:
        console.print(f"[{style}][{self.name}][/{style}] {message}")

    @abstractmethod
    def process(self, *args, **kwargs):
        pass
