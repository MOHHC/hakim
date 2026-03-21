"""RAG pipeline: multi-query retrieval + LLM-based re-ranking."""
from __future__ import annotations
import asyncio, logging
from dataclasses import dataclass, field
from typing import Any

from app.core.arabic_processor import ArabicProcessor, LexiconMatch
from app.core.llm_client import LLMClient
from app.knowledge.vector_store import SearchResult, VectorStore

logger = logging.getLogger(__name__)

_RERANK_PROMPT = """\
You are a medical relevance scorer. Rate how relevant the document chunk is \
to the user query on a scale from 0.0 to 1.0.
Respond with ONLY a single decimal number. No explanation.

Query: {query}

Document chunk:
{chunk}

Relevance score (0.0-1.0):"""

@dataclass
class RetrievalResult:
    chunk_id: str
    chunk_text: str
    source: str
    relevance_score: float
    medical_category: str
    section_title: str
    page_number: int
    vector_score: float
    rerank_score: float
    matched_queries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "chunk_text": self.chunk_text,
            "source": self.source,
            "relevance_score": round(self.relevance_score, 4),
            "medical_category": self.medical_category,
            "section_title": self.section_title,
            "page_number": self.page_number,
            "matched_queries": self.matched_queries,
        }

@dataclass
class QueryBundle:
    original: str
    msa: str
    english: str

    def all_queries(self) -> list[str]:
        seen: list[str] = []
        for q in (self.original, self.msa, self.english):
            if q and q not in seen:
                seen.append(q)
        return seen

class RAGPipeline:
    def __init__(
        self,
        vector_store: VectorStore,
        llm_client: LLMClient | None = None,
        arabic_processor: ArabicProcessor | None = None,
        candidates_per_query: int = 8,
        top_k: int = 5,
        rerank: bool = True,
    ) -> None:
        self._store = vector_store
        self._llm = llm_client or LLMClient()
        self._proc = arabic_processor or ArabicProcessor()
        self._candidates_per_query = candidates_per_query
        self._top_k = top_k
        self._rerank = rerank

    async def retrieve(
        self,
        query: str,
        symptoms: list[LexiconMatch] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        if symptoms is None:
            symptoms = self._proc.extract_symptoms(query)
        bundle = self._build_query_bundle(query, symptoms)
        logger.info("RAG queries: %s", bundle.all_queries())
        candidates = await self._multi_query_search(bundle, filters)
        if not candidates:
            return []
        if self._rerank and len(candidates) > self._top_k:
            results = await self._rerank_candidates(query, candidates)
        else:
            results = [self._to_retrieval(r, -1.0) for r in candidates]
            results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[: self._top_k]

    def _build_query_bundle(self, query: str, symptoms: list[LexiconMatch]) -> QueryBundle:
        original = query.strip()
        msa_terms = list(dict.fromkeys(m.msa_equivalent for m in symptoms if m.msa_equivalent))
        english_terms = list(dict.fromkeys(m.english_medical_term for m in symptoms if m.english_medical_term))
        return QueryBundle(
            original=original,
            msa=" ".join(msa_terms) if msa_terms else original,
            english=" ".join(english_terms) if english_terms else original,
        )

    async def _multi_query_search(
        self, bundle: QueryBundle, filters: dict[str, Any] | None
    ) -> list[SearchResult]:
        queries = bundle.all_queries()
        results_per_query: list[list[SearchResult]] = await asyncio.gather(*[
            self._store.search(q, top_k=self._candidates_per_query, filters=filters)
            for q in queries
        ])
        best: dict[str, SearchResult] = {}
        for results in results_per_query:
            for r in results:
                if r.chunk_id not in best or r.score > best[r.chunk_id].score:
                    best[r.chunk_id] = r
        deduped = sorted(best.values(), key=lambda r: r.score, reverse=True)
        logger.info("Retrieved %d unique candidates from %d queries", len(deduped), len(queries))
        return deduped

    async def _rerank_candidates(
        self, query: str, candidates: list[SearchResult]
    ) -> list[RetrievalResult]:
        scored = await asyncio.gather(*[self._score_one(query, c) for c in candidates])
        return sorted(scored, key=lambda r: r.relevance_score, reverse=True)

    async def _score_one(self, query: str, candidate: SearchResult) -> RetrievalResult:
        rerank_score = -1.0
        try:
            resp = await self._llm.generate(
                prompt=_RERANK_PROMPT.format(query=query, chunk=candidate.text[:800]),
                temperature=0.0,
                max_tokens=8,
            )
            rerank_score = max(0.0, min(1.0, float(resp.text.strip().split()[0])))
        except Exception as exc:
            logger.warning("Re-ranker failed for %s: %s", candidate.chunk_id, exc)
        final = (0.3 * candidate.score + 0.7 * rerank_score) if rerank_score >= 0 else candidate.score
        return self._to_retrieval(candidate, rerank_score, final)

    @staticmethod
    def _to_retrieval(r: SearchResult, rerank_score: float, final_score: float | None = None) -> RetrievalResult:
        meta = r.metadata
        return RetrievalResult(
            chunk_id=r.chunk_id,
            chunk_text=r.text,
            source=meta.get("source_name", ""),
            relevance_score=final_score if final_score is not None else r.score,
            medical_category=meta.get("medical_category", ""),
            section_title=meta.get("section_title", ""),
            page_number=meta.get("page_number", 0),
            vector_score=r.vector_score,
            rerank_score=rerank_score,
        )
