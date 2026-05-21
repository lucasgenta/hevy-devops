"""Unified LLM provider interface with Deepseek support.

Deepseek uses an OpenAI-compatible API. We call it directly via httpx.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from hevy.env import load_dotenv

# Auto-load .env on module import so env vars are available everywhere
load_dotenv()

# ---------------------------------------------------------------------------
# Provider configs
# ---------------------------------------------------------------------------

PROVIDER_CONFIGS: dict[str, dict[str, Any]] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-v4-flash",
        "env_key": "DEEPSEEK_API_KEY",
        "description": "Deepseek (deepseek-v4-pro, deepseek-r1, etc.)",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "env_key": "OPENAI_API_KEY",
        "description": "OpenAI (GPT-4o, GPT-4o-mini, etc.)",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3",
        "env_key": None,  # no API key needed for local
        "description": "Local Ollama (llama3, mixtral, etc.)",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-sonnet-4-20250514",
        "env_key": "ANTHROPIC_API_KEY",
        "description": "Anthropic (Claude Sonnet 4, etc.)",
    },
}


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""

    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider:
    """Call LLM APIs via a unified interface.

    Usage::

        llm = LLMProvider("deepseek", api_key="sk-...")
        resp = llm.chat([
            {"role": "system", "content": "You are a coach."},
            {"role": "user", "content": "Analyze my training."},
        ])
        print(resp.content)
    """

    def __init__(
        self,
        provider: str = "deepseek",
        *,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> None:
        config = PROVIDER_CONFIGS.get(provider)
        if config is None:
            raise ValueError(
                f"Unknown provider '{provider}'. "
                f"Available: {list(PROVIDER_CONFIGS)}"
            )

        self.provider = provider
        self.base_url = config["base_url"]
        self.model = model or config["default_model"]
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Resolve API key: passed arg > env var
        env_key_name = config.get("env_key")
        self.api_key = api_key or (os.environ.get(env_key_name) if env_key_name else None)

        if config.get("env_key") and not self.api_key:
            raise ValueError(
                f"API key required for {provider}. "
                f"Set {config['env_key']} env var or pass api_key=."
            )

        self._client = httpx.Client(timeout=120.0)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send a chat completion request and return the response."""
        # Prepend system prompt if provided
        all_messages = list(messages)
        if system_prompt:
            all_messages.insert(0, {"role": "system", "content": system_prompt})

        body = {
            "model": self.model,
            "messages": all_messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "stream": False,
        }

        response = self._client.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=body,
        )

        if response.status_code == 401:
            raise PermissionError(
                f"Authentication failed for {self.provider}. Check your API key."
            )
        if response.status_code == 429:
            raise RuntimeError(f"Rate limited by {self.provider}. Try again later.")
        if not response.is_success:
            raise RuntimeError(
                f"{self.provider} API error ({response.status_code}): {response.text}"
            )

        data = response.json()
        choice = data["choices"][0]
        content = choice.get("message", {}).get("content", "")
        usage = data.get("usage", {})

        return LLMResponse(
            content=content,
            model=data.get("model", self.model),
            provider=self.provider,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            if self.provider == "anthropic":
                headers["x-api-key"] = self.api_key
                headers["anthropic-version"] = "2023-06-01"
            else:
                headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
