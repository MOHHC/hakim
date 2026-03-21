"""Gemini text-embedding-004 client.

Provides embed_text() and embed_batch() using Google's Generative Language
Embeddings API — free tier, 768-dimensional vectors, optimised for semantic
similarity and retrieval tasks.

API docs:
  https://ai.google.dev/api/embeddings#method:-models.embedcontent
"""

from __future__ import annotations

import asyncio
import logging
from typing import Sequence

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMBEDDING_MODEL = "text-embedding-004"
EMBEDDING_DIM = 768
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
# Gemini free tier: 100 embeddings/request max
_MAX_BATCH = 100


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_headers() -> dict[str, str]:
    return {
        "x-goog-api-key": settings.gemini_api_key,
        "Content-Type": "application/json",
    }


def _embed_url() -> str:
    return f"{_GEMINI_BASE}/models/{EMBEDDING_MODEL}:batchEmbedContents"


async def _post(client: httpx.AsyncClient, body: dict) -> dict:
    resp = await client.post(_embed_url(), json=body, headers=_build_headers())
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def embed_text(text: str, *, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
    """Embed a single text string. Returns a 768-dim float vector.

    task_type options:
      RETRIEVAL_DOCUMENT  — for indexing documents (default)
      RETRIEVAL_QUERY     — for embedding search queries
      SEMANTIC_SIMILARITY — for similarity comparison
    """
    vectors = await embed_batch([text], task_type=task_type)
    return vectors[0]


async def embed_batch(
    texts: Sequence[str],
    *,
    task_type: str = "RETRIEVAL_DOCUMENT",
    timeout: float = 60.0,
) -> list[list[float]]:
    """Embed a list of texts in efficient batches.

    Automatically splits into ≤100-item sub-batches (Gemini API limit).
    Returns vectors in the same order as the input.
    """
    if not texts:
        return []

    results: list[list[float]] = []
    chunks = [list(texts[i : i + _MAX_BATCH]) for i in range(0, len(texts), _MAX_BATCH)]

    async with httpx.AsyncClient(timeout=timeout) as client:
        for batch in chunks:
            body = {
                "requests": [
                    {
                        "model": f"models/{EMBEDDING_MODEL}",
                        "content": {"parts": [{"text": t}]},
                        "taskType": task_type,
                    }
                    for t in batch
                ]
            }
            logger.debug("Embedding batch of %d texts", len(batch))
            data = await _post(client, body)
            for item in data["embeddings"]:
                results.append(item["values"])

    logger.info("Embedded %d texts → %d-dim vectors", len(texts), EMBEDDING_DIM)
    return results


async def embed_query(query: str) -> list[float]:
    """Convenience wrapper for embedding a search query."""
    return await embed_text(query, task_type="RETRIEVAL_QUERY")
