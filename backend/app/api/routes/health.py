"""GET /api/health — system status including component availability."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["health"])


class ComponentStatus(BaseModel):
    status: str  # "ok" | "degraded" | "error"
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str
    components: dict[str, ComponentStatus]


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System health check",
    description=(
        "Returns overall system status and per-component availability. "
        "``status`` is ``ok`` when all components are healthy, "
        "``degraded`` when some are unavailable but requests can still be served."
    ),
)
async def health_check() -> HealthResponse:
    from app.config import settings

    components: dict[str, ComponentStatus] = {}
    overall = "ok"

    # --- LLM providers (check key presence only, no HTTP call) ---
    gemini_ok = bool(settings.gemini_api_key)
    groq_ok = bool(settings.groq_api_key)
    if gemini_ok or groq_ok:
        labels = []
        if gemini_ok:
            labels.append("gemini (primary)")
        if groq_ok:
            labels.append("groq (fallback)")
        components["llm"] = ComponentStatus(
            status="ok", detail=f"configured: {', '.join(labels)}"
        )
    else:
        components["llm"] = ComponentStatus(
            status="error", detail="no LLM API keys configured"
        )
        overall = "degraded"

    # --- Vector store (count() is synchronous, no network call) ---
    try:
        from app.knowledge.vector_store import VectorStore

        store = VectorStore()
        doc_count = store.count()
        components["vector_store"] = ComponentStatus(
            status="ok", detail=f"{doc_count} documents indexed"
        )
    except Exception as exc:
        components["vector_store"] = ComponentStatus(
            status="error", detail=str(exc)[:120]
        )
        overall = "degraded"

    # --- Arabic processor / lexicon ---
    try:
        from app.core.arabic_processor import ArabicProcessor

        proc = ArabicProcessor()
        entry_count = len(proc._entries)
        if entry_count == 0:
            components["arabic_processor"] = ComponentStatus(
                status="degraded", detail="lexicon not loaded"
            )
            overall = "degraded"
        else:
            components["arabic_processor"] = ComponentStatus(
                status="ok", detail=f"{entry_count} lexicon entries"
            )
    except Exception as exc:
        components["arabic_processor"] = ComponentStatus(
            status="error", detail=str(exc)[:120]
        )
        overall = "degraded"

    return HealthResponse(
        status=overall,
        version="0.1.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
        components=components,
    )
