"""
Lead Gen Assistant - Base Agent
All agents inherit from this class for consistent Claude API usage
"""

import os
import json
import time
from typing import Optional
from abc import ABC, abstractmethod

import anthropic
from dotenv import load_dotenv
from rich.console import Console

from utils.databricks_client import DatabricksClient

load_dotenv()
console = Console()

CLAUDE_MODEL = "claude-sonnet-4-20250514"


class BaseAgent(ABC):
    """
    Base class for all Lead Gen Assistant agents.
    Provides shared Claude API client, Databricks client,
    and structured tool_use pattern.
    """

    VERSION = "1.0.0"

    def __init__(self, db_client: Optional[DatabricksClient] = None):
        self.anthropic = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        self.db = db_client or DatabricksClient()
        self.name = self.__class__.__name__

    def call_claude(
        self,
        system_prompt: str,
        user_message:  str,
        tools:         Optional[list] = None,
        max_tokens:    int = 2048,
    ) -> dict:
        """
        Call Claude API with optional tool_use.
        Returns the parsed response content.
        """
        kwargs = {
            "model":      CLAUDE_MODEL,
            "max_tokens": max_tokens,
            "system":     system_prompt,
            "messages":   [{"role": "user", "content": user_message}],
        }
        if tools:
            kwargs["tools"] = tools

        start = time.time()
        response = self.anthropic.messages.create(**kwargs)
        elapsed = int((time.time() - start) * 1000)

        # Extract text and tool_use blocks
        result = {"text": "", "tool_use": None, "duration_ms": elapsed}
        for block in response.content:
            if block.type == "text":
                result["text"] += block.text
            elif block.type == "tool_use":
                result["tool_use"] = {
                    "name":  block.name,
                    "input": block.input,
                }
        return result

    def log(self, message: str, style: str = "white") -> None:
        console.print(f"[{style}][{self.name}][/{style}] {message}")

    @abstractmethod
    def process(self, *args, **kwargs):
        """Each agent implements its own process() method."""
        pass
