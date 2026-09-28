"""LLM client with Gemini primary, Groq fallback, caching, and rate limiting."""

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict, deque
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
    # Additional keys for the same provider, tried in order when the active one
    # runs out of quota.  Free-tier limits are per-key, so a spare key is often
    # the difference between a completed batch run and a half-empty report.
    spare_keys: list[str] = field(default_factory=list)
    # How many times we have already rotated; bounds the search.
    _rotations: int = field(default=0, repr=False)

    def rotate_key(self) -> bool:
        """Swap in the next spare key.  False once every key has been tried.

        Rotation cycles rather than discards: a key parked for a daily quota
        reset becomes usable again on the next run of a long-lived process.
        """
        if self._rotations >= len(self.spare_keys):
            return False
        exhausted, self.api_key = self.api_key, self.spare_keys[self._rotations]
        self.spare_keys[self._rotations] = exhausted
        self._rotations += 1
        return True

    def reset_key_rotation(self) -> None:
        """Allow the key ring to be walked again (e.g. after a cooldown)."""
        self._rotations = 0


def _split_keys(raw: str) -> tuple[str, list[str]]:
    """Split a comma-separated credential into (active key, spare keys)."""
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    return (keys[0] if keys else ""), keys[1:]


_gemini_key, _gemini_spares = _split_keys(settings.gemini_api_key)
_groq_key, _groq_spares = _split_keys(settings.groq_api_key)

GEMINI_CONFIG = ProviderConfig(
    name="gemini",
    base_url="https://generativelanguage.googleapis.com/v1beta",
    api_key=_gemini_key,
    model=settings.gemini_model,
    # Gemini uses query-param key, not Authorization header
    auth_header="x-goog-api-key",
    auth_prefix="",
    spare_keys=_gemini_spares,
)

GROQ_CONFIG = ProviderConfig(
    name="groq",
    base_url="https://api.groq.com/openai/v1",
    api_key=_groq_key,
    model=settings.groq_model,
    spare_keys=_groq_spares,
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
    def _make_key(
        prompt: str, system_prompt: str, temperature: float, max_tokens: int
    ) -> str:
        raw = f"{system_prompt}||{prompt}||{temperature}||{max_tokens}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(
        self, prompt: str, system_prompt: str, temperature: float, max_tokens: int
    ) -> LLMResponse | None:
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

    def put(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
        response: LLMResponse,
    ) -> None:
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
# Rate Limiter — client-side pacing to stay under provider free-tier limits
# ---------------------------------------------------------------------------


class _RateLimiter:
    """Async sliding-window limiter: at most ``max_rpm`` calls in any 60s.

    It used to space every call evenly (6s apart at 10 RPM), which put a fixed
    wait between the two calls a single chat reply makes even when the
    provider was nowhere near its limit.  A window allows that short burst and
    only waits once the per-minute budget is actually spent.
    """

    WINDOW_SECONDS = 60.0

    def __init__(self, max_rpm: int) -> None:
        if max_rpm <= 0:
            raise ValueError(f"max_rpm must be positive, got {max_rpm}")
        self._max = max_rpm
        self._lock = asyncio.Lock()
        self._calls: deque[float] = deque()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            while self._calls and now - self._calls[0] >= self.WINDOW_SECONDS:
                self._calls.popleft()
            if len(self._calls) >= self._max:
                wait = self.WINDOW_SECONDS - (now - self._calls[0])
                logger.debug("Rate limiter: waiting %.1fs", wait)
                await asyncio.sleep(wait)
                self._calls.popleft()
            self._calls.append(time.monotonic())


# ---------------------------------------------------------------------------
# Circuit Breaker — skip Gemini entirely after quota/auth errors
# ---------------------------------------------------------------------------


class _CircuitBreaker:
    """Skip a provider for a cooldown period after fatal errors (401/403/404/429)."""

    def __init__(self, cooldown_seconds: float = 60.0) -> None:
        self._cooldown = cooldown_seconds
        self._tripped_at: float = 0.0

    def trip(self) -> None:
        self._tripped_at = time.monotonic()
        logger.warning(
            "Circuit breaker tripped — skipping provider for %.0fs", self._cooldown
        )

    def is_open(self) -> bool:
        if self._tripped_at == 0.0:
            return False
        if time.monotonic() - self._tripped_at > self._cooldown:
            self._tripped_at = 0.0  # Reset
            return False
        return True


# Module-level singletons
#
# Pacing must stay *under* each provider's free-tier RPM, not near it: the old
# Gemini setting of 14 RPM sat above gemini-2.5-flash's free-tier ceiling of 10,
# so batch workloads (the eval suite) reliably 429'd about a minute in.  Groq had
# no limiter at all, so every fallback request went out unpaced.  Both are
# configurable because the ceilings differ per model and per billing tier.
_cache = _ResponseCache()
_gemini_limiter = _RateLimiter(max_rpm=settings.gemini_rpm)
_groq_limiter = _RateLimiter(max_rpm=settings.groq_rpm)
_gemini_breaker = _CircuitBreaker(cooldown_seconds=settings.provider_cooldown_seconds)
_groq_breaker = _CircuitBreaker(cooldown_seconds=settings.provider_cooldown_seconds)

# Key-level failures: the credential is rejected or out of quota.
_KEY_ERRORS = (401, 403, 429)
# Request-level failures that the same request will never get past, so retrying
# only adds latency to a user who is waiting on a reply.  404 usually means the
# model is retired or not enabled for the account, which is a config problem
# worth parking the provider for.
_NON_RETRYABLE = (400, 404, 422)


def _limiter_for(cfg: ProviderConfig) -> _RateLimiter:
    """Return the pacing limiter for a provider."""
    return _gemini_limiter if cfg.name == "gemini" else _groq_limiter


def _breaker_for(cfg: ProviderConfig) -> _CircuitBreaker:
    """Return the circuit breaker for a provider."""
    return _gemini_breaker if cfg.name == "gemini" else _groq_breaker


def _provider_order() -> tuple[ProviderConfig, ProviderConfig]:
    """Providers in the order they are tried (settings.llm_primary first)."""
    if settings.llm_primary.strip().lower() == "gemini":
        return (GEMINI_CONFIG, GROQ_CONFIG)
    return (GROQ_CONFIG, GEMINI_CONFIG)


def _gemini_generation_config(temperature: float, max_tokens: int) -> dict[str, Any]:
    config: dict[str, Any] = {"temperature": temperature, "maxOutputTokens": max_tokens}
    if settings.gemini_thinking_level:
        config["thinkingConfig"] = {"thinkingLevel": settings.gemini_thinking_level}
    return config


def _error_detail(exc: httpx.HTTPStatusError) -> str:
    """Best-effort snippet of the provider's error body, for the logs.

    Provider error bodies name the actual cause ("model not found", "API key
    expired") where the status code alone does not.
    """
    try:
        return exc.response.text[:300]
    except Exception:  # streamed bodies may not have been read
        return ""


@dataclass
class ProviderStatus:
    ok: bool
    detail: str


_probe_cache: tuple[float, dict[str, ProviderStatus]] | None = None
_PROBE_TTL_SECONDS = 300.0


async def probe_providers(force: bool = False) -> dict[str, ProviderStatus]:
    """Check each configured provider with a tiny real generation request.

    Having a key set says nothing about whether it works (a revoked key once
    left chat fully down while health reported "ok"), and neither does looking
    the model up: Google kept listing gemini-2.5-flash while refusing to
    generate with it for new projects.  So this asks for a one-word reply, the
    same call chat makes.  Results are cached for five minutes so health checks
    barely touch free-tier quotas.
    """
    global _probe_cache
    now = time.monotonic()
    if not force and _probe_cache and now - _probe_cache[0] < _PROBE_TTL_SECONDS:
        return _probe_cache[1]

    results: dict[str, ProviderStatus] = {}
    ping = "Reply with the single word: ok"
    async with httpx.AsyncClient(timeout=15.0) as client:
        for cfg in (GEMINI_CONFIG, GROQ_CONFIG):
            if not cfg.api_key:
                results[cfg.name] = ProviderStatus(False, "no API key configured")
                continue
            if cfg.name == "gemini":
                url = f"{cfg.base_url}/models/{cfg.model}:generateContent"
                headers = {"x-goog-api-key": cfg.api_key}
                body: dict[str, Any] = {
                    "contents": [{"role": "user", "parts": [{"text": ping}]}],
                    "generationConfig": _gemini_generation_config(0.0, 20),
                }
            else:
                url = f"{cfg.base_url}/chat/completions"
                headers = {"Authorization": f"Bearer {cfg.api_key}"}
                body = {
                    "model": cfg.model,
                    "messages": [{"role": "user", "content": ping}],
                    "max_tokens": 20,
                }
            start = time.monotonic()
            try:
                resp = await client.post(url, headers=headers, json=body)
            except httpx.RequestError as exc:
                results[cfg.name] = ProviderStatus(False, f"unreachable: {exc}"[:120])
                continue
            if resp.status_code == 200:
                ms = (time.monotonic() - start) * 1000
                results[cfg.name] = ProviderStatus(
                    True, f"{cfg.model} answered in {ms:.0f} ms"
                )
            else:
                results[cfg.name] = ProviderStatus(
                    False, f"{cfg.model}: HTTP {resp.status_code} {resp.text[:120]}"
                )

    _probe_cache = (now, results)
    return results


class LLMClient:
    """Async LLM client with Gemini primary, Groq fallback, caching, and rate limiting."""

    MAX_RETRIES = 3
    # Attempts for a provider that still has a fallback behind it.  The patient
    # is waiting: one retry covers a blip, and anything longer is better spent
    # on the fallback, which answers in a few seconds.
    MAX_RETRIES_WITH_FALLBACK = 2
    RETRY_BASE_DELAY = 1.0  # seconds

    def __init__(self, timeout: float = 12.0) -> None:
        # A short connect timeout finds an unreachable provider quickly; the read
        # timeout bounds a hung one (it applies between streamed chunks too).
        self._timeout = httpx.Timeout(timeout, connect=5.0)

    @staticmethod
    def _has_fallback_after(cfg: ProviderConfig) -> bool:
        """True when a later provider could still answer if this one fails."""
        order = _provider_order()
        later = order[order.index(cfg) + 1 :] if cfg in order else ()
        return any(p.api_key and not _breaker_for(p).is_open() for p in later)

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

        for provider_cfg in _provider_order():
            if not provider_cfg.api_key:
                continue
            # Skip a provider whose circuit breaker is open (recent fatal error)
            if _breaker_for(provider_cfg).is_open():
                logger.info("Skipping %s — circuit breaker open", provider_cfg.name)
                continue
            try:
                resp = await self._generate_with_retry(
                    provider_cfg, prompt, system_prompt, temperature, max_tokens
                )
                _cache.put(prompt, system_prompt, temperature, max_tokens, resp)
                return resp
            except LLMError as exc:
                logger.warning(
                    "Provider %s failed: %s — trying next", provider_cfg.name, exc
                )

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
        attempt = 0
        has_fallback = self._has_fallback_after(cfg)
        max_attempts = (
            self.MAX_RETRIES_WITH_FALLBACK if has_fallback else self.MAX_RETRIES
        )
        while attempt < max_attempts:
            try:
                return await self._call_provider(
                    cfg, prompt, system_prompt, temperature, max_tokens
                )
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                # 429 (quota) and 401/403 (auth) are properties of the *key*, not
                # the request, so retrying the same credential is pointless — but
                # a spare key for the same provider may still have budget.
                status = exc.response.status_code
                if status in _KEY_ERRORS:
                    if cfg.rotate_key():
                        logger.warning(
                            "%s key rejected (%d) — switching to spare key",
                            cfg.name,
                            status,
                        )
                        continue  # different credential, so not a retry
                    logger.error(
                        "%s returned %d and has no spare keys left, skipping retries: %s",
                        cfg.name,
                        status,
                        _error_detail(exc),
                    )
                    _breaker_for(cfg).trip()
                    break
                if status in _NON_RETRYABLE:
                    logger.error(
                        "%s rejected the request (%d, model=%s), not retrying: %s",
                        cfg.name,
                        status,
                        cfg.model,
                        _error_detail(exc),
                    )
                    if status == 404:
                        _breaker_for(cfg).trip()
                    break
                attempt += 1
                await self._backoff(cfg, attempt, exc, max_attempts)
            except (httpx.RequestError, LLMError) as exc:
                last_exc = exc
                # A timed-out provider is likely to time out again; with a
                # fallback available, waiting another full timeout on it is
                # the slowest possible way to answer.
                if has_fallback and isinstance(exc, httpx.TimeoutException):
                    logger.warning("%s timed out, switching to fallback", cfg.name)
                    break
                attempt += 1
                await self._backoff(cfg, attempt, exc, max_attempts)

        if has_fallback:
            # Park it so the rest of this reply (and the next few) go straight
            # to the fallback instead of re-paying the failure.
            _breaker_for(cfg).trip()
        raise LLMError(f"{cfg.name} failed: {last_exc}") from last_exc

    async def _backoff(
        self, cfg: ProviderConfig, attempt: int, exc: Exception, max_attempts: int
    ) -> None:
        """Exponentially back off, unless this was the final attempt."""
        if attempt >= max_attempts:
            return
        delay = self.RETRY_BASE_DELAY * (2 ** (attempt - 1))
        logger.debug(
            "%s attempt %d failed, retrying in %.1fs: %s", cfg.name, attempt, delay, exc
        )
        await asyncio.sleep(delay)

    async def _call_provider(
        self,
        cfg: ProviderConfig,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        await _limiter_for(cfg).acquire()

        start = time.monotonic()

        if cfg.name == "gemini":
            response = await self._call_gemini(
                cfg, prompt, system_prompt, temperature, max_tokens
            )
        else:
            response = await self._call_openai_compat(
                cfg, prompt, system_prompt, temperature, max_tokens
            )

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
            "generationConfig": _gemini_generation_config(temperature, max_tokens),
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
            raise LLMError(
                f"Gemini returned no text. Response: {json.dumps(data)[:300]}"
            )

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
            "max_tokens": min(max_tokens, settings.groq_max_tokens),
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
        """Yield response tokens: primary → backup streaming → non-streaming fallback."""
        for cfg in _provider_order():
            stream_method = (
                self._stream_gemini_tokens
                if cfg.name == "gemini"
                else self._stream_groq_tokens
            )
            if not cfg.api_key:
                continue
            # Skip a provider whose circuit breaker is open (recent fatal error)
            if _breaker_for(cfg).is_open():
                logger.info("Skipping %s streaming — circuit breaker open", cfg.name)
                continue
            yielded = False
            accumulated: list[str] = []
            start = time.monotonic()
            try:
                await _limiter_for(cfg).acquire()

                async for chunk in stream_method(
                    cfg, prompt, system_prompt, temperature, max_tokens
                ):
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
                # Quota/auth errors are per-key: rotate to a spare if we have one,
                # and only park the provider once every key is spent.
                status = exc.response.status_code
                if status in _KEY_ERRORS:
                    if not cfg.rotate_key():
                        _breaker_for(cfg).trip()
                elif status == 404 or self._has_fallback_after(cfg):
                    # 5xx/overload: park it so the fallback below (and the next
                    # calls) don't wait on it again.
                    _breaker_for(cfg).trip()
                logger.warning(
                    "%s streaming failed (HTTP %d): %s",
                    cfg.name,
                    exc.response.status_code,
                    exc,
                )
                if yielded:
                    obs.log_stream_generation(
                        provider=cfg.name,
                        model=cfg.model,
                        prompt=prompt,
                        response="".join(accumulated),
                        latency_ms=(time.monotonic() - start) * 1000,
                    )
                    return
            except Exception as exc:
                logger.warning("%s streaming failed: %s", cfg.name, exc)
                if self._has_fallback_after(cfg):
                    _breaker_for(cfg).trip()  # timeouts / network: don't retry it
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
            "generationConfig": _gemini_generation_config(temperature, max_tokens),
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
                        parts = (
                            data.get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [])
                        )
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
            "max_tokens": min(max_tokens, settings.groq_max_tokens),
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
