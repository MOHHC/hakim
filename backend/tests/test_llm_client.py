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
)


@pytest.fixture(autouse=True)
def _fake_api_keys(monkeypatch):
    """Ensure provider configs have fake API keys so tests don't skip providers."""
    monkeypatch.setattr(GEMINI_CONFIG, "api_key", "fake-gemini-key")
    monkeypatch.setattr(GROQ_CONFIG, "api_key", "fake-groq-key")
    # Disable rate limiter so it doesn't inject extra sleeps into tests
    monkeypatch.setattr("app.core.llm_client._gemini_limiter.acquire", AsyncMock())


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
    cfg = ProviderConfig(name="test", base_url="https://api.test.com", api_key="key123", model="test-model")
    assert cfg.name == "test"
    assert cfg.base_url == "https://api.test.com"
    assert cfg.api_key == "key123"
    assert cfg.model == "test-model"
    assert cfg.extra_headers == {}


def test_provider_config_extra_headers():
    cfg = ProviderConfig(
        name="custom", base_url="https://x.com", api_key="k", model="m",
        extra_headers={"X-Custom": "value"}
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
    r = LLMResponse(text="hi", provider="gemini", model="m", prompt_tokens=5, completion_tokens=10, total_tokens=15, latency_ms=100.0)
    assert r.total_tokens == 15
    assert r.latency_ms == 100.0


# ---------------------------------------------------------------------------
# Successful Gemini call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_success_gemini():
    client = LLMClient()
    mock_resp = _mock_http_response(_gemini_response("hello world"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
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

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=fail_resp):
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

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=flaky_post):
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
            await client.generate("symptoms", system_prompt="You are a medical assistant.")

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

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=capture_post):
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
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_mock_http_response(resp_data)):
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
