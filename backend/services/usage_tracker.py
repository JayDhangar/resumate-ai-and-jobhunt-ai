"""LLM token-usage and cost tracking.

Every LLM call records its real token counts (as reported by the provider API)
into the document store, grouped by operation. Exposed via GET /api/usage.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from core.logging_config import get_logger
from services.storage import get_store

logger = get_logger("usage")

USAGE_DOC_ID = "llm-usage"
USAGE_COLLECTION = "usage"

# USD per 1M tokens (input, output)
PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
}

_lock = threading.Lock()


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    for known, (in_rate, out_rate) in PRICING_PER_MTOK.items():
        if model.startswith(known):
            return input_tokens / 1e6 * in_rate + output_tokens / 1e6 * out_rate
    return None


def record_usage(provider: str, model: str, op: str,
                 input_tokens: int, output_tokens: int) -> None:
    """Accumulate one call's usage into the persistent counters."""
    cost = _cost_usd(model, input_tokens, output_tokens)
    with _lock:
        store = get_store()
        doc: dict[str, Any] = store.get(USAGE_COLLECTION, USAGE_DOC_ID) or {
            "id": USAGE_DOC_ID,
            "since": datetime.now(timezone.utc).isoformat(),
            "totals": {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
            "by_operation": {},
        }
        for bucket in (doc["totals"], doc["by_operation"].setdefault(
            op, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
        )):
            bucket["calls"] += 1
            bucket["input_tokens"] += input_tokens
            bucket["output_tokens"] += output_tokens
            if cost is not None:
                bucket["cost_usd"] = round(bucket["cost_usd"] + cost, 6)
        doc["provider"] = provider
        doc["model"] = model
        doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        store.put(USAGE_COLLECTION, doc)
    logger.info("LLM call [%s] %s: %d in / %d out tokens (%s)",
                op, model, input_tokens, output_tokens,
                f"${cost:.6f}" if cost is not None else "unknown pricing")


def get_usage() -> dict[str, Any]:
    doc = get_store().get(USAGE_COLLECTION, USAGE_DOC_ID)
    if doc is None:
        return {"totals": {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
                "by_operation": {}, "since": None}
    return doc


def reset_usage() -> None:
    get_store().delete(USAGE_COLLECTION, USAGE_DOC_ID)
