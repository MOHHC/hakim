"""POST /api/triage — structured triage without conversation context."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.dependencies import get_safety_guardrails, get_triage_engine
from app.core.safety_guardrails import SafetyGuardrails
from app.core.triage_engine import TriageEngine, TriageLevel

router = APIRouter(prefix="/api", tags=["triage"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TriageRequest(BaseModel):
    """Request body for POST /api/triage."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Patient symptom description (Lebanese Arabic, Franco-Arab, or English).",
    )


class TriageResponse(BaseModel):
    """Successful triage result."""

    triage_level: TriageLevel
    response_text: str
    possible_conditions: list[str]
    recommended_actions: list[str]
    sources: list[dict]
    disclaimer: str
    needs_clarification: bool
    clarification_question: str | None


class BlockedResponse(BaseModel):
    """Returned when a safety guardrail blocks the request."""

    blocked: bool = True
    reason: str
    message: str


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post(
    "/triage",
    summary="Direct structured triage",
    description=(
        "Run the full triage pipeline on a symptom description and return "
        "a structured result.\n\n"
        "Safety guardrails are applied before and after the pipeline.  "
        "Blocked queries receive a ``{blocked: true}`` response (HTTP 200) "
        "rather than an error code — the call succeeded; the content was "
        "filtered.\n\n"
        "Triage levels:\n"
        "- **GREEN** — self-care at home\n"
        "- **YELLOW** — see a doctor within 24-48 h\n"
        "- **RED** — go to the emergency room immediately\n"
    ),
    response_model=TriageResponse | BlockedResponse,
    responses={
        200: {"description": "Triage result or safety-block message"},
        422: {"description": "Validation error"},
        429: {"description": "Rate limit exceeded"},
    },
)
async def triage(
    request: TriageRequest,
    engine: Annotated[TriageEngine, Depends(get_triage_engine)],
    guardrails: Annotated[SafetyGuardrails, Depends(get_safety_guardrails)],
) -> dict:
    # Pre-input safety gate
    check = guardrails.check_query(request.query)
    if not check.is_safe:
        return {
            "blocked": True,
            "reason": check.violation_type,
            "message": check.rejection_message or "",
        }

    result = await engine.triage(request.query)

    # Post-output sanitization
    is_emergency = result.triage_level.value == "RED"
    safe_text = guardrails.sanitize_response(result.response_text)
    safe_text = guardrails.ensure_disclaimer(safe_text, is_emergency=is_emergency)

    return {
        "triage_level": result.triage_level,
        "response_text": safe_text,
        "possible_conditions": result.possible_conditions,
        "recommended_actions": result.recommended_actions,
        "sources": result.sources,
        "disclaimer": guardrails.ensure_disclaimer(
            result.disclaimer, is_emergency=is_emergency
        ),
        "needs_clarification": result.needs_clarification,
        "clarification_question": result.clarification_question,
    }
