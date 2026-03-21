"""Tests for RAGPipeline — mock VectorStore and LLMClient throughout."""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.arabic_processor import ArabicProcessor, LexiconMatch
from app.core.llm_client import LLMResponse
from app.core.rag_pipeline import QueryBundle, RAGPipeline, RetrievalResult
from app.knowledge.vector_store import SearchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_search_result(
    chunk_id: str = "doc_0",
    text: str = "Chest pain assessment and ECG evaluation.",
    score: float = 0.85,
    category: str = "cardiovascular",
    source: str = "cardiology.txt",
) -> SearchResult:
    r = MagicMock(spec=SearchResult)
    r.chunk_id = chunk_id
    r.text = text
    r.score = score
    r.vector_score = score
    r.keyword_score = 0.0
    r.metadata = {
        "source_name": source,
        "medical_category": category,
        "section_title": "Chest Pain",
        "page_number": 1,
    }
    return r


def _make_llm_response(score_text: str = "0.9") -> LLMResponse:
    return LLMResponse(
        text=score_text,
        provider="gemini",
        model="gemini-1.5-flash",
        prompt_tokens=50,
        completion_tokens=2,
        total_tokens=52,
        latency_ms=100.0,
    )


def _make_symptom(latin: str = "waja3", msa: str = "ألم", english: str = "pain") -> LexiconMatch:
    return LexiconMatch(
        dialect_term="وجع",
        dialect_term_latin=latin,
        msa_equivalent=msa,
        english_medical_term=english,
        category="pain_descriptions",
        body_system="general",
        severity_hint="mild_to_moderate",
        matched_on="latin",
    )


def _mock_store(results: list[SearchResult] | None = None) -> MagicMock:
    store = MagicMock()
    store.search = AsyncMock(return_value=results or [_make_search_result()])
    store.count = MagicMock(return_value=10)
    return store


def _mock_llm(score: str = "0.9") -> MagicMock:
    llm = MagicMock()
    llm.generate = AsyncMock(return_value=_make_llm_response(score))
    return llm


def _make_pipeline(
    store=None,
    llm=None,
    proc=None,
    rerank: bool = False,
    top_k: int = 5,
    candidates_per_query: int = 8,
) -> RAGPipeline:
    return RAGPipeline(
        vector_store=store or _mock_store(),
        llm_client=llm or _mock_llm(),
        arabic_processor=proc or ArabicProcessor(),
        rerank=rerank,
        top_k=top_k,
        candidates_per_query=candidates_per_query,
    )


# ---------------------------------------------------------------------------
# QueryBundle
# ---------------------------------------------------------------------------

class TestQueryBundle:
    def test_all_queries_deduplicates(self):
        b = QueryBundle(original="waja3", msa="waja3", english="pain")
        queries = b.all_queries()
        assert queries.count("waja3") == 1

    def test_all_queries_preserves_unique(self):
        b = QueryBundle(original="3andi waja3", msa="ألم", english="pain / ache")
        assert len(b.all_queries()) == 3

    def test_all_queries_skips_empty(self):
        b = QueryBundle(original="test", msa="", english="pain")
        queries = b.all_queries()
        assert "" not in queries

    def test_all_queries_order(self):
        b = QueryBundle(original="orig", msa="msa", english="eng")
        assert b.all_queries()[0] == "orig"


# ---------------------------------------------------------------------------
# _build_query_bundle
# ---------------------------------------------------------------------------

class TestBuildQueryBundle:
    def test_original_preserved(self):
        pipe = _make_pipeline()
        b = pipe._build_query_bundle("3andi waja3 ras", [])
        assert b.original == "3andi waja3 ras"

    def test_msa_from_symptoms(self):
        pipe = _make_pipeline()
        symptoms = [_make_symptom(msa="ألم"), _make_symptom(latin="hammy", msa="حمى", english="fever")]
        b = pipe._build_query_bundle("test", symptoms)
        assert "ألم" in b.msa
        assert "حمى" in b.msa

    def test_english_from_symptoms(self):
        pipe = _make_pipeline()
        symptoms = [_make_symptom(english="pain / ache")]
        b = pipe._build_query_bundle("test", symptoms)
        assert "pain" in b.english

    def test_fallback_to_original_when_no_symptoms(self):
        pipe = _make_pipeline()
        b = pipe._build_query_bundle("chest pain", [])
        assert b.msa == "chest pain"
        assert b.english == "chest pain"

    def test_deduplicates_msa_terms(self):
        pipe = _make_pipeline()
        symptoms = [_make_symptom(msa="ألم"), _make_symptom(latin="waja3b", msa="ألم", english="pain")]
        b = pipe._build_query_bundle("test", symptoms)
        assert b.msa.count("ألم") == 1


# ---------------------------------------------------------------------------
# _multi_query_search
# ---------------------------------------------------------------------------

class TestMultiQuerySearch:
    @pytest.mark.asyncio
    async def test_calls_store_once_per_unique_query(self):
        store = _mock_store()
        pipe = _make_pipeline(store=store)
        bundle = QueryBundle(original="orig", msa="msa", english="eng")
        await pipe._multi_query_search(bundle, filters=None)
        assert store.search.call_count == 3

    @pytest.mark.asyncio
    async def test_deduplicates_by_chunk_id(self):
        r1 = _make_search_result(chunk_id="doc_0", score=0.7)
        r2 = _make_search_result(chunk_id="doc_0", score=0.9)  # same id, higher score
        r3 = _make_search_result(chunk_id="doc_1", score=0.5)
        store = MagicMock()
        store.search = AsyncMock(side_effect=[[r1], [r2], [r3]])
        pipe = _make_pipeline(store=store)
        bundle = QueryBundle(original="a", msa="b", english="c")
        results = await pipe._multi_query_search(bundle, filters=None)
        chunk_ids = [r.chunk_id for r in results]
        assert chunk_ids.count("doc_0") == 1

    @pytest.mark.asyncio
    async def test_keeps_best_score_on_dedup(self):
        r1 = _make_search_result(chunk_id="doc_0", score=0.6)
        r2 = _make_search_result(chunk_id="doc_0", score=0.95)
        store = MagicMock()
        store.search = AsyncMock(side_effect=[[r1], [r2], []])
        pipe = _make_pipeline(store=store)
        bundle = QueryBundle(original="a", msa="b", english="c")
        results = await pipe._multi_query_search(bundle, filters=None)
        assert results[0].score == 0.95

    @pytest.mark.asyncio
    async def test_sorted_by_score_desc(self):
        r1 = _make_search_result(chunk_id="doc_0", score=0.5)
        r2 = _make_search_result(chunk_id="doc_1", score=0.9)
        store = MagicMock()
        store.search = AsyncMock(return_value=[r1, r2])
        pipe = _make_pipeline(store=store)
        bundle = QueryBundle(original="a", msa="a", english="a")
        results = await pipe._multi_query_search(bundle, filters=None)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_passes_filters_to_store(self):
        store = _mock_store()
        pipe = _make_pipeline(store=store)
        bundle = QueryBundle(original="a", msa="b", english="c")
        await pipe._multi_query_search(bundle, filters={"medical_category": "cardiovascular"})
        for call in store.search.call_args_list:
            assert call.kwargs.get("filters") == {"medical_category": "cardiovascular"}


# ---------------------------------------------------------------------------
# Re-ranking
# ---------------------------------------------------------------------------

class TestReranking:
    @pytest.mark.asyncio
    async def test_rerank_score_blended_into_final(self):
        r = _make_search_result(score=0.6)
        llm = _mock_llm("0.8")
        pipe = _make_pipeline(llm=llm)
        result = await pipe._score_one("chest pain", r)
        expected = 0.3 * 0.6 + 0.7 * 0.8
        assert abs(result.relevance_score - expected) < 0.01

    @pytest.mark.asyncio
    async def test_rerank_score_clamped_to_zero_one(self):
        r = _make_search_result(score=0.5)
        llm = _mock_llm("1.5")  # out-of-range response
        pipe = _make_pipeline(llm=llm)
        result = await pipe._score_one("test", r)
        assert 0.0 <= result.rerank_score <= 1.0

    @pytest.mark.asyncio
    async def test_rerank_fallback_on_llm_error(self):
        r = _make_search_result(score=0.7)
        llm = MagicMock()
        llm.generate = AsyncMock(side_effect=Exception("LLM down"))
        pipe = _make_pipeline(llm=llm)
        result = await pipe._score_one("test", r)
        assert result.rerank_score == -1.0
        assert result.relevance_score == 0.7  # falls back to vector score

    @pytest.mark.asyncio
    async def test_rerank_fallback_on_non_numeric_response(self):
        r = _make_search_result(score=0.6)
        llm = _mock_llm("not_a_number")
        pipe = _make_pipeline(llm=llm)
        result = await pipe._score_one("test", r)
        assert result.rerank_score == -1.0


# ---------------------------------------------------------------------------
# retrieve() end-to-end
# ---------------------------------------------------------------------------

class TestRetrieve:
    @pytest.mark.asyncio
    async def test_returns_list_of_retrieval_results(self):
        pipe = _make_pipeline(rerank=False)
        results = await pipe.retrieve("waja3 ras")
        assert isinstance(results, list)
        assert all(isinstance(r, RetrievalResult) for r in results)

    @pytest.mark.asyncio
    async def test_respects_top_k(self):
        candidates = [_make_search_result(chunk_id=f"doc_{i}", score=0.9 - i * 0.05) for i in range(10)]
        store = _mock_store(candidates)
        pipe = _make_pipeline(store=store, rerank=False, top_k=3)
        results = await pipe.retrieve("chest pain")
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_empty_store_returns_empty(self):
        store = MagicMock()
        store.search = AsyncMock(return_value=[])  # always empty regardless of query
        pipe = _make_pipeline(store=store, rerank=False)
        results = await pipe.retrieve("waja3")
        assert results == []

    @pytest.mark.asyncio
    async def test_retrieval_result_fields_populated(self):
        pipe = _make_pipeline(rerank=False)
        results = await pipe.retrieve("chest pain")
        r = results[0]
        assert r.chunk_id
        assert r.chunk_text
        assert r.source
        assert 0.0 <= r.relevance_score <= 1.0
        assert r.medical_category
        assert isinstance(r.page_number, int)

    @pytest.mark.asyncio
    async def test_accepts_pre_extracted_symptoms(self):
        store = _mock_store()
        pipe = _make_pipeline(store=store, rerank=False)
        symptoms = [_make_symptom()]
        results = await pipe.retrieve("3andi waja3", symptoms=symptoms)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_to_dict_has_required_keys(self):
        pipe = _make_pipeline(rerank=False)
        results = await pipe.retrieve("pain")
        d = results[0].to_dict()
        for key in ("chunk_id", "chunk_text", "source", "relevance_score", "medical_category", "section_title"):
            assert key in d

    @pytest.mark.asyncio
    async def test_rerank_enabled_calls_llm(self):
        candidates = [_make_search_result(chunk_id=f"doc_{i}", score=0.9 - i * 0.05) for i in range(6)]
        store = _mock_store(candidates)
        llm = _mock_llm("0.8")
        pipe = _make_pipeline(store=store, llm=llm, rerank=True, top_k=3)
        results = await pipe.retrieve("chest pain")
        assert llm.generate.called
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_filters_passed_through(self):
        store = _mock_store()
        pipe = _make_pipeline(store=store, rerank=False)
        await pipe.retrieve("pain", filters={"medical_category": "respiratory"})
        for call in store.search.call_args_list:
            assert call.kwargs.get("filters") == {"medical_category": "respiratory"}

    @pytest.mark.asyncio
    async def test_results_sorted_by_relevance_desc(self):
        candidates = [_make_search_result(chunk_id=f"doc_{i}", score=0.5 + i * 0.1) for i in range(5)]
        store = _mock_store(candidates)
        pipe = _make_pipeline(store=store, rerank=False, top_k=5)
        results = await pipe.retrieve("chest pain")
        scores = [r.relevance_score for r in results]
        assert scores == sorted(scores, reverse=True)
