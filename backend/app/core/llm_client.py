"""LLM client with Gemini primary and Groq fallback."""

import asyncio
import json
import logging
import time
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
    model="gemini-1.5-flash",
    # Gemini uses query-param key, not Authorization header
    auth_header="x-goog-api-key",
    auth_prefix="",
)

GROQ_CONFIG = ProviderConfig(
    name="groq",
    base_url="https://api.groq.com/openai/v1",
    api_key=settings.groq_api_key,
    model="llama3-8b-8192",
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


class LLMClient:
    """Async LLM client with Gemini primary, Groq fallback, and retry logic."""

    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 1.0  # seconds

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Generate a response, trying Gemini first then Groq on failure."""
        for provider_cfg in (GEMINI_CONFIG, GROQ_CONFIG):
            try:
                return await self._generate_with_retry(
                    provider_cfg, prompt, system_prompt, temperature, max_tokens
                )
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
            except (httpx.HTTPStatusError, httpx.RequestError, LLMError) as exc:
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
        candidate = data["candidates"][0]["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata", {})
        prompt_tokens = usage.get("promptTokenCount", 0)
        completion_tokens = usage.get("candidatesTokenCount", 0)

        return LLMResponse(
            text=candidate,
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
            yielded = False
            accumulated: list[str] = []
            start = time.monotonic()
            try:
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
                        text = data["candidates"][0]["content"]["parts"][0]["text"]
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
