"""LLM client with Gemini primary, Groq fallback, caching, and rate limiting."""

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import settings
from app.core import observability as obs

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    model: str
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer"
    # Extra headers required by provider
    extra_headers: dict[str, str] = field(default_factory=dict)


GEMINI_CONFIG = ProviderConfig(
    name="gemini",
    base_url="https://generativelanguage.googleapis.com/v1beta",
    api_key=settings.gemini_api_key,
    model="gemini-2.5-flash",
    # Gemini uses query-param key, not Authorization header
    auth_header="x-goog-api-key",
    auth_prefix="",
)

GROQ_CONFIG = ProviderConfig(
    name="groq",
    base_url="https://api.groq.com/openai/v1",
    api_key=settings.groq_api_key,
    model="llama-3.3-70b-versatile",
)


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float


class LLMError(Exception):
    pass


# ---------------------------------------------------------------------------
# Response Cache — in-memory LRU with TTL
# ---------------------------------------------------------------------------

class _ResponseCache:
    """Simple in-memory LRU cache with TTL for non-streaming LLM responses."""

    def __init__(self, max_size: int = 256, ttl_seconds: float = 600.0) -> None:
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._store: OrderedDict[str, tuple[float, LLMResponse]] = OrderedDict()

    @staticmethod
    def _make_key(prompt: str, system_prompt: str, temperature: float, max_tokens: int) -> str:
        raw = f"{system_prompt}||{prompt}||{temperature}||{max_tokens}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, prompt: str, system_prompt: str, temperature: float, max_tokens: int) -> LLMResponse | None:
        key = self._make_key(prompt, system_prompt, temperature, max_tokens)
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, resp = entry
        if time.monotonic() - ts > self._ttl:
            del self._store[key]
            return None
        # Move to end (most recently used)
        self._store.move_to_end(key)
        logger.debug("Cache HIT for prompt hash %s…", key[:12])
        return resp

    def put(self, prompt: str, system_prompt: str, temperature: float, max_tokens: int, response: LLMResponse) -> None:
        # Only cache deterministic-ish responses (low temperature)
        if temperature > 0.2:
            return
        key = self._make_key(prompt, system_prompt, temperature, max_tokens)
        self._store[key] = (time.monotonic(), response)
        self._store.move_to_end(key)
        # Evict oldest if over capacity
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)


# ---------------------------------------------------------------------------
# Rate Limiter — token bucket for Gemini free tier (15 RPM)
# ---------------------------------------------------------------------------

class _RateLimiter:
    """Async token bucket rate limiter."""

    def __init__(self, max_rpm: int = 15) -> None:
        self._interval = 60.0 / max_rpm  # seconds between requests
        self._lock = asyncio.Lock()
        self._last_request: float = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < self._interval:
                wait = self._interval - elapsed
                logger.debug("Rate limiter: waiting %.1fs", wait)
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()


# ---------------------------------------------------------------------------
# Circuit Breaker — skip Gemini entirely after quota/auth errors
# ---------------------------------------------------------------------------

class _CircuitBreaker:
    """Skip a provider for a cooldown period after fatal errors (429, 401, 403)."""

    def __init__(self, cooldown_seconds: float = 60.0) -> None:
        self._cooldown = cooldown_seconds
        self._tripped_at: float = 0.0

    def trip(self) -> None:
        self._tripped_at = time.monotonic()
        logger.warning("Circuit breaker tripped — skipping provider for %.0fs", self._cooldown)

    def is_open(self) -> bool:
        if self._tripped_at == 0.0:
            return False
        if time.monotonic() - self._tripped_at > self._cooldown:
            self._tripped_at = 0.0  # Reset
            return False
        return True


# Module-level singletons
_cache = _ResponseCache()
_gemini_limiter = _RateLimiter(max_rpm=14)  # Stay safely under 15 RPM
_gemini_breaker = _CircuitBreaker(cooldown_seconds=60.0)


class LLMClient:
    """Async LLM client with Gemini primary, Groq fallback, caching, and rate limiting."""

    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 1.0  # seconds

    def __init__(self, timeout: float = 60.0) -> None:
        self._timeout = timeout

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Generate a response, trying cache first, then Gemini, then Groq."""
        # Check cache
        cached = _cache.get(prompt, system_prompt, temperature, max_tokens)
        if cached is not None:
            return cached

        for provider_cfg in (GEMINI_CONFIG, GROQ_CONFIG):
            if not provider_cfg.api_key:
                continue
            # Skip Gemini if circuit breaker is open (recent 429/auth failure)
            if provider_cfg.name == "gemini" and _gemini_breaker.is_open():
                logger.info("Skipping Gemini — circuit breaker open")
                continue
            try:
                resp = await self._generate_with_retry(
                    provider_cfg, prompt, system_prompt, temperature, max_tokens
                )
                _cache.put(prompt, system_prompt, temperature, max_tokens, resp)
                return resp
            except LLMError as exc:
                logger.warning("Provider %s failed: %s — trying next", provider_cfg.name, exc)

        raise LLMError("All providers failed.")

    async def _generate_with_retry(
        self,
        cfg: ProviderConfig,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        last_exc: Exception | None = None
        for attempt in range(self.MAX_RETRIES):
            try:
                return await self._call_provider(cfg, prompt, system_prompt, temperature, max_tokens)
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                # Don't retry on 429 (quota) or 401/403 (auth) — fail fast to next provider
                if exc.response.status_code in (401, 403, 429):
                    logger.warning("%s returned %d, skipping retries", cfg.name, exc.response.status_code)
                    if cfg.name == "gemini":
                        _gemini_breaker.trip()
                    break
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_BASE_DELAY * (2 ** attempt)
                    logger.debug("%s attempt %d failed, retrying in %.1fs: %s", cfg.name, attempt + 1, delay, exc)
                    await asyncio.sleep(delay)
            except (httpx.RequestError, LLMError) as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_BASE_DELAY * (2 ** attempt)
                    logger.debug("%s attempt %d failed, retrying in %.1fs: %s", cfg.name, attempt + 1, delay, exc)
                    await asyncio.sleep(delay)

        raise LLMError(f"{cfg.name} failed after {self.MAX_RETRIES} attempts: {last_exc}") from last_exc

    async def _call_provider(
        self,
        cfg: ProviderConfig,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        # Rate limit Gemini calls
        if cfg.name == "gemini":
            await _gemini_limiter.acquire()

        start = time.monotonic()

        if cfg.name == "gemini":
            response = await self._call_gemini(cfg, prompt, system_prompt, temperature, max_tokens)
        else:
            response = await self._call_openai_compat(cfg, prompt, system_prompt, temperature, max_tokens)

        latency_ms = (time.monotonic() - start) * 1000
        response.latency_ms = latency_ms

        self._log_response(response)
        obs.log_generation(
            provider=cfg.name,
            model=response.model,
            system_prompt=system_prompt,
            prompt=prompt,
            response=response.text,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.total_tokens,
            latency_ms=latency_ms,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response

    async def _call_gemini(
        self,
        cfg: ProviderConfig,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        url = f"{cfg.base_url}/models/{cfg.model}:generateContent"
        contents: list[dict[str, Any]] = [{"role": "user", "parts": [{"text": prompt}]}]
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        headers = {"x-goog-api-key": cfg.api_key, "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()

        data = resp.json()
        # Gemini 2.5+ may return parts without text (thinking tokens) — find first text part
        candidate_text = ""
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        for part in parts:
            if "text" in part:
                candidate_text = part["text"]
                break
        if not candidate_text:
            raise LLMError(f"Gemini returned no text. Response: {json.dumps(data)[:300]}")

        usage = data.get("usageMetadata", {})
        prompt_tokens = usage.get("promptTokenCount", 0)
        completion_tokens = usage.get("candidatesTokenCount", 0)

        return LLMResponse(
            text=candidate_text,
            provider=cfg.name,
            model=cfg.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            latency_ms=0.0,
        )

    async def _call_openai_compat(
        self,
        cfg: ProviderConfig,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        url = f"{cfg.base_url}/chat/completions"
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": cfg.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "frequency_penalty": 1.2,
        }
        headers = {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
            **cfg.extra_headers,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()

        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        return LLMResponse(
            text=text,
            provider=cfg.name,
            model=cfg.model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            latency_ms=0.0,
        )

    # ------------------------------------------------------------------
    # Streaming API
    # ------------------------------------------------------------------

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        """Yield response tokens.  Gemini → Groq streaming → non-streaming fallback."""
        for cfg, stream_method in [
            (GEMINI_CONFIG, self._stream_gemini_tokens),
            (GROQ_CONFIG, self._stream_groq_tokens),
        ]:
            if not cfg.api_key:
                continue
            # Skip Gemini if circuit breaker is open (recent 429/auth failure)
            if cfg.name == "gemini" and _gemini_breaker.is_open():
                logger.info("Skipping Gemini streaming — circuit breaker open")
                continue
            yielded = False
            accumulated: list[str] = []
            start = time.monotonic()
            try:
                # Rate limit Gemini streaming calls too
                if cfg.name == "gemini":
                    await _gemini_limiter.acquire()

                async for chunk in stream_method(cfg, prompt, system_prompt, temperature, max_tokens):
                    yield chunk
                    accumulated.append(chunk)
                    yielded = True
                obs.log_stream_generation(
                    provider=cfg.name,
                    model=cfg.model,
                    prompt=prompt,
                    response="".join(accumulated),
                    latency_ms=(time.monotonic() - start) * 1000,
                )
                return  # provider completed the stream successfully
            except httpx.HTTPStatusError as exc:
                # Trip circuit breaker on quota/auth errors
                if cfg.name == "gemini" and exc.response.status_code in (401, 403, 429):
                    _gemini_breaker.trip()
                logger.warning("%s streaming failed (HTTP %d): %s", cfg.name, exc.response.status_code, exc)
                if yielded:
                    obs.log_stream_generation(
                        provider=cfg.name, model=cfg.model, prompt=prompt,
                        response="".join(accumulated),
                        latency_ms=(time.monotonic() - start) * 1000,
                    )
                    return
            except Exception as exc:
                logger.warning("%s streaming failed: %s", cfg.name, exc)
                if yielded:
                    obs.log_stream_generation(
                        provider=cfg.name,
                        model=cfg.model,
                        prompt=prompt,
                        response="".join(accumulated),
                        latency_ms=(time.monotonic() - start) * 1000,
                    )
                    # Already sent partial output; can't cleanly switch providers
                    return

        # All streaming providers failed — fall back to a single non-streaming chunk
        # (generate() calls _call_provider which already logs via log_generation)
        try:
            resp = await self.generate(prompt, system_prompt, temperature, max_tokens)
            yield resp.text
        except Exception as exc:
            raise LLMError(f"All providers failed: {exc}") from exc

    async def _stream_gemini_tokens(
        self,
        cfg: ProviderConfig,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from Gemini using streamGenerateContent + alt=sse."""
        url = f"{cfg.base_url}/models/{cfg.model}:streamGenerateContent"
        contents: list[dict[str, Any]] = [{"role": "user", "parts": [{"text": prompt}]}]
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        headers = {"x-goog-api-key": cfg.api_key, "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST", url, json=body, headers=headers, params={"alt": "sse"}
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        data = json.loads(data_str)
                        # Gemini 2.5+ may have thinking parts without text
                        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                        for part in parts:
                            text = part.get("text", "")
                            if text:
                                yield text
                    except (KeyError, IndexError, json.JSONDecodeError):
                        continue

    async def _stream_groq_tokens(
        self,
        cfg: ProviderConfig,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from Groq (OpenAI-compatible SSE)."""
        url = f"{cfg.base_url}/chat/completions"
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        body: dict[str, Any] = {
            "model": cfg.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "frequency_penalty": 1.2,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
            **cfg.extra_headers,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream("POST", url, json=body, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0]["delta"].get("content") or ""
                        if delta:
                            yield delta
                    except (KeyError, IndexError, json.JSONDecodeError):
                        continue

    def _log_response(self, response: LLMResponse) -> None:
        logger.info(
            "LLM response | provider=%s model=%s tokens=%d latency=%.0fms",
            response.provider,
            response.model,
            response.total_tokens,
            response.latency_ms,
        )
