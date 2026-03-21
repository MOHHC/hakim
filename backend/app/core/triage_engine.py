"""Triage engine: multi-step triage agent for Lebanese Arabic medical queries."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.core.arabic_processor import ArabicProcessor, LexiconMatch
from app.core.llm_client import LLMClient
from app.core.rag_pipeline import RAGPipeline, RetrievalResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Emergency keyword patterns -> instant RED
# ---------------------------------------------------------------------------

# Stored as plain substrings; _EMERGENCY_RE handles case-insensitive matching.
_EMERGENCY_SUBSTRINGS = [
    # Arabic critical presentations (unicode literals so the file stays ASCII-safe)
    "\u0635\u0639\u0648\u0628\u0629 \u062a\u0646\u0641\u0633",    # difficulty breathing
    "\u0636\u064a\u0642 \u062a\u0646\u0641\u0633",                 # breath tightness
    "\u0641\u0642\u062f\u0627\u0646 \u0648\u0639\u064a",           # loss of consciousness
    "\u0646\u0632\u064a\u0641 \u0634\u062f\u064a\u062f",           # severe bleeding
    "\u062c\u0644\u0637\u0629",                                     # clot/stroke
    "\u0633\u0643\u062a\u0629",                                     # stroke (sukta)
    "\u0634\u0644\u0644",                                           # paralysis
    "\u062a\u0634\u0646\u062c",                                     # convulsion
    # Franco-Arab / English
    "chest pain", "cant breathe", "can't breathe",
    "shortness of breath", "heart attack",
    "lost consciousness", "unconscious", "heavy bleeding", "stroke",
    "ta3ab ktir bnafs", "waja3 sadr ktir", "ma 3am tnaffas",
]

_EMERGENCY_RE = re.compile(
    "|".join(re.escape(s) for s in _EMERGENCY_SUBSTRINGS), re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Refusal trigger patterns (CLAUDE.md safety rules)
# ---------------------------------------------------------------------------

_REFUSAL_SUBSTRINGS = [
    "\u0631\u0636\u064a\u0639",                                                   # infant
    "\u0646\u062a\u064a\u062c\u0629 \u062a\u062d\u0644\u064a\u0644",             # lab result
    "\u062a\u062d\u0627\u0644\u064a\u0644 \u0637\u0644\u0639\u062a",             # results came out
]
_REFUSAL_RE = re.compile(
    "|".join(re.escape(s) for s in _REFUSAL_SUBSTRINGS), re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are Hakim, a Lebanese medical triage assistant. "
    "Rules: (1) Never give a definitive diagnosis -- say 'may be' or 'possible'. "
    "(2) Never name medications or dosages. "
    "(3) Always add a disclaimer that this is not a substitute for a doctor."
)

_TRIAGE_PROMPT = (
    "Patient symptoms: {symptoms_text}\n\n"
    "Relevant medical context:\n{context}\n\n"
    "Classify urgency. Respond ONLY in valid JSON, no extra text:\n"
    '{{\n'
    '  "triage_level": "GREEN" or "YELLOW" or "RED",\n'
    '  "possible_conditions": ["condition 1", "condition 2"],\n'
    '  "recommended_actions": ["action 1", "action 2"]\n'
    '}}\n\n'
    "Criteria:\n"
    "- RED   : Emergency -- go to ER immediately\n"
    "- YELLOW: See a doctor within 24-48 h\n"
    "- GREEN : Can manage at home with monitoring\n\n"
    "JSON:"
)

_RESPONSE_PROMPT = (
    "Write a response in Lebanese colloquial Arabic (not Modern Standard Arabic) "
    "to a patient complaining of: {symptoms_text}\n\n"
    "Triage level: {triage_level}\n"
    "Possible conditions: {conditions}\n"
    "Recommended actions: {actions}\n\n"
    "Rules:\n"
    "- Lebanese dialect (3ammiye)\n"
    "- Start with empathy\n"
    "- Be clear about urgency\n"
    "- Use 'ma byekoun 2ella' or 'mn al-ihtimelat' before conditions\n"
    "- No medication names or dosages\n"
    "- 3-5 sentences, one cohesive paragraph\n\n"
    "Response:"
)

_CLARIFICATION_PROMPT = (
    'A Lebanese patient said: "{query}"\n\n'
    "Extracted symptoms: {symptoms_text}\n\n"
    "The symptoms are too vague for assessment. "
    "Write ONE clarifying question in Lebanese colloquial Arabic "
    "to better understand the situation. "
    "Write only the question, no preamble:"
)

_DISCLAIMER = (
    "\u26a0\ufe0f Disclaimer: This info does not replace a doctor. "
    "If the condition worsens, please see a doctor."
)
_EMERGENCY_DISCLAIMER = (
    "\U0001f6a8 These symptoms are serious \u2014 "
    "go to the ER now or call 140!"
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class TriageLevel(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


@dataclass
class TriageResult:
    triage_level: TriageLevel
    response_text: str
    possible_conditions: list[str]
    recommended_actions: list[str]
    sources: list[dict]
    disclaimer: str
    needs_clarification: bool = False
    clarification_question: str | None = None
    total_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "triage_level": self.triage_level.value,
            "response_text": self.response_text,
            "possible_conditions": self.possible_conditions,
            "recommended_actions": self.recommended_actions,
            "sources": self.sources,
            "disclaimer": self.disclaimer,
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class TriageEngine:
    """Multi-step triage agent: extract -> clarify -> retrieve -> classify -> respond."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        arabic_processor: ArabicProcessor | None = None,
        rag_pipeline: RAGPipeline | None = None,
    ) -> None:
        self._llm = llm_client or LLMClient()
        self._proc = arabic_processor or ArabicProcessor()
        self._rag = rag_pipeline  # None -> retrieval skipped

    async def triage(
        self,
        query: str,
        prior_symptoms: list[LexiconMatch] | None = None,
    ) -> TriageResult:
        """Run the full 5-step triage pipeline."""
        total_tokens = 0

        # Step 1: Symptom extraction
        symptoms = (
            prior_symptoms
            if prior_symptoms is not None
            else self._proc.extract_symptoms(query)
        )
        symptom_labels = [
            s.english_medical_term or s.msa_equivalent
            for s in symptoms
            if s.english_medical_term or s.msa_equivalent
        ]
        symptoms_text = ", ".join(symptom_labels) if symptom_labels else query
        logger.info("Step 1 -- extracted %d symptoms: %s", len(symptoms), symptom_labels)

        # Safety gate: refuse out-of-scope cases immediately
        if _REFUSAL_RE.search(query):
            logger.info("Safety refusal triggered for query: %r", query[:60])
            return TriageResult(
                triage_level=TriageLevel.YELLOW,
                response_text=(
                    "Sorry, I cannot help with this case. "
                    "For infants, pregnancy complications, or lab results, "
                    "please consult a doctor directly."
                ),
                possible_conditions=[],
                recommended_actions=["Consult a doctor immediately"],
                sources=[],
                disclaimer=_DISCLAIMER,
            )

        # Emergency fast-path: skip Steps 2-4 -> instant RED
        if _EMERGENCY_RE.search(query):
            logger.info("Step 1b -- emergency detected, fast-path RED")
            return await self._emergency_response(symptoms_text, total_tokens)

        # Step 2: Clarification -- only when genuinely vague
        if len(symptoms) < 2 and len(query.split()) < 4:
            logger.info("Step 2 -- vague query, requesting clarification")
            clarify_resp = await self._llm.generate(
                prompt=_CLARIFICATION_PROMPT.format(
                    query=query,
                    symptoms_text=symptoms_text if symptom_labels else "nothing specific",
                ),
                system_prompt=_SYSTEM_PROMPT,
                temperature=0.4,
                max_tokens=256,
            )
            total_tokens += clarify_resp.total_tokens
            q = clarify_resp.text.strip()
            return TriageResult(
                triage_level=TriageLevel.GREEN,
                response_text=q,
                possible_conditions=[],
                recommended_actions=[],
                sources=[],
                disclaimer=_DISCLAIMER,
                needs_clarification=True,
                clarification_question=q,
                total_tokens=total_tokens,
            )

        # Step 3: Knowledge retrieval
        retrieval_results: list[RetrievalResult] = []
        if self._rag is not None:
            retrieval_results = await self._rag.retrieve(query, symptoms=symptoms)
            logger.info("Step 3 -- retrieved %d chunks", len(retrieval_results))
        context = self._format_context(retrieval_results)

        # Step 4: Triage classification
        classify_resp = await self._llm.generate(
            prompt=_TRIAGE_PROMPT.format(symptoms_text=symptoms_text, context=context),
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=512,
        )
        total_tokens += classify_resp.total_tokens
        triage_level, conditions, actions = self._parse_triage_json(classify_resp.text)
        logger.info("Step 4 -- level=%s | conditions=%s", triage_level, conditions)

        # Step 5: Response generation in Lebanese Arabic
        response_resp = await self._llm.generate(
            prompt=_RESPONSE_PROMPT.format(
                symptoms_text=symptoms_text,
                triage_level=triage_level.value,
                conditions=", ".join(conditions) if conditions else "unspecified",
                actions=", ".join(actions) if actions else "follow up with doctor",
            ),
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.4,
            max_tokens=768,
        )
        total_tokens += response_resp.total_tokens

        disclaimer = _EMERGENCY_DISCLAIMER if triage_level == TriageLevel.RED else _DISCLAIMER
        return TriageResult(
            triage_level=triage_level,
            response_text=response_resp.text.strip(),
            possible_conditions=conditions,
            recommended_actions=actions,
            sources=[r.to_dict() for r in retrieval_results],
            disclaimer=disclaimer,
            total_tokens=total_tokens,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _emergency_response(
        self, symptoms_text: str, base_tokens: int
    ) -> TriageResult:
        resp = await self._llm.generate(
            prompt=_RESPONSE_PROMPT.format(
                symptoms_text=symptoms_text,
                triage_level="RED",
                conditions="possible emergency",
                actions="call ambulance immediately -- 140",
            ),
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=512,
        )
        return TriageResult(
            triage_level=TriageLevel.RED,
            response_text=resp.text.strip(),
            possible_conditions=["emergency"],
            recommended_actions=["call ambulance immediately -- 140", "go to ER now"],
            sources=[],
            disclaimer=_EMERGENCY_DISCLAIMER,
            total_tokens=base_tokens + resp.total_tokens,
        )

    @staticmethod
    def _format_context(results: list[RetrievalResult]) -> str:
        if not results:
            return "No additional medical information available."
        parts = [
            f"[{i}] {r.chunk_text[:400]} (source: {r.source})"
            for i, r in enumerate(results[:4], 1)
        ]
        return "\n\n".join(parts)

    @staticmethod
    def _parse_triage_json(
        text: str,
        default_level: TriageLevel = TriageLevel.YELLOW,
    ) -> tuple[TriageLevel, list[str], list[str]]:
        """Parse LLM JSON output; return defaults on any error."""
        try:
            clean = re.sub(r"```(?:json)?|```", "", text).strip()
            match = re.search(r"\{.*\}", clean, re.DOTALL)
            if not match:
                raise ValueError("no JSON object found")
            data = json.loads(match.group(0))
            level_str = str(data.get("triage_level", "")).strip().upper()
            level = (
                TriageLevel[level_str]
                if level_str in TriageLevel.__members__
                else default_level
            )
            conditions: list[str] = data.get("possible_conditions", [])
            actions: list[str] = data.get("recommended_actions", [])
            return level, conditions[:5], actions[:5]
        except Exception as exc:
            logger.warning(
                "Failed to parse triage JSON: %s | text=%r", exc, text[:200]
            )
            return default_level, [], []
