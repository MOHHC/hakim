"""FastAPI dependency factories.

Each factory is a plain callable so FastAPI's ``Depends()`` system can
inject them into route handlers, and tests can override them with
``app.dependency_overrides``.
"""
from __future__ import annotations

from app.core.arabic_processor import ArabicProcessor
from app.core.llm_client import LLMClient
from app.core.safety_guardrails import SafetyGuardrails
from app.core.triage_engine import TriageEngine

# ---------------------------------------------------------------------------
# Lazy module-level singletons (instantiated on first request)
# ---------------------------------------------------------------------------

_arabic_processor: ArabicProcessor | None = None
_llm_client: LLMClient | None = None
_triage_engine: TriageEngine | None = None
_safety_guardrails: SafetyGuardrails | None = None


def get_arabic_processor() -> ArabicProcessor:
    global _arabic_processor
    if _arabic_processor is None:
        _arabic_processor = ArabicProcessor()
    return _arabic_processor


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


def get_safety_guardrails() -> SafetyGuardrails:
    global _safety_guardrails
    if _safety_guardrails is None:
        _safety_guardrails = SafetyGuardrails()
    return _safety_guardrails


def get_triage_engine() -> TriageEngine:
    global _triage_engine
    if _triage_engine is None:
        _triage_engine = TriageEngine(
            llm_client=get_llm_client(),
            arabic_processor=get_arabic_processor(),
            rag_pipeline=None,  # populated after knowledge base is ingested
        )
    return _triage_engine
