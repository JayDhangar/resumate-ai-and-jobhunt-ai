"""Text embeddings for RAG-style resume↔job matching.

Uses OpenAI ``text-embedding-3-small`` when an API key is configured
(cost: $0.02 per 1M tokens — a full match run costs ~$0.0005). Falls back to a
pure-Python TF-IDF cosine similarity so matching still works offline.
"""
from __future__ import annotations

import math
import re
from collections import Counter

import httpx

from core.config import get_settings
from core.logging_config import get_logger

logger = get_logger("embeddings")

EMBEDDING_MODEL = "text-embedding-3-small"
_WORD_RE = re.compile(r"[a-z][a-z0-9+#.]{1,}")

_STOPWORDS = frozenset(
    "the a an and or for with of in on at to from by is are was were be been as this that "
    "we you they it our your their will can may job work team role candidate experience "
    "years skills strong ability looking join us more have has had do does".split()
)


class EmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def available(self) -> bool:
        return bool(self.settings.openai_api_key)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Batch-embed texts via OpenAI; raises on failure (caller falls back)."""
        resp = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
            json={"model": EMBEDDING_MODEL, "input": [t[:8000] for t in texts]},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        try:
            from services.usage_tracker import record_usage

            record_usage("openai", EMBEDDING_MODEL, "job_match_embeddings",
                         usage.get("prompt_tokens", 0), 0)
        except Exception:  # noqa: BLE001
            pass
        return [item["embedding"] for item in data["data"]]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


# ------------------------------------------------------------- TF-IDF fallback

def _tokens(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS]


def tfidf_similarities(query_text: str, documents: list[str]) -> list[float]:
    """Cosine similarity between a query and each document (pure Python)."""
    docs_tokens = [_tokens(d) for d in documents]
    query_tokens = _tokens(query_text)
    all_docs = docs_tokens + [query_tokens]
    doc_freq: Counter[str] = Counter()
    for tokens in all_docs:
        doc_freq.update(set(tokens))
    n_docs = len(all_docs)

    def vectorize(tokens: list[str]) -> dict[str, float]:
        tf = Counter(tokens)
        total = len(tokens) or 1
        return {
            term: (count / total) * math.log(1 + n_docs / doc_freq[term])
            for term, count in tf.items()
        }

    query_vec = vectorize(query_tokens)
    query_norm = math.sqrt(sum(v * v for v in query_vec.values())) or 1.0
    sims: list[float] = []
    for tokens in docs_tokens:
        doc_vec = vectorize(tokens)
        dot = sum(query_vec.get(t, 0.0) * w for t, w in doc_vec.items())
        doc_norm = math.sqrt(sum(v * v for v in doc_vec.values())) or 1.0
        sims.append(dot / (query_norm * doc_norm))
    return sims


_service: EmbeddingService | None = None


def get_embedder() -> EmbeddingService:
    global _service
    if _service is None:
        _service = EmbeddingService()
    return _service
