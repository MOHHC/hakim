"""POST /api/chat — conversational triage with SSE streaming."""

from __future__ import annotations

import json
import logging
import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.dependencies import get_safety_guardrails, get_triage_engine
from app.core.safety_guardrails import SafetyGuardrails, detect_script
from app.core.triage_engine import TriageEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    """A single turn in the conversation history."""

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    """Request body for POST /api/chat."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Patient's symptom description in Lebanese Arabic, Franco-Arab, or English.",
    )
    conversation_history: list[ChatMessage] = Field(
        default_factory=list,
        max_length=20,
        description="Previous turns, newest last. Used for context only.",
    )
    language_preference: Literal["arabic", "english", "auto"] = Field(
        "auto",
        description="Preferred response language. 'auto' detects from input.",
    )
    response_script: Literal["arabic", "franco"] = Field(
        "arabic",
        description="Response script: 'arabic' for Arabic script, 'franco' for Franco-Arab (Latin letters).",
    )


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------


def _sse(data: dict) -> str:
    """Format a dict as a Server-Sent Event frame."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _output_script(request: ChatRequest) -> str:
    """Pick the reply language: "english", "franco" or "arabic"."""
    if request.language_preference == "english":
        return "english"
    if request.response_script == "franco":
        return "franco"
    if request.language_preference == "auto":
        return detect_script(request.message)
    return "arabic"


# Where it is safe to cut streamed text for sanitising: a dosage like "500 mg"
# never spans a sentence end, so each sentence can be cleaned on its own.
_SENTENCE_END_RE = re.compile(r"[.!?؟،\n]")

_ERROR_MESSAGES = {
    "arabic": "صار في مشكلة تقنية. جرب كمان مرة. إذا حاسس إنو حالتك طارئة، اتصل بالصليب الأحمر على 140.",
    "franco": "sar fi moshkle te2niye. jarreb kamen marra. eza 7ases enno 7altak tar2a, ettesel bel Salib l A7mar 3ala 140.",
    "english": "Something went wrong on our side. Please try again. If this feels like an emergency, call the Red Cross on 140.",
}


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post(
    "/chat",
    summary="Conversational triage with SSE streaming",
    description=(
        "Accepts a patient message and streams a triage response as "
        "Server-Sent Events.  Safety guardrails are applied before the "
        "pipeline runs.\n\n"
        "**Event types emitted in order:**\n"
        "- `start` — pipeline accepted the request\n"
        "- `blocked` — safety guardrail triggered (stream ends here)\n"
        "- `chunk` — response text token (repeated)\n"
        "- `complete` — final metadata (triage level, sources, disclaimer)\n"
        "- `[DONE]` — stream terminator\n"
    ),
    response_description="text/event-stream of JSON events",
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": "SSE stream",
        },
        422: {"description": "Validation error"},
        429: {"description": "Rate limit exceeded"},
    },
)
async def chat(
    request: ChatRequest,
    engine: Annotated[TriageEngine, Depends(get_triage_engine)],
    guardrails: Annotated[SafetyGuardrails, Depends(get_safety_guardrails)],
) -> StreamingResponse:
    script = _output_script(request)
    history = [m.content for m in request.conversation_history if m.role == "user"]

    async def event_stream():
        yield _sse({"type": "start"})

        # Safety gate — runs synchronously, no LLM call
        check = guardrails.check_query(request.message)
        if not check.is_safe:
            yield _sse(
                {
                    "type": "blocked",
                    "reason": check.violation_type,
                    "message": guardrails.format_rejection(check, script),
                    "force_red": check.force_red,
                }
            )
            yield "data: [DONE]\n\n"
            return

        # Run streaming triage pipeline — yields triage_classified → chunk×N → complete.
        # Model text is held back to the end of each sentence and sanitised
        # there, so a dosage or drug name never reaches the patient mid-stream.
        pending = ""
        try:
            async for event in engine.triage_stream(
                request.message, response_script=script, history=history
            ):
                if event["type"] == "chunk":
                    pending += event.get("content", "")
                    cut = max(
                        (m.end() for m in _SENTENCE_END_RE.finditer(pending)),
                        default=0,
                    )
                    if cut:
                        ready, pending = pending[:cut], pending[cut:]
                        yield _sse(
                            {
                                "type": "chunk",
                                "content": guardrails.sanitize_response(ready),
                            }
                        )
                    continue
                if event["type"] == "complete":
                    if pending:
                        yield _sse(
                            {
                                "type": "chunk",
                                "content": guardrails.sanitize_response(pending),
                            }
                        )
                        pending = ""
                    # The engine already picked a disclaimer in the reply language
                    if not event.get("disclaimer"):
                        event["disclaimer"] = guardrails.ensure_disclaimer(
                            "",
                            is_emergency=event.get("triage_level") == "RED",
                            script=script,
                        ).strip()
                yield _sse(event)
        except Exception as exc:
            logger.exception("Triage stream failed: %s", exc)
            yield _sse({"type": "error", "message": _ERROR_MESSAGES[script]})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
