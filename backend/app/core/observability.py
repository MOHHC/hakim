"""Langfuse observability wrapper.

All public functions are safe to call unconditionally — they are silent no-ops
when LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are not configured, or when the
langfuse package is not installed.  Triage must never fail due to observability.
"""
from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ContextVars — one per async triage call, so concurrent requests never cross.
# ---------------------------------------------------------------------------

# Active Langfuse StatefulTraceClient (or None)
_active_trace: ContextVar[Any] = ContextVar("lf_trace", default=None)
# Human-readable step name set by TriageEngine before each LLM call
_active_step: ContextVar[str] = ContextVar("lf_step", default="llm-call")

# ---------------------------------------------------------------------------
# Lazy singleton client
# ---------------------------------------------------------------------------

_client: Any = None
_init_attempted: bool = False


def _init() -> None:
    global _client, _init_attempted
    if _init_attempted:
        return
    _init_attempted = True
    try:
        from langfuse import Langfuse  # noqa: PLC0415  (lazy import)
        from app.config import settings  # noqa: PLC0415

        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            return
        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info("Langfuse observability enabled → %s", settings.langfuse_host)
    except ImportError:
        logger.debug("langfuse package not installed — observability disabled")
    except Exception as exc:
        logger.warning("Langfuse init failed, observability disabled: %s", exc)


def get_client() -> Any:
    _init()
    return _client


# ---------------------------------------------------------------------------
# Trace lifecycle
# ---------------------------------------------------------------------------


def start_trace(
    name: str,
    user_id: str = "anonymous",
    metadata: dict[str, Any] | None = None,
) -> Any:
    """Create a trace and store it in the ContextVar.  Returns trace or None."""
    lf = get_client()
    if lf is None:
        return None
    try:
        trace = lf.trace(name=name, user_id=user_id, metadata=metadata or {})
        _active_trace.set(trace)
        return trace
    except Exception as exc:
        logger.debug("start_trace failed: %s", exc)
        return None


def end_trace(
    trace: Any,
    *,
    output: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Finalise the trace.  Always swallows exceptions."""
    if trace is None:
        return
    try:
        if error:
            trace.update(metadata={"error": error}, level="ERROR")
        elif output:
            trace.update(output=output)
    except Exception as exc:
        logger.debug("end_trace failed: %s", exc)
    finally:
        _active_trace.set(None)


# ---------------------------------------------------------------------------
# Step name helper (set by TriageEngine before each LLM call)
# ---------------------------------------------------------------------------


def set_step(name: str) -> None:
    _active_step.set(name)


# ---------------------------------------------------------------------------
# Generation logging (called by LLMClient after every non-streaming call)
# ---------------------------------------------------------------------------


def log_generation(
    *,
    provider: str,
    model: str,
    system_prompt: str,
    prompt: str,
    response: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    latency_ms: float,
    temperature: float,
    max_tokens: int,
) -> None:
    """Attach an LLM generation to the active trace.  No-op if no active trace."""
    trace = _active_trace.get()
    if trace is None:
        return
    step = _active_step.get()
    try:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt[:2000]})
        messages.append({"role": "user", "content": prompt[:3000]})

        trace.generation(
            name=f"{step}:{provider}",
            model=model,
            model_parameters={"temperature": temperature, "max_tokens": max_tokens},
            input=messages,
            output=response[:4000],
            usage={
                "input": prompt_tokens,
                "output": completion_tokens,
                "total": total_tokens,
                "unit": "TOKENS",
            },
            metadata={"latency_ms": round(latency_ms, 1)},
        )
    except Exception as exc:
        logger.debug("log_generation failed: %s", exc)


def log_stream_generation(
    *,
    provider: str,
    model: str,
    prompt: str,
    response: str,
    latency_ms: float,
) -> None:
    """Log a streaming generation (no token counts available from stream API)."""
    trace = _active_trace.get()
    if trace is None:
        return
    step = _active_step.get()
    try:
        trace.generation(
            name=f"{step}:{provider}(stream)",
            model=model,
            input=[{"role": "user", "content": prompt[:3000]}],
            output=response[:4000],
            metadata={"latency_ms": round(latency_ms, 1), "streamed": True},
        )
    except Exception as exc:
        logger.debug("log_stream_generation failed: %s", exc)


# ---------------------------------------------------------------------------
# Flush (call on app shutdown to drain the SDK's async queue)
# ---------------------------------------------------------------------------


def flush() -> None:
    lf = get_client()
    if lf is not None:
        try:
            lf.flush()
        except Exception as exc:
            logger.debug("Langfuse flush failed: %s", exc)
