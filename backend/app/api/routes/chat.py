"""POST /api/chat — conversational triage with SSE streaming."""
from __future__ import annotations

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.dependencies import get_safety_guardrails, get_triage_engine
from app.core.safety_guardrails import SafetyGuardrails
from app.core.triage_engine import TriageEngine

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


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------


def _sse(data: dict) -> str:
    """Format a dict as a Server-Sent Event frame."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


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
    async def event_stream():
        yield _sse({"type": "start"})

        # Safety gate — runs synchronously, no LLM call
        check = guardrails.check_query(request.message)
        if not check.is_safe:
            yield _sse(
                {
                    "type": "blocked",
                    "reason": check.violation_type,
                    "message": guardrails.ensure_disclaimer(
                        check.rejection_message or "",
                        is_emergency=guardrails.is_emergency_violation(check),
                    ),
                    "force_red": check.force_red,
                }
            )
            yield "data: [DONE]\n\n"
            return

        # Run streaming triage pipeline — yields triage_classified → chunk×N → complete
        try:
            async for event in engine.triage_stream(request.message):
                if event["type"] == "complete":
                    # Apply guardrail disclaimer post-processing to the complete event
                    is_emergency = event.get("triage_level") == "RED"
                    event["disclaimer"] = guardrails.ensure_disclaimer(
                        event.get("disclaimer", ""), is_emergency=is_emergency
                    )
                yield _sse(event)
        except Exception:
            yield _sse(
                {
                    "type": "error",
                    "message": "Triage processing failed. Please try again.",
                }
            )
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
