"""
Lead Gen Assistant - Base Agent
All agents inherit from this class.
Uses the pluggable LLM client — works with Anthropic, OpenAI, or Gemini.
"""

import time
from typing import Optional
from abc import ABC, abstractmethod

from rich.console import Console
from utils.llm_client import call_llm, get_provider_info, LLMResponse
from utils.databricks_client import DatabricksClient

console = Console()


class BaseAgent(ABC):
    """
    Base class for all Lead Gen Assistant agents.
    Provides shared LLM client (provider-agnostic) and Databricks client.
    """

    VERSION = "1.0.0"

    def __init__(self, db_client: Optional[DatabricksClient] = None):
        self.db   = db_client or DatabricksClient()
        self.name = self.__class__.__name__

        # Log which provider is active on first init
        info = get_provider_info()
        self.log(
            f"LLM Provider: [cyan]{info['provider']}[/cyan] "
            f"| Model: [yellow]{info['model']}[/yellow]"
        )

    def call_claude(
        self,
        system_prompt: str,
        user_message:  str,
        tools:         Optional[list] = None,
        max_tokens:    int = 2048,
    ) -> dict:
        """
        Call the configured LLM provider.
        Returns dict with text, tool_use, duration_ms for backward compatibility.
        """
        response: LLMResponse = call_llm(
            system_prompt = system_prompt,
            user_message  = user_message,
            tools         = tools,
            max_tokens    = max_tokens,
        )
        return {
            "text":        response.text,
            "tool_use":    response.tool_use,
            "duration_ms": response.duration_ms,
        }

    def log(self, message: str, style: str = "white") -> None:
        console.print(f"[{style}][{self.name}][/{style}] {message}")

    @abstractmethod
    def process(self, *args, **kwargs):
        pass
