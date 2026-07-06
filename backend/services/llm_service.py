"""Pluggable LLM service.

Providers implement one method (``complete``) so swapping OpenAI / Anthropic /
Gemini is a config change, not a code change.  When no provider is configured
the service raises :class:`LLMUnavailableError` and callers fall back to their
deterministic heuristics — the app stays fully functional offline.
"""
from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from core.config import get_settings
from core.exceptions import LLMUnavailableError
from core.logging_config import get_logger

logger = get_logger("llm")


class LLMProvider(ABC):
    name: str = "base"
    model: str = ""
    last_usage: tuple[int, int] = (0, 0)  # (input_tokens, output_tokens) of last call

    @abstractmethod
    def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        """Return the assistant's text for a single-turn prompt."""


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        self._api_key = api_key
        self.model = model
        self._timeout = timeout

    def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        self.last_usage = (usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
        return data["choices"][0]["message"]["content"]


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        self._api_key = api_key
        self.model = model
        self._timeout = timeout

    def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": self.model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        self.last_usage = (usage.get("input_tokens", 0), usage.get("output_tokens", 0))
        return "".join(block.get("text", "") for block in data.get("content", []))


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        self._api_key = api_key
        self.model = model
        self._timeout = timeout

    def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self._api_key}"
        )
        resp = httpx.post(
            url,
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"maxOutputTokens": max_tokens},
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise LLMUnavailableError("Gemini returned no candidates")
        meta = data.get("usageMetadata", {})
        self.last_usage = (meta.get("promptTokenCount", 0), meta.get("candidatesTokenCount", 0))
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts)


class LLMService:
    """Front-door used by agents. Handles provider choice, retries and JSON parsing."""

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider
        self._settings = get_settings()

    # -- provider resolution -------------------------------------------------

    @property
    def provider(self) -> LLMProvider | None:
        if self._provider is None:
            self._provider = self._build_provider()
        return self._provider

    @property
    def available(self) -> bool:
        return self.provider is not None

    def _build_provider(self) -> LLMProvider | None:
        s = self._settings
        choice = s.llm_provider.lower().strip()
        builders = {
            "openai": lambda: OpenAIProvider(s.openai_api_key, s.openai_model, s.llm_timeout_seconds)
            if s.openai_api_key else None,
            "anthropic": lambda: AnthropicProvider(s.anthropic_api_key, s.anthropic_model, s.llm_timeout_seconds)
            if s.anthropic_api_key else None,
            "gemini": lambda: GeminiProvider(s.gemini_api_key, s.gemini_model, s.llm_timeout_seconds)
            if s.gemini_api_key else None,
        }
        if choice == "none":
            return None
        if choice in builders:
            provider = builders[choice]()
            if provider is None:
                logger.warning("LLM_PROVIDER=%s but its API key is missing", choice)
            return provider
        # auto: first configured provider wins
        for build in builders.values():
            provider = build()
            if provider is not None:
                logger.info("LLM provider auto-selected: %s", provider.name)
                return provider
        logger.warning("No LLM API key configured — running with heuristic fallbacks only")
        return None

    # -- calls ----------------------------------------------------------------

    def complete(self, system: str, user: str, *, max_tokens: int = 4096, op: str = "general") -> str:
        provider = self.provider
        if provider is None:
            raise LLMUnavailableError("No LLM provider configured")
        last_error: Exception | None = None
        for attempt in range(self._settings.llm_max_retries + 1):
            try:
                text = provider.complete(system, user, max_tokens=max_tokens)
                self._record_usage(provider, op)
                return text
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status = exc.response.status_code
                if status in (401, 403):
                    raise LLMUnavailableError(
                        f"{provider.name} rejected the API key (HTTP {status})"
                    ) from exc
                if status == 429 or status >= 500:
                    wait = 2 ** attempt
                    logger.warning("%s HTTP %s — retrying in %ss", provider.name, status, wait)
                    time.sleep(wait)
                    continue
                raise LLMUnavailableError(f"{provider.name} error: HTTP {status}") from exc
            except httpx.HTTPError as exc:
                last_error = exc
                time.sleep(2 ** attempt)
        raise LLMUnavailableError(f"{provider.name} unreachable: {last_error}")

    def complete_vision(self, system: str, user: str, image_b64: str,
                        mime: str = "image/png", *, max_tokens: int = 4096,
                        op: str = "vision") -> str:
        """Single-image vision completion (OpenAI only for now)."""
        provider = self.provider
        if provider is None or provider.name != "openai":
            raise LLMUnavailableError("Vision extraction requires an OpenAI provider")
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._settings.openai_api_key}"},
            json={
                "model": self._settings.openai_model,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": [
                        {"type": "text", "text": user},
                        {"type": "image_url",
                         "image_url": {"url": f"data:{mime};base64,{image_b64}", "detail": "high"}},
                    ]},
                ],
            },
            timeout=self._settings.llm_timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        provider.last_usage = (usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
        self._record_usage(provider, op)
        return data["choices"][0]["message"]["content"]

    def complete_json(self, system: str, user: str, *, max_tokens: int = 4096, op: str = "general") -> dict[str, Any]:
        """Request JSON output and parse it defensively."""
        text = self.complete(
            system + "\nRespond ONLY with valid JSON. No markdown fences, no commentary.",
            user,
            max_tokens=max_tokens,
            op=op,
        )
        return parse_json_loose(text)

    def _record_usage(self, provider: LLMProvider, op: str) -> None:
        try:
            from services.usage_tracker import record_usage

            input_tokens, output_tokens = provider.last_usage
            if input_tokens or output_tokens:
                record_usage(provider.name, provider.model, op, input_tokens, output_tokens)
        except Exception as exc:  # noqa: BLE001 - tracking must never break a call
            logger.debug("usage tracking skipped: %s", exc)


def parse_json_loose(text: str) -> dict[str, Any]:
    """Parse JSON out of LLM text that may include fences or prose."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


_service: LLMService | None = None


def get_llm() -> LLMService:
    global _service
    if _service is None:
        _service = LLMService()
    return _service


def reset_llm() -> None:
    global _service
    _service = None
