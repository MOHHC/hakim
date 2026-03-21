"""Tests for embeddings.py and vector_store.py.

Embeddings tests mock the Gemini HTTP call (no API key needed).
VectorStore tests use a real in-memory ChromaDB with mocked embeddings.
"""

from __future__ import annotations

import math
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.knowledge.embeddings import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    _MAX_BATCH,
    embed_batch,
    embed_query,
    embed_text,
)
from app.knowledge.vector_store import (
    DEFAULT_ALPHA,
    SearchResult,
    VectorStore,
    _build_where,
    _keyword_score,
    _tokenize,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_vector(seed: int = 1) -> list[float]:
    """Returns a unit-length 768-dim vector seeded by an integer."""
    import random
    rng = random.Random(seed)
    v = [rng.gauss(0, 1) for _ in range(EMBEDDING_DIM)]
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def _gemini_embed_response(texts: list[str]) -> dict:
    return {"embeddings": [{"values": _fake_vector(i)} for i, _ in enumerate(texts)]}


def _mock_http_post(texts_per_call: int = 1):
    """Returns an AsyncMock that simulates the Gemini batchEmbedContents response."""
    async def _post(url, *, json=None, headers=None):
        n = len(json["requests"])
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = _gemini_embed_response([""] * n)
        return mock_resp

    return _post


def _make_store(tmp_path: Path, alpha: float = DEFAULT_ALPHA) -> VectorStore:
    return VectorStore(
        collection_name="test_collection",
        persist_dir=tmp_path / "chroma",
        alpha=alpha,
    )


def _make_chunks(n: int = 3) -> list[dict]:
    categories = ["cardiovascular", "respiratory", "digestive"]
    return [
        {
            "chunk_id": f"doc_{i}",
            "text": f"Sample medical text about {categories[i % len(categories)]} conditions chunk {i}.",
            "source_name": f"source_{i}.txt",
            "page_number": i,
            "section_title": f"Section {i}",
            "medical_category": categories[i % len(categories)],
            "token_count": 20 + i,
            "char_start": 0,
            "char_end": 100,
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# embeddings.py — unit tests
# ---------------------------------------------------------------------------

class TestEmbedText:
    @pytest.mark.asyncio
    async def test_returns_768_dim_vector(self):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_mock_http_post()):
            vector = await embed_text("chest pain")
        assert isinstance(vector, list)
        assert len(vector) == EMBEDDING_DIM

    @pytest.mark.asyncio
    async def test_returns_floats(self):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_mock_http_post()):
            vector = await embed_text("headache")
        assert all(isinstance(v, float) for v in vector)

    @pytest.mark.asyncio
    async def test_task_type_passed_in_request(self):
        captured = {}

        async def capture_post(url, *, json=None, headers=None):
            captured["body"] = json
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = _gemini_embed_response([""])
            return mock_resp

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=capture_post):
            await embed_text("test", task_type="RETRIEVAL_QUERY")

        assert captured["body"]["requests"][0]["taskType"] == "RETRIEVAL_QUERY"

    @pytest.mark.asyncio
    async def test_model_name_in_request(self):
        captured = {}

        async def capture_post(url, *, json=None, headers=None):
            captured["body"] = json
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = _gemini_embed_response([""])
            return mock_resp

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=capture_post):
            await embed_text("test")

        model = captured["body"]["requests"][0]["model"]
        assert EMBEDDING_MODEL in model


class TestEmbedBatch:
    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self):
        result = await embed_batch([])
        assert result == []

    @pytest.mark.asyncio
    async def test_batch_preserves_order(self):
        texts = [f"text {i}" for i in range(5)]
        call_count = 0

        async def ordered_post(url, *, json=None, headers=None):
            nonlocal call_count
            n = len(json["requests"])
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"embeddings": [{"values": _fake_vector(call_count * 100 + j)} for j in range(n)]}
            call_count += 1
            return mock_resp

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=ordered_post):
            vectors = await embed_batch(texts)

        assert len(vectors) == 5
        assert all(len(v) == EMBEDDING_DIM for v in vectors)

    @pytest.mark.asyncio
    async def test_large_batch_split_into_chunks(self):
        n = _MAX_BATCH + 10
        texts = [f"text {i}" for i in range(n)]
        post_calls = []

        async def counting_post(url, *, json=None, headers=None):
            post_calls.append(len(json["requests"]))
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = _gemini_embed_response([""] * len(json["requests"]))
            return mock_resp

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=counting_post):
            vectors = await embed_batch(texts)

        # Should have been split into 2 HTTP calls
        assert len(post_calls) == 2
        assert post_calls[0] == _MAX_BATCH
        assert post_calls[1] == 10
        assert len(vectors) == n

    @pytest.mark.asyncio
    async def test_single_text_batch(self):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_mock_http_post()):
            vectors = await embed_batch(["single text"])
        assert len(vectors) == 1
        assert len(vectors[0]) == EMBEDDING_DIM


class TestEmbedQuery:
    @pytest.mark.asyncio
    async def test_uses_retrieval_query_task_type(self):
        captured = {}

        async def capture_post(url, *, json=None, headers=None):
            captured["body"] = json
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = _gemini_embed_response([""])
            return mock_resp

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=capture_post):
            await embed_query("وجع بالصدر")

        assert captured["body"]["requests"][0]["taskType"] == "RETRIEVAL_QUERY"


# ---------------------------------------------------------------------------
# vector_store.py — keyword helpers
# ---------------------------------------------------------------------------

class TestTokenize:
    def test_removes_stop_words(self):
        tokens = _tokenize("the patient is in pain")
        assert "the" not in tokens
        assert "is" not in tokens
        assert "pain" in tokens

    def test_lowercases(self):
        tokens = _tokenize("Chest Pain Tachycardia")
        assert all(t == t.lower() for t in tokens)

    def test_filters_short_words(self):
        tokens = _tokenize("a is of in chest")
        assert all(len(t) > 2 for t in tokens)


class TestKeywordScore:
    def test_exact_match_scores_higher(self):
        corpus = ["chest pain assessment", "headache and dizziness", "nausea vomiting"]
        s1 = _keyword_score("chest pain", corpus[0], corpus)
        s2 = _keyword_score("chest pain", corpus[1], corpus)
        assert s1 > s2

    def test_no_match_returns_zero(self):
        corpus = ["cardiology notes"]
        s = _keyword_score("xyz123", corpus[0], corpus)
        assert s == 0.0

    def test_score_bounded_zero_to_one(self):
        corpus = ["chest pain chest pain chest pain chest pain"] * 5
        s = _keyword_score("chest pain", corpus[0], corpus)
        assert 0.0 <= s <= 1.0


# ---------------------------------------------------------------------------
# vector_store.py — _build_where
# ---------------------------------------------------------------------------

class TestBuildWhere:
    def test_single_filter(self):
        result = _build_where({"medical_category": "cardiovascular"})
        assert result == {"medical_category": {"$eq": "cardiovascular"}}

    def test_multiple_filters_use_and(self):
        result = _build_where({"medical_category": "respiratory", "page_number": 1})
        assert "$and" in result
        assert len(result["$and"]) == 2


# ---------------------------------------------------------------------------
# VectorStore — integration (real ChromaDB, mocked embeddings)
# ---------------------------------------------------------------------------

class TestVectorStore:
    @pytest.mark.asyncio
    async def test_add_documents_returns_count(self, tmp_path):
        store = _make_store(tmp_path)
        chunks = _make_chunks(3)
        with patch("app.knowledge.vector_store.embed_batch", new_callable=AsyncMock,
                   return_value=[_fake_vector(i) for i in range(3)]):
            n = await store.add_documents(chunks)
        assert n == 3

    @pytest.mark.asyncio
    async def test_count_after_add(self, tmp_path):
        store = _make_store(tmp_path)
        chunks = _make_chunks(5)
        with patch("app.knowledge.vector_store.embed_batch", new_callable=AsyncMock,
                   return_value=[_fake_vector(i) for i in range(5)]):
            await store.add_documents(chunks)
        assert store.count() == 5

    @pytest.mark.asyncio
    async def test_add_empty_returns_zero(self, tmp_path):
        store = _make_store(tmp_path)
        n = await store.add_documents([])
        assert n == 0

    @pytest.mark.asyncio
    async def test_search_returns_results(self, tmp_path):
        store = _make_store(tmp_path)
        chunks = _make_chunks(3)
        vectors = [_fake_vector(i) for i in range(3)]
        with patch("app.knowledge.vector_store.embed_batch", new_callable=AsyncMock, return_value=vectors):
            await store.add_documents(chunks)
        with patch("app.knowledge.vector_store.embed_query", new_callable=AsyncMock, return_value=_fake_vector(0)):
            results = await store.search("chest pain", top_k=2)
        assert len(results) <= 2
        assert all(isinstance(r, SearchResult) for r in results)

    @pytest.mark.asyncio
    async def test_search_empty_store_returns_empty(self, tmp_path):
        store = _make_store(tmp_path)
        with patch("app.knowledge.vector_store.embed_query", new_callable=AsyncMock, return_value=_fake_vector(0)):
            results = await store.search("test query")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_results_have_required_fields(self, tmp_path):
        store = _make_store(tmp_path)
        chunks = _make_chunks(3)
        vectors = [_fake_vector(i) for i in range(3)]
        with patch("app.knowledge.vector_store.embed_batch", new_callable=AsyncMock, return_value=vectors):
            await store.add_documents(chunks)
        with patch("app.knowledge.vector_store.embed_query", new_callable=AsyncMock, return_value=_fake_vector(0)):
            results = await store.search("medical conditions")
        for r in results:
            assert r.chunk_id
            assert r.text
            assert isinstance(r.metadata, dict)
            assert 0.0 <= r.score <= 1.0

    @pytest.mark.asyncio
    async def test_search_with_category_filter(self, tmp_path):
        store = _make_store(tmp_path)
        chunks = _make_chunks(6)
        vectors = [_fake_vector(i) for i in range(6)]
        with patch("app.knowledge.vector_store.embed_batch", new_callable=AsyncMock, return_value=vectors):
            await store.add_documents(chunks)
        with patch("app.knowledge.vector_store.embed_query", new_callable=AsyncMock, return_value=_fake_vector(0)):
            results = await store.search("pain", top_k=5, filters={"medical_category": "cardiovascular"})
        assert all(r.metadata["medical_category"] == "cardiovascular" for r in results)

    @pytest.mark.asyncio
    async def test_upsert_deduplicates_by_id(self, tmp_path):
        store = _make_store(tmp_path)
        chunks = _make_chunks(2)
        vectors = [_fake_vector(i) for i in range(2)]
        with patch("app.knowledge.vector_store.embed_batch", new_callable=AsyncMock, return_value=vectors):
            await store.add_documents(chunks)
            await store.add_documents(chunks)  # same IDs — upsert
        assert store.count() == 2  # not 4

    @pytest.mark.asyncio
    async def test_delete_collection_resets_count(self, tmp_path):
        store = _make_store(tmp_path)
        chunks = _make_chunks(3)
        vectors = [_fake_vector(i) for i in range(3)]
        with patch("app.knowledge.vector_store.embed_batch", new_callable=AsyncMock, return_value=vectors):
            await store.add_documents(chunks)
        assert store.count() == 3
        store.delete_collection()
        assert store.count() == 0

    @pytest.mark.asyncio
    async def test_hybrid_score_between_zero_and_one(self, tmp_path):
        store = _make_store(tmp_path)
        chunks = _make_chunks(3)
        vectors = [_fake_vector(i) for i in range(3)]
        with patch("app.knowledge.vector_store.embed_batch", new_callable=AsyncMock, return_value=vectors):
            await store.add_documents(chunks)
        with patch("app.knowledge.vector_store.embed_query", new_callable=AsyncMock, return_value=_fake_vector(0)):
            results = await store.search("medical conditions")
        for r in results:
            assert 0.0 <= r.vector_score <= 1.0
            assert 0.0 <= r.keyword_score <= 1.0
            assert 0.0 <= r.score <= 1.0

    def test_get_collection_info(self, tmp_path):
        store = _make_store(tmp_path)
        info = store.get_collection_info()
        assert info["name"] == "test_collection"
        assert info["count"] == 0
        assert "persist_dir" in info

    @pytest.mark.asyncio
    async def test_persistence_survives_reinit(self, tmp_path):
        """Documents added to one VectorStore instance are visible after reinit."""
        persist = tmp_path / "chroma"
        store1 = VectorStore("test_col", persist_dir=persist)
        chunks = _make_chunks(3)
        vectors = [_fake_vector(i) for i in range(3)]
        with patch("app.knowledge.vector_store.embed_batch", new_callable=AsyncMock, return_value=vectors):
            await store1.add_documents(chunks)

        # Re-open from same directory
        store2 = VectorStore("test_col", persist_dir=persist)
        assert store2.count() == 3
