"""Integration tests for FastAPI routes.

All LLM / engine calls are mocked via app.dependency_overrides so no
real API keys or vector store are needed.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_safety_guardrails, get_triage_engine
from app.api.middleware.rate_limiter import _SlidingWindowLimiter
from app.core.safety_guardrails import GuardrailResult, SafetyGuardrails, ViolationType
from app.core.triage_engine import TriageEngine, TriageLevel, TriageResult
from app.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_triage_result(
    level: TriageLevel = TriageLevel.GREEN,
    response: str = "Rest and drink fluids.",
    conditions: list[str] | None = None,
    actions: list[str] | None = None,
    clarification: str | None = None,
    needs_clarification: bool = False,
) -> TriageResult:
    return TriageResult(
        triage_level=level,
        response_text=response,
        possible_conditions=conditions or ["viral infection"],
        recommended_actions=actions or ["rest", "hydrate"],
        sources=[],
        disclaimer="This is not medical advice.",
        needs_clarification=needs_clarification,
        clarification_question=clarification,
        total_tokens=100,
    )


async def _stream_from_result(result: TriageResult):
    """Async generator that mimics TriageEngine.triage_stream() output."""
    yield {
        "type": "triage_classified",
        "triage_level": result.triage_level.value,
        "possible_conditions": result.possible_conditions,
        "recommended_actions": result.recommended_actions,
        "needs_clarification": result.needs_clarification,
    }
    words = result.response_text.split()
    for i, word in enumerate(words):
        yield {"type": "chunk", "content": word + (" " if i < len(words) - 1 else "")}
    yield {
        "type": "complete",
        "triage_level": result.triage_level.value,
        "possible_conditions": result.possible_conditions,
        "recommended_actions": result.recommended_actions,
        "sources": result.sources,
        "disclaimer": result.disclaimer,
        "needs_clarification": result.needs_clarification,
        "follow_up_question": result.clarification_question,
    }


def _mock_engine(result: TriageResult) -> TriageEngine:
    engine = MagicMock(spec=TriageEngine)
    engine.triage = AsyncMock(return_value=result)
    engine.triage_stream = MagicMock(
        side_effect=lambda *a, **kw: _stream_from_result(result)
    )
    return engine


def _mock_guardrails(
    safe: bool = True, violation: ViolationType | None = None
) -> SafetyGuardrails:
    g = MagicMock(spec=SafetyGuardrails)
    if safe:
        g.check_query.return_value = GuardrailResult(is_safe=True)
    else:
        g.check_query.return_value = GuardrailResult(
            is_safe=False,
            violation_type=violation or ViolationType.SCOPE_INFANT,
            rejection_message="Cannot help with this case.",
            force_red=False,
        )
    g.check_response.return_value = GuardrailResult(is_safe=True)
    g.sanitize_response.side_effect = lambda text: text
    g.ensure_disclaimer.side_effect = lambda text, **kw: text
    g.is_emergency_violation.return_value = False
    return g


def _parse_sse_events(body: str) -> list[dict]:
    """Extract JSON payloads from a raw SSE body."""
    events = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data: ") and line[6:] != "[DONE]":
            events.append(json.loads(line[6:]))
    return events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset the module-level rate limiter before each test to prevent bleed."""
    from app.api.middleware.rate_limiter import default_limiter

    default_limiter.reset()


@pytest.fixture
async def client():
    """AsyncClient with clean dependency overrides."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


# ===========================================================================
# GET /api/health
# ===========================================================================


class TestHealth:
    @pytest.mark.asyncio
    async def test_returns_200(self, client):
        response = await client.get("/api/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_response_has_status_field(self, client):
        data = (await client.get("/api/health")).json()
        assert "status" in data
        assert data["status"] in ("ok", "degraded", "error")

    @pytest.mark.asyncio
    async def test_response_has_version(self, client):
        data = (await client.get("/api/health")).json()
        assert data["version"] == "0.1.0"

    @pytest.mark.asyncio
    async def test_response_has_timestamp(self, client):
        data = (await client.get("/api/health")).json()
        assert "timestamp" in data
        assert "T" in data["timestamp"]  # ISO 8601

    @pytest.mark.asyncio
    async def test_response_has_components(self, client):
        data = (await client.get("/api/health")).json()
        assert "components" in data
        assert isinstance(data["components"], dict)

    @pytest.mark.asyncio
    async def test_llm_component_present(self, client):
        data = (await client.get("/api/health")).json()
        assert "llm" in data["components"]

    @pytest.mark.asyncio
    async def test_arabic_processor_component_present(self, client):
        data = (await client.get("/api/health")).json()
        assert "arabic_processor" in data["components"]

    @pytest.mark.asyncio
    async def test_vector_store_component_present(self, client):
        data = (await client.get("/api/health")).json()
        assert "vector_store" in data["components"]

    @pytest.mark.asyncio
    async def test_each_component_has_status(self, client):
        data = (await client.get("/api/health")).json()
        for name, comp in data["components"].items():
            assert "status" in comp, f"component {name} missing 'status'"

    @pytest.mark.asyncio
    async def test_arabic_processor_has_entries_when_lexicon_loaded(self, client):
        data = (await client.get("/api/health")).json()
        proc_comp = data["components"]["arabic_processor"]
        if proc_comp["status"] == "ok":
            assert "entries" in proc_comp.get("detail", "")


# ===========================================================================
# POST /api/triage
# ===========================================================================


class TestTriageRoute:
    def _setup(self, result: TriageResult, safe: bool = True, violation=None):
        engine = _mock_engine(result)
        guardrails = _mock_guardrails(safe=safe, violation=violation)
        app.dependency_overrides[get_triage_engine] = lambda: engine
        app.dependency_overrides[get_safety_guardrails] = lambda: guardrails
        return engine, guardrails

    @pytest.mark.asyncio
    async def test_valid_request_returns_200(self, client):
        self._setup(_make_triage_result())
        resp = await client.post("/api/triage", json={"query": "I have a headache"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_triage_level_in_response(self, client):
        self._setup(_make_triage_result(TriageLevel.YELLOW))
        data = (
            await client.post("/api/triage", json={"query": "3andi waja3 ras"})
        ).json()
        assert data["triage_level"] == "YELLOW"

    @pytest.mark.asyncio
    async def test_response_has_required_fields(self, client):
        self._setup(_make_triage_result())
        data = (await client.post("/api/triage", json={"query": "chest pain"})).json()
        for key in (
            "triage_level",
            "response_text",
            "possible_conditions",
            "recommended_actions",
            "sources",
            "disclaimer",
            "needs_clarification",
            "clarification_question",
        ):
            assert key in data, f"missing field: {key}"

    @pytest.mark.asyncio
    async def test_green_triage(self, client):
        self._setup(_make_triage_result(TriageLevel.GREEN))
        data = (
            await client.post("/api/triage", json={"query": "mild headache"})
        ).json()
        assert data["triage_level"] == "GREEN"

    @pytest.mark.asyncio
    async def test_red_triage(self, client):
        self._setup(_make_triage_result(TriageLevel.RED, response="Go to ER now."))
        data = (
            await client.post("/api/triage", json={"query": "severe chest pain"})
        ).json()
        assert data["triage_level"] == "RED"

    @pytest.mark.asyncio
    async def test_blocked_query_returns_200(self, client):
        self._setup(
            _make_triage_result(), safe=False, violation=ViolationType.SCOPE_INFANT
        )
        resp = await client.post("/api/triage", json={"query": "my infant has fever"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_blocked_response_has_blocked_true(self, client):
        self._setup(
            _make_triage_result(), safe=False, violation=ViolationType.SCOPE_INFANT
        )
        data = (
            await client.post("/api/triage", json={"query": "my infant is sick"})
        ).json()
        assert data["blocked"] is True

    @pytest.mark.asyncio
    async def test_blocked_response_has_reason(self, client):
        self._setup(
            _make_triage_result(), safe=False, violation=ViolationType.SCOPE_PREGNANCY
        )
        data = (
            await client.post("/api/triage", json={"query": "pregnant with pain"})
        ).json()
        assert data["reason"] == ViolationType.SCOPE_PREGNANCY

    @pytest.mark.asyncio
    async def test_blocked_response_engine_not_called(self, client):
        engine, _ = self._setup(
            _make_triage_result(), safe=False, violation=ViolationType.SCOPE_LAB_RESULTS
        )
        await client.post("/api/triage", json={"query": "my lab results"})
        engine.triage.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_query_returns_422(self, client):
        resp = await client.post("/api/triage", json={"query": ""})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_query_returns_422(self, client):
        resp = await client.post("/api/triage", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_needs_clarification_field(self, client):
        self._setup(
            _make_triage_result(
                needs_clarification=True,
                clarification="When did this start?",
            )
        )
        data = (await client.post("/api/triage", json={"query": "pain"})).json()
        assert data["needs_clarification"] is True
        assert data["clarification_question"] == "When did this start?"

    @pytest.mark.asyncio
    async def test_sources_list_in_response(self, client):
        self._setup(_make_triage_result())
        data = (await client.post("/api/triage", json={"query": "headache"})).json()
        assert isinstance(data["sources"], list)


# ===========================================================================
# POST /api/chat (SSE)
# ===========================================================================


class TestChatRoute:
    def _setup(self, result: TriageResult, safe: bool = True, violation=None):
        engine = _mock_engine(result)
        guardrails = _mock_guardrails(safe=safe, violation=violation)
        app.dependency_overrides[get_triage_engine] = lambda: engine
        app.dependency_overrides[get_safety_guardrails] = lambda: guardrails

    @pytest.mark.asyncio
    async def test_returns_200(self, client):
        self._setup(_make_triage_result(response="Ok."))
        resp = await client.post("/api/chat", json={"message": "I have a headache"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_content_type_is_event_stream(self, client):
        self._setup(_make_triage_result(response="Ok."))
        resp = await client.post("/api/chat", json={"message": "headache"})
        assert "text/event-stream" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_stream_starts_with_start_event(self, client):
        self._setup(_make_triage_result(response="Ok."))
        resp = await client.post("/api/chat", json={"message": "headache"})
        events = _parse_sse_events(resp.text)
        assert events[0]["type"] == "start"

    @pytest.mark.asyncio
    async def test_stream_contains_chunk_events(self, client):
        self._setup(_make_triage_result(response="Rest and drink water."))
        resp = await client.post("/api/chat", json={"message": "headache"})
        events = _parse_sse_events(resp.text)
        chunk_events = [e for e in events if e["type"] == "chunk"]
        assert len(chunk_events) > 0

    @pytest.mark.asyncio
    async def test_chunk_events_reconstruct_response(self, client):
        self._setup(_make_triage_result(response="Rest and drink water."))
        resp = await client.post("/api/chat", json={"message": "headache"})
        events = _parse_sse_events(resp.text)
        reconstructed = "".join(e["content"] for e in events if e["type"] == "chunk")
        assert "Rest" in reconstructed
        assert "drink" in reconstructed

    @pytest.mark.asyncio
    async def test_stream_ends_with_complete_event(self, client):
        self._setup(_make_triage_result(response="Ok."))
        resp = await client.post("/api/chat", json={"message": "headache"})
        events = _parse_sse_events(resp.text)
        last_json_event = events[-1]
        assert last_json_event["type"] == "complete"

    @pytest.mark.asyncio
    async def test_complete_event_has_triage_level(self, client):
        self._setup(_make_triage_result(TriageLevel.YELLOW, response="See a doctor."))
        resp = await client.post("/api/chat", json={"message": "3andi waja3"})
        events = _parse_sse_events(resp.text)
        complete = next(e for e in events if e["type"] == "complete")
        assert complete["triage_level"] == "YELLOW"

    @pytest.mark.asyncio
    async def test_complete_event_has_disclaimer(self, client):
        self._setup(_make_triage_result(response="Ok."))
        resp = await client.post("/api/chat", json={"message": "headache"})
        events = _parse_sse_events(resp.text)
        complete = next(e for e in events if e["type"] == "complete")
        assert "disclaimer" in complete

    @pytest.mark.asyncio
    async def test_complete_event_has_sources(self, client):
        self._setup(_make_triage_result(response="Ok."))
        resp = await client.post("/api/chat", json={"message": "headache"})
        events = _parse_sse_events(resp.text)
        complete = next(e for e in events if e["type"] == "complete")
        assert "sources" in complete
        assert isinstance(complete["sources"], list)

    @pytest.mark.asyncio
    async def test_stream_body_ends_with_done(self, client):
        self._setup(_make_triage_result(response="Ok."))
        resp = await client.post("/api/chat", json={"message": "headache"})
        assert "[DONE]" in resp.text

    @pytest.mark.asyncio
    async def test_blocked_query_emits_blocked_event(self, client):
        self._setup(
            _make_triage_result(), safe=False, violation=ViolationType.SCOPE_INFANT
        )
        resp = await client.post("/api/chat", json={"message": "my infant has fever"})
        events = _parse_sse_events(resp.text)
        types = [e["type"] for e in events]
        assert "blocked" in types

    @pytest.mark.asyncio
    async def test_blocked_event_has_reason(self, client):
        self._setup(
            _make_triage_result(), safe=False, violation=ViolationType.SCOPE_PREGNANCY
        )
        resp = await client.post("/api/chat", json={"message": "pregnant with pain"})
        events = _parse_sse_events(resp.text)
        blocked = next(e for e in events if e["type"] == "blocked")
        assert blocked["reason"] == ViolationType.SCOPE_PREGNANCY

    @pytest.mark.asyncio
    async def test_blocked_stream_has_no_chunk_events(self, client):
        self._setup(
            _make_triage_result(), safe=False, violation=ViolationType.SCOPE_LAB_RESULTS
        )
        resp = await client.post("/api/chat", json={"message": "lab results"})
        events = _parse_sse_events(resp.text)
        assert not any(e["type"] == "chunk" for e in events)

    @pytest.mark.asyncio
    async def test_empty_message_returns_422(self, client):
        resp = await client.post("/api/chat", json={"message": ""})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_conversation_history_accepted(self, client):
        self._setup(_make_triage_result(response="Ok."))
        payload = {
            "message": "still hurts",
            "conversation_history": [
                {"role": "user", "content": "I have a headache"},
                {"role": "assistant", "content": "How long has it lasted?"},
            ],
        }
        resp = await client.post("/api/chat", json=payload)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_event_order_start_chunks_complete(self, client):
        self._setup(_make_triage_result(response="Rest at home."))
        resp = await client.post("/api/chat", json={"message": "mild fever"})
        events = _parse_sse_events(resp.text)
        types = [e["type"] for e in events]
        assert types[0] == "start"
        assert types[-1] == "complete"
        # All chunk events are between start and complete
        if "chunk" in types:
            first_chunk = types.index("chunk")
            last_chunk = len(types) - 1 - types[::-1].index("chunk")
            assert first_chunk > 0
            assert last_chunk < len(types) - 1


# ===========================================================================
# Rate limiter — unit tests for _SlidingWindowLimiter
# ===========================================================================


class TestSlidingWindowLimiter:
    @pytest.mark.asyncio
    async def test_first_request_allowed(self):
        lim = _SlidingWindowLimiter(max_requests=5, window_seconds=60)
        allowed, _ = await lim.check("1.2.3.4")
        assert allowed is True

    @pytest.mark.asyncio
    async def test_requests_within_limit_all_allowed(self):
        lim = _SlidingWindowLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            allowed, _ = await lim.check("1.2.3.4")
            assert allowed is True

    @pytest.mark.asyncio
    async def test_request_over_limit_denied(self):
        lim = _SlidingWindowLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            await lim.check("1.2.3.4")
        allowed, _ = await lim.check("1.2.3.4")
        assert allowed is False

    @pytest.mark.asyncio
    async def test_denied_returns_positive_retry_after(self):
        lim = _SlidingWindowLimiter(max_requests=2, window_seconds=60)
        await lim.check("1.2.3.4")
        await lim.check("1.2.3.4")
        _, retry_after = await lim.check("1.2.3.4")
        assert retry_after > 0

    @pytest.mark.asyncio
    async def test_different_ips_have_separate_limits(self):
        lim = _SlidingWindowLimiter(max_requests=2, window_seconds=60)
        for _ in range(2):
            await lim.check("1.1.1.1")
        # IP 1 is now at limit
        denied, _ = await lim.check("1.1.1.1")
        # IP 2 should still be allowed
        allowed, _ = await lim.check("2.2.2.2")
        assert denied is False
        assert allowed is True

    @pytest.mark.asyncio
    async def test_reset_clears_ip_counter(self):
        lim = _SlidingWindowLimiter(max_requests=2, window_seconds=60)
        for _ in range(2):
            await lim.check("1.2.3.4")
        lim.reset("1.2.3.4")
        allowed, _ = await lim.check("1.2.3.4")
        assert allowed is True

    @pytest.mark.asyncio
    async def test_reset_all_clears_all_ips(self):
        lim = _SlidingWindowLimiter(max_requests=1, window_seconds=60)
        await lim.check("1.1.1.1")
        await lim.check("2.2.2.2")
        lim.reset()
        allowed1, _ = await lim.check("1.1.1.1")
        allowed2, _ = await lim.check("2.2.2.2")
        assert allowed1 is True
        assert allowed2 is True


# ===========================================================================
# CORS headers
# ===========================================================================


class TestCORS:
    @pytest.mark.asyncio
    async def test_cors_header_on_health(self, client):
        resp = await client.get(
            "/api/health",
            headers={"Origin": "http://localhost:3000"},
        )
        assert "access-control-allow-origin" in resp.headers

    @pytest.mark.asyncio
    async def test_options_preflight_succeeds(self, client):
        resp = await client.options(
            "/api/chat",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        # Preflight should not return 429 or 403
        assert resp.status_code < 400
