"""
Lead Gen Assistant - Pluggable LLM Client
Supports Anthropic Claude, OpenAI GPT, and Google Gemini.
Set LLM_PROVIDER and LLM_API_KEY in your .env file.

Usage:
    LLM_PROVIDER=anthropic  LLM_API_KEY=sk-ant-...
    LLM_PROVIDER=openai     LLM_API_KEY=sk-...
    LLM_PROVIDER=gemini     LLM_API_KEY=AIza...
"""

import os
import json
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Supported providers
ANTHROPIC = "anthropic"
OPENAI    = "openai"
GEMINI    = "gemini"

# Model defaults per provider — override via .env if needed
DEFAULT_MODELS = {
    ANTHROPIC: "claude-sonnet-4-20250514",
    OPENAI:    "gpt-4o",
    GEMINI:    "gemini-1.5-pro",
}


def get_provider() -> str:
    """Return the configured LLM provider. Defaults to anthropic."""
    provider = os.getenv("LLM_PROVIDER", ANTHROPIC).lower().strip()
    if provider not in (ANTHROPIC, OPENAI, GEMINI):
        raise ValueError(
            f"Unsupported LLM_PROVIDER: '{provider}'. "
            f"Choose from: anthropic, openai, gemini"
        )
    return provider


def get_model(provider: str) -> str:
    """Return the model to use for a given provider."""
    env_model = os.getenv("LLM_MODEL")
    if env_model:
        return env_model
    return DEFAULT_MODELS[provider]


def get_api_key(provider: str) -> str:
    """
    Return the API key for the given provider.
    Supports both unified LLM_API_KEY and provider-specific keys.
    """
    # Unified key takes priority
    unified = os.getenv("LLM_API_KEY")
    if unified:
        return unified

    # Provider-specific fallbacks
    key_map = {
        ANTHROPIC: "ANTHROPIC_API_KEY",
        OPENAI:    "OPENAI_API_KEY",
        GEMINI:    "GEMINI_API_KEY",
    }
    key = os.getenv(key_map[provider])
    if not key:
        raise ValueError(
            f"No API key found for provider '{provider}'. "
            f"Set LLM_API_KEY or {key_map[provider]} in your .env file."
        )
    return key


# ============================================================
# Unified LLM Response Format
# ============================================================

class LLMResponse:
    """
    Unified response object returned by all providers.
    Normalizes provider-specific formats into a single interface.
    """
    def __init__(self, text: str, tool_use: Optional[dict] = None, duration_ms: int = 0):
        self.text       = text
        self.tool_use   = tool_use   # {"name": str, "input": dict} or None
        self.duration_ms= duration_ms


# ============================================================
# Provider Implementations
# ============================================================

def _call_anthropic(
    system_prompt: str,
    user_message:  str,
    tools:         Optional[list],
    max_tokens:    int,
    model:         str,
    api_key:       str,
) -> LLMResponse:
    """Call Anthropic Claude API."""
    import anthropic
    import time

    client = anthropic.Anthropic(api_key=api_key)
    kwargs = {
        "model":      model,
        "max_tokens": max_tokens,
        "system":     system_prompt,
        "messages":   [{"role": "user", "content": user_message}],
    }
    if tools:
        kwargs["tools"] = tools

    start    = time.time()
    response = client.messages.create(**kwargs)
    elapsed  = int((time.time() - start) * 1000)

    text     = ""
    tool_use = None
    for block in response.content:
        if block.type == "text":
            text += block.text
        elif block.type == "tool_use":
            tool_use = {"name": block.name, "input": block.input}

    return LLMResponse(text=text, tool_use=tool_use, duration_ms=elapsed)


def _call_openai(
    system_prompt: str,
    user_message:  str,
    tools:         Optional[list],
    max_tokens:    int,
    model:         str,
    api_key:       str,
) -> LLMResponse:
    """Call OpenAI GPT API. Converts Anthropic tool format to OpenAI function format."""
    import openai
    import time

    client = openai.OpenAI(api_key=api_key)

    messages = [
        {"role": "system",  "content": system_prompt},
        {"role": "user",    "content": user_message},
    ]

    kwargs = {
        "model":      model,
        "max_tokens": max_tokens,
        "messages":   messages,
    }

    # Convert Anthropic tool schema → OpenAI function schema
    if tools:
        kwargs["tools"] = [
            {
                "type": "function",
                "function": {
                    "name":        t["name"],
                    "description": t.get("description", ""),
                    "parameters":  t["input_schema"],
                }
            }
            for t in tools
        ]
        kwargs["tool_choice"] = "required"

    start    = time.time()
    response = client.chat.completions.create(**kwargs)
    elapsed  = int((time.time() - start) * 1000)

    message  = response.choices[0].message
    text     = message.content or ""
    tool_use = None

    if message.tool_calls:
        tc = message.tool_calls[0]
        tool_use = {
            "name":  tc.function.name,
            "input": json.loads(tc.function.arguments),
        }

    return LLMResponse(text=text, tool_use=tool_use, duration_ms=elapsed)


def _call_gemini(
    system_prompt: str,
    user_message:  str,
    tools:         Optional[list],
    max_tokens:    int,
    model:         str,
    api_key:       str,
) -> LLMResponse:
    """Call Google Gemini API. Converts tool schemas to Gemini function declarations."""
    import time
    import google.generativeai as genai
    from google.generativeai.types import FunctionDeclaration, Tool

    genai.configure(api_key=api_key)

    # Build Gemini tool declarations
    gemini_tools = None
    if tools:
        declarations = []
        for t in tools:
            declarations.append(
                FunctionDeclaration(
                    name        = t["name"],
                    description = t.get("description", ""),
                    parameters  = t["input_schema"],
                )
            )
        gemini_tools = [Tool(function_declarations=declarations)]

    gemini_model = genai.GenerativeModel(
        model_name    = model,
        system_instruction = system_prompt,
        tools         = gemini_tools,
    )

    start    = time.time()
    response = gemini_model.generate_content(user_message)
    elapsed  = int((time.time() - start) * 1000)

    text     = ""
    tool_use = None

    for part in response.parts:
        if hasattr(part, "text") and part.text:
            text += part.text
        elif hasattr(part, "function_call") and part.function_call:
            fc = part.function_call
            tool_use = {
                "name":  fc.name,
                "input": dict(fc.args),
            }

    return LLMResponse(text=text, tool_use=tool_use, duration_ms=elapsed)


# ============================================================
# Main Entry Point
# ============================================================

def call_llm(
    system_prompt: str,
    user_message:  str,
    tools:         Optional[list] = None,
    max_tokens:    int = 2048,
) -> LLMResponse:
    """
    Unified LLM call. Routes to the configured provider automatically.

    Args:
        system_prompt: The system/role prompt for the agent
        user_message:  The user message or lead data to process
        tools:         Optional list of tool schemas (Anthropic format)
        max_tokens:    Maximum response tokens

    Returns:
        LLMResponse with .text and .tool_use attributes
    """
    provider = get_provider()
    model    = get_model(provider)
    api_key  = get_api_key(provider)

    if provider == ANTHROPIC:
        return _call_anthropic(system_prompt, user_message, tools, max_tokens, model, api_key)
    elif provider == OPENAI:
        return _call_openai(system_prompt, user_message, tools, max_tokens, model, api_key)
    elif provider == GEMINI:
        return _call_gemini(system_prompt, user_message, tools, max_tokens, model, api_key)


def get_provider_info() -> dict:
    """Return current provider configuration for display."""
    provider = get_provider()
    return {
        "provider": provider,
        "model":    get_model(provider),
        "key_set":  bool(get_api_key(provider)),
    }
