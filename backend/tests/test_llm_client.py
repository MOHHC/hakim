"""Tests for LLMClient."""

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.llm_client import (
    LLMClient,
    LLMError,
    LLMResponse,
    ProviderConfig,
    GEMINI_CONFIG,
    GROQ_CONFIG,
    _RateLimiter,
    _split_keys,
    _gemini_breaker,
)


@pytest.fixture(autouse=True)
def _fake_api_keys(monkeypatch):
    """Ensure provider configs have fake API keys so tests don't skip providers."""
    monkeypatch.setattr(GEMINI_CONFIG, "api_key", "fake-gemini-key")
    monkeypatch.setattr(GROQ_CONFIG, "api_key", "fake-groq-key")
    # Disable rate limiters so they don't inject extra sleeps into tests
    monkeypatch.setattr("app.core.llm_client._gemini_limiter.acquire", AsyncMock())
    monkeypatch.setattr("app.core.llm_client._groq_limiter.acquire", AsyncMock())
    # Reset circuit breaker so tests don't leak state
    _gemini_breaker._tripped_at = 0.0


def _gemini_response(text: str = "test response") -> dict:
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 20},
    }


def _groq_response(text: str = "groq response") -> dict:
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 8, "completion_tokens": 15, "total_tokens": 23},
    }


def _mock_http_response(json_data: dict, status_code: int = 200) -> MagicMock:
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status = MagicMock()
    if status_code >= 400:
        mock.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=mock
        )
    return mock


# ---------------------------------------------------------------------------
# ProviderConfig
# ---------------------------------------------------------------------------


def test_provider_config_fields():
    cfg = ProviderConfig(
        name="test",
        base_url="https://api.test.com",
        api_key="key123",
        model="test-model",
    )
    assert cfg.name == "test"
    assert cfg.base_url == "https://api.test.com"
    assert cfg.api_key == "key123"
    assert cfg.model == "test-model"
    assert cfg.extra_headers == {}


def test_provider_config_extra_headers():
    cfg = ProviderConfig(
        name="custom",
        base_url="https://x.com",
        api_key="k",
        model="m",
        extra_headers={"X-Custom": "value"},
    )
    assert cfg.extra_headers["X-Custom"] == "value"


def test_gemini_config_uses_api_key_header():
    assert GEMINI_CONFIG.auth_header == "x-goog-api-key"
    assert GEMINI_CONFIG.name == "gemini"


def test_groq_config_uses_bearer():
    assert GROQ_CONFIG.auth_prefix == "Bearer"
    assert GROQ_CONFIG.name == "groq"


# ---------------------------------------------------------------------------
# LLMResponse
# ---------------------------------------------------------------------------


def test_llm_response_total_tokens():
    r = LLMResponse(
        text="hi",
        provider="gemini",
        model="m",
        prompt_tokens=5,
        completion_tokens=10,
        total_tokens=15,
        latency_ms=100.0,
    )
    assert r.total_tokens == 15
    assert r.latency_ms == 100.0


# ---------------------------------------------------------------------------
# Successful Gemini call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_success_gemini():
    client = LLMClient()
    mock_resp = _mock_http_response(_gemini_response("hello world"))

    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp
    ):
        result = await client.generate("What hurts?")

    assert result.text == "hello world"
    assert result.provider == "gemini"
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 20
    assert result.total_tokens == 30
    assert result.latency_ms >= 0


# ---------------------------------------------------------------------------
# Fallback to Groq when Gemini fails
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_falls_back_to_groq_on_gemini_failure():
    client = LLMClient()
    gemini_fail = _mock_http_response({}, status_code=500)
    groq_ok = _mock_http_response(_groq_response("groq answer"))

    call_count = 0

    async def mock_post(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if "generativelanguage" in url:
            return gemini_fail
        return groq_ok

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=mock_post):
        result = await client.generate("chest pain")

    assert result.provider == "groq"
    assert result.text == "groq answer"


# ---------------------------------------------------------------------------
# All providers fail → LLMError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_raises_when_all_providers_fail():
    client = LLMClient()
    fail_resp = _mock_http_response({}, status_code=500)

    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=fail_resp
    ):
        with pytest.raises(LLMError, match="All providers failed"):
            await client.generate("test")


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retries_on_transient_error():
    client = LLMClient()
    call_count = 0
    ok_resp = _mock_http_response(_groq_response("ok"))

    async def flaky_post(url, **kwargs):
        nonlocal call_count
        call_count += 1
        # Fail Gemini twice, succeed on 3rd (still Gemini retry 3)
        if "generativelanguage" in url and call_count < 3:
            raise httpx.RequestError("timeout")
        if "generativelanguage" in url:
            return _mock_http_response(_gemini_response("recovered"))
        return ok_resp

    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=flaky_post
    ):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client.generate("headache")

    assert result.text == "recovered"
    assert result.provider == "gemini"


@pytest.mark.asyncio
async def test_exponential_backoff_delays():
    client = LLMClient()
    sleep_calls = []
    fail_resp = _mock_http_response({}, status_code=503)
    ok_groq = _mock_http_response(_groq_response("ok"))

    async def mock_post(url, **kwargs):
        if "generativelanguage" in url:
            return fail_resp
        return ok_groq

    async def mock_sleep(delay):
        sleep_calls.append(delay)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=mock_post):
        with patch("asyncio.sleep", side_effect=mock_sleep):
            await client.generate("test")

    # Gemini retries produce delays: 1.0, 2.0 (3 attempts = 2 sleeps)
    assert len(sleep_calls) == 2
    assert sleep_calls[0] == pytest.approx(1.0)
    assert sleep_calls[1] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# system_prompt and parameters passed correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_system_prompt_included_in_groq_request():
    client = LLMClient()
    captured_body = {}
    ok_resp = _mock_http_response(_groq_response())

    async def capture_post(url, json=None, **kwargs):
        nonlocal captured_body
        if "groq" in url:
            captured_body = json or {}
        return ok_resp

    # Force Gemini to fail so we hit Groq
    fail_resp = _mock_http_response({}, status_code=500)

    async def mock_post(url, **kwargs):
        if "generativelanguage" in url:
            return fail_resp
        return await capture_post(url, **kwargs)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=mock_post):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await client.generate(
                "symptoms", system_prompt="You are a medical assistant."
            )

    messages = captured_body.get("messages", [])
    roles = [m["role"] for m in messages]
    assert "system" in roles
    system_msg = next(m for m in messages if m["role"] == "system")
    assert "medical" in system_msg["content"]


@pytest.mark.asyncio
async def test_temperature_and_max_tokens_passed_to_gemini():
    client = LLMClient()
    captured_body = {}

    async def capture_post(url, json=None, **kwargs):
        nonlocal captured_body
        captured_body = json or {}
        return _mock_http_response(_gemini_response())

    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=capture_post
    ):
        await client.generate("test", temperature=0.7, max_tokens=512)

    gen_config = captured_body.get("generationConfig", {})
    assert gen_config["temperature"] == 0.7
    assert gen_config["maxOutputTokens"] == 512


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_counts_from_gemini():
    client = LLMClient()
    resp_data = {
        "candidates": [{"content": {"parts": [{"text": "answer"}]}}],
        "usageMetadata": {"promptTokenCount": 42, "candidatesTokenCount": 88},
    }
    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=_mock_http_response(resp_data),
    ):
        result = await client.generate("test")

    assert result.prompt_tokens == 42
    assert result.completion_tokens == 88
    assert result.total_tokens == 130


@pytest.mark.asyncio
async def test_token_counts_from_groq():
    client = LLMClient()
    fail_resp = _mock_http_response({}, status_code=500)
    groq_data = {
        "choices": [{"message": {"content": "answer"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 15, "total_tokens": 20},
    }

    async def mock_post(url, **kwargs):
        if "generativelanguage" in url:
            return fail_resp
        return _mock_http_response(groq_data)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=mock_post):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client.generate("test")

    assert result.prompt_tokens == 5
    assert result.completion_tokens == 15
    assert result.total_tokens == 20


# ---------------------------------------------------------------------------
# Rate limiting — client-side pacing must stay under each provider's free tier
# ---------------------------------------------------------------------------


def test_rate_limiter_interval_derives_from_rpm():
    assert _RateLimiter(max_rpm=10)._interval == pytest.approx(6.0)
    assert _RateLimiter(max_rpm=30)._interval == pytest.approx(2.0)


def test_rate_limiter_rejects_non_positive_rpm():
    with pytest.raises(ValueError):
        _RateLimiter(max_rpm=0)


@pytest.mark.asyncio
async def test_rate_limiter_paces_successive_acquires():
    limiter = _RateLimiter(max_rpm=60)  # 1s interval
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    with patch("asyncio.sleep", new=fake_sleep):
        await limiter.acquire()
        await limiter.acquire()

    # First acquire is free, second must wait out the interval.
    assert len(slept) == 1
    assert slept[0] > 0


@pytest.mark.asyncio
async def test_gemini_calls_are_rate_limited(monkeypatch):
    """Gemini is the primary provider and the one that 429s first in CI."""
    acquire = AsyncMock()
    monkeypatch.setattr("app.core.llm_client._gemini_limiter.acquire", acquire)
    client = LLMClient()

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=_mock_http_response(_gemini_response()),
    ):
        await client.generate("test")

    acquire.assert_awaited()


@pytest.mark.asyncio
async def test_groq_calls_are_rate_limited(monkeypatch):
    """Groq is the fallback; unpaced fallback traffic exhausted its quota too."""
    acquire = AsyncMock()
    monkeypatch.setattr("app.core.llm_client._groq_limiter.acquire", acquire)
    client = LLMClient()

    async def mock_post(url, **kwargs):
        if "generativelanguage" in url:
            return _mock_http_response({}, status_code=429)
        return _mock_http_response(_groq_response())

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=mock_post):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client.generate("test")

    assert result.provider == "groq"
    acquire.assert_awaited()


# ---------------------------------------------------------------------------
# Multi-key rotation — free-tier quota is per key, so spares extend a run
# ---------------------------------------------------------------------------


def test_split_keys_parses_a_single_key():
    assert _split_keys("only-key") == ("only-key", [])


def test_split_keys_parses_comma_separated_keys():
    assert _split_keys("first, second ,third") == ("first", ["second", "third"])


def test_split_keys_handles_empty_and_ragged_values():
    assert _split_keys("") == ("", [])
    assert _split_keys("  ") == ("", [])
    assert _split_keys("a,,b,") == ("a", ["b"])


def test_rotate_key_activates_each_spare_in_turn():
    cfg = ProviderConfig(
        name="groq",
        base_url="https://x",
        api_key="key-1",
        model="m",
        spare_keys=["key-2", "key-3"],
    )

    assert cfg.api_key == "key-1"
    assert cfg.rotate_key() is True
    assert cfg.api_key == "key-2"
    assert cfg.rotate_key() is True
    assert cfg.api_key == "key-3"
    # Every key tried — the provider is genuinely out.
    assert cfg.rotate_key() is False


def test_rotate_key_is_a_noop_without_spares():
    cfg = ProviderConfig(name="groq", base_url="https://x", api_key="solo", model="m")

    assert cfg.rotate_key() is False
    assert cfg.api_key == "solo"


def test_reset_key_rotation_allows_the_ring_to_be_walked_again():
    cfg = ProviderConfig(
        name="groq",
        base_url="https://x",
        api_key="key-1",
        model="m",
        spare_keys=["key-2"],
    )

    assert cfg.rotate_key() is True
    assert cfg.rotate_key() is False
    cfg.reset_key_rotation()
    # key-1 is back in the spare slot, so it can be tried again after a reset.
    assert cfg.rotate_key() is True
    assert cfg.api_key == "key-1"


@pytest.mark.asyncio
async def test_exhausted_groq_key_rotates_to_spare_instead_of_failing(monkeypatch):
    """The CI failure mode: Groq 429s, but a second key still has quota."""
    monkeypatch.setattr(GROQ_CONFIG, "spare_keys", ["groq-spare-key"])
    monkeypatch.setattr(GROQ_CONFIG, "_rotations", 0)
    monkeypatch.setattr(GEMINI_CONFIG, "api_key", "")  # force Groq to be used
    client = LLMClient()
    keys_seen: list[str] = []

    async def mock_post(url, **kwargs):
        keys_seen.append(kwargs["headers"]["Authorization"])
        if len(keys_seen) == 1:
            return _mock_http_response({}, status_code=429)
        return _mock_http_response(_groq_response("recovered on spare key"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=mock_post):
        result = await client.generate("chest pain")

    assert result.text == "recovered on spare key"
    assert keys_seen[0] != keys_seen[1], "must retry with a different credential"
    assert keys_seen[1] == "Bearer groq-spare-key"


@pytest.mark.asyncio
async def test_all_keys_exhausted_still_fails_cleanly(monkeypatch):
    monkeypatch.setattr(GROQ_CONFIG, "spare_keys", ["groq-spare-key"])
    monkeypatch.setattr(GROQ_CONFIG, "_rotations", 0)
    monkeypatch.setattr(GEMINI_CONFIG, "api_key", "")
    client = LLMClient()

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=_mock_http_response({}, status_code=429),
    ):
        with pytest.raises(LLMError, match="All providers failed"):
            await client.generate("chest pain")
