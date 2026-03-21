"""ChromaDB-backed vector store with hybrid search.

Hybrid search combines:
  1. Vector similarity  — dense semantic matching via Gemini embeddings
  2. Keyword matching   — BM25-style term frequency on medical terms

The two scores are merged with a configurable alpha weight:
  final_score = alpha * vector_score + (1 - alpha) * keyword_score

Persistence: ChromaDB writes to disk at CHROMA_DIR so the collection
survives restarts without re-embedding.
"""

from __future__ import annotations

import logging
import math
import re
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.knowledge.embeddings import embed_batch, embed_query

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHROMA_DIR = Path(__file__).resolve().parents[2] / "chroma_db"
DEFAULT_COLLECTION = "hakim_medical"
# Weight for vector score in hybrid fusion (0=keyword only, 1=vector only)
DEFAULT_ALPHA = 0.7
# Medical domain stop-words (too common to be useful for keyword matching)
_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "as", "or", "and", "but",
    "not", "this", "that", "it", "its", "their", "they", "we", "our",
    "patient", "patients", "also", "used", "using", "based",
})


# ---------------------------------------------------------------------------
# SearchResult
# ---------------------------------------------------------------------------

class SearchResult:
    __slots__ = ("chunk_id", "text", "metadata", "vector_score", "keyword_score", "score")

    def __init__(
        self,
        chunk_id: str,
        text: str,
        metadata: dict[str, Any],
        vector_score: float,
        keyword_score: float = 0.0,
        alpha: float = DEFAULT_ALPHA,
    ) -> None:
        self.chunk_id = chunk_id
        self.text = text
        self.metadata = metadata
        self.vector_score = vector_score
        self.keyword_score = keyword_score
        self.score = alpha * vector_score + (1 - alpha) * keyword_score

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "metadata": self.metadata,
            "score": round(self.score, 4),
            "vector_score": round(self.vector_score, 4),
            "keyword_score": round(self.keyword_score, 4),
        }

    def __repr__(self) -> str:
        return f"SearchResult(chunk_id={self.chunk_id!r}, score={self.score:.4f})"


# ---------------------------------------------------------------------------
# Keyword scoring
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    return [
        w.lower()
        for w in re.findall(r"\b\w+\b", text)
        if w.lower() not in _STOP_WORDS and len(w) > 2
    ]


def _idf(term: str, corpus_texts: list[str]) -> float:
    """Simple IDF: log((N+1) / (df+1)) + 1."""
    n = len(corpus_texts)
    df = sum(1 for t in corpus_texts if term in t.lower())
    return math.log((n + 1) / (df + 1)) + 1.0


def _keyword_score(query: str, doc_text: str, corpus_texts: list[str]) -> float:
    """TF-IDF-style keyword relevance score, normalised to [0, 1]."""
    query_terms = _tokenize(query)
    if not query_terms:
        return 0.0

    doc_tokens = _tokenize(doc_text)
    doc_len = len(doc_tokens) or 1
    tf = {t: doc_tokens.count(t) / doc_len for t in set(doc_tokens)}

    score = 0.0
    for term in query_terms:
        score += tf.get(term, 0.0) * _idf(term, corpus_texts)

    # Normalise by query length so longer queries don't dominate
    return min(score / len(query_terms), 1.0)


# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------

class VectorStore:
    """Persistent ChromaDB vector store with hybrid search."""

    def __init__(
        self,
        collection_name: str = DEFAULT_COLLECTION,
        persist_dir: Path = CHROMA_DIR,
        alpha: float = DEFAULT_ALPHA,
    ) -> None:
        self._collection_name = collection_name
        self._alpha = alpha
        persist_dir.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "VectorStore ready: collection=%r persist_dir=%s count=%d",
            collection_name, persist_dir, self._collection.count(),
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def add_documents(self, chunks: list[dict[str, Any]]) -> int:
        """Embed and store a list of chunk dicts (output of ingest pipeline).

        Each chunk must have: chunk_id, text, and any metadata fields.
        Returns the number of documents added.
        """
        if not chunks:
            return 0

        texts = [c["text"] for c in chunks]
        ids = [c["chunk_id"] for c in chunks]

        logger.info("Embedding %d chunks ...", len(chunks))
        vectors = await embed_batch(texts)

        metadatas = [
            {
                "source_name": c.get("source_name", ""),
                "page_number": c.get("page_number", 0),
                "section_title": c.get("section_title", ""),
                "medical_category": c.get("medical_category", "general"),
                "token_count": c.get("token_count", 0),
                "char_start": c.get("char_start", 0),
                "char_end": c.get("char_end", 0),
            }
            for c in chunks
        ]

        self._collection.upsert(
            ids=ids,
            embeddings=vectors,
            documents=texts,
            metadatas=metadatas,
        )
        logger.info("Stored %d documents in collection %r", len(chunks), self._collection_name)
        return len(chunks)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
        alpha: float | None = None,
    ) -> list[SearchResult]:
        """Hybrid search: vector similarity + keyword scoring.

        Args:
            query:   Natural language query (Arabic, Franco-Arab, or English).
            top_k:   Number of results to return.
            filters: ChromaDB metadata filters, e.g. {"medical_category": "cardiovascular"}.
            alpha:   Override instance-level alpha weight (0=keyword, 1=vector).

        Returns:
            List of SearchResult sorted by descending hybrid score.
        """
        if self._collection.count() == 0:
            return []

        alpha = alpha if alpha is not None else self._alpha

        # Fetch more candidates than top_k so keyword re-ranking has material to work with
        n_candidates = min(top_k * 4, self._collection.count())

        query_vector = await embed_query(query)

        where = _build_where(filters) if filters else None
        query_kwargs: dict[str, Any] = {
            "query_embeddings": [query_vector],
            "n_results": n_candidates,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_kwargs["where"] = where

        raw = self._collection.query(**query_kwargs)

        ids: list[str] = raw["ids"][0]
        docs: list[str] = raw["documents"][0]
        metas: list[dict] = raw["metadatas"][0]
        distances: list[float] = raw["distances"][0]

        # Cosine distance → similarity score (ChromaDB returns distance, not similarity)
        # distance=0 → identical, distance=2 → opposite
        vector_scores = [max(0.0, 1.0 - d / 2.0) for d in distances]

        # Keyword re-rank against candidates only (not full corpus — too expensive)
        results: list[SearchResult] = []
        for chunk_id, text, meta, vscore in zip(ids, docs, metas, vector_scores):
            kscore = _keyword_score(query, text, docs)
            results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    text=text,
                    metadata=meta,
                    vector_score=vscore,
                    keyword_score=kscore,
                    alpha=alpha,
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def count(self) -> int:
        """Return number of documents in the collection."""
        return self._collection.count()

    def delete_collection(self) -> None:
        """Permanently delete the collection and all its data."""
        self._client.delete_collection(self._collection_name)
        logger.warning("Deleted collection %r", self._collection_name)
        # Re-create empty so the instance stays usable
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def get_collection_info(self) -> dict[str, Any]:
        return {
            "name": self._collection_name,
            "count": self._collection.count(),
            "persist_dir": str(CHROMA_DIR),
            "alpha": self._alpha,
        }


# ---------------------------------------------------------------------------
# Metadata filter builder
# ---------------------------------------------------------------------------

def _build_where(filters: dict[str, Any]) -> dict[str, Any]:
    """Convert a flat {field: value} dict to ChromaDB $and/$eq syntax."""
    if len(filters) == 1:
        field, value = next(iter(filters.items()))
        return {field: {"$eq": value}}
    return {"$and": [{field: {"$eq": value}} for field, value in filters.items()]}
