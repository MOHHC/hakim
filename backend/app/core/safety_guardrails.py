"""Safety guardrails: pre/post-filter rules for the Hakim triage assistant.

Two main entry points:
  check_query(query)      -> GuardrailResult  (pre-LLM input gate)
  check_response(text)    -> GuardrailResult  (post-LLM output gate)
  sanitize_response(text) -> str              (strip prohibited content)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple


# ---------------------------------------------------------------------------
# ViolationType
# ---------------------------------------------------------------------------


class ViolationType(str, Enum):
    SCOPE_INFANT = "scope_infant"
    SCOPE_PREGNANCY = "scope_pregnancy"
    SCOPE_LAB_RESULTS = "scope_lab_results"
    EMERGENCY_RED_FLAG = "emergency_red_flag"
    SUICIDAL_IDEATION = "suicidal_ideation"
    DIAGNOSIS_LANGUAGE = "diagnosis_language"
    MEDICATION_REFERENCE = "medication_reference"


# ---------------------------------------------------------------------------
# GuardrailResult
# ---------------------------------------------------------------------------


@dataclass
class GuardrailResult:
    """Outcome of a guardrail check.

    is_safe:           False means a rule was triggered.
    violation_type:    Which rule fired.
    rejection_message: Ready-made reply to send to the user.
    force_red:         Immediately escalate triage to RED.
    add_uncertainty:   Append the uncertainty disclaimer to the response.
    """

    is_safe: bool
    violation_type: ViolationType | None = None
    rejection_message: str | None = None
    force_red: bool = False
    add_uncertainty: bool = False


# ---------------------------------------------------------------------------
# Compound red-flag pattern helper
# ---------------------------------------------------------------------------


class _RedFlagPattern(NamedTuple):
    name: str
    triggers_a: list[str]  # at least one must match
    triggers_b: list[str]  # at least one must also match (compound check)


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

# ---- Scope-limit substrings -----------------------------------------------

_INFANT_SUBSTRINGS = [
    "\u0631\u0636\u064a\u0639",         # رضيع
    "\u0631\u0636\u064a\u0639\u0629",   # رضيعة
    "infant", "newborn",
    "2 months old", "6 months old", "1 year old", "18 months old",
    "under 2 years", "less than 2 years", "baby under 2",
]
_INFANT_RE = re.compile(
    "|".join(re.escape(s) for s in _INFANT_SUBSTRINGS), re.IGNORECASE
)

_PREGNANCY_SUBSTRINGS = [
    "\u062d\u0627\u0645\u0644\u0629",    # حاملة
    "\u062d\u0645\u0644",                # حمل
    "pregnant", "pregnancy",
    "contractions", "water broke", "preeclampsia", "hamil",
]
_PREGNANCY_RE = re.compile(
    "|".join(re.escape(s) for s in _PREGNANCY_SUBSTRINGS), re.IGNORECASE
)

_LAB_SUBSTRINGS = [
    "\u0646\u062a\u064a\u062c\u0629 \u062a\u062d\u0644\u064a\u0644",    # نتيجة تحليل
    "\u062a\u062d\u0627\u0644\u064a\u0644 \u0637\u0644\u0639\u062a",    # تحاليل طلعت
    "\u0646\u062a\u064a\u062c\u0629 \u0635\u0648\u0631\u0629",          # نتيجة صورة
    "\u0635\u0648\u0631\u0629 \u0623\u0634\u0639\u0629",                # صورة أشعة
    "lab result", "blood test result", "test result",
    "x-ray result", "mri result", "ct scan result",
    "ultrasound result", "ecg result", "biopsy result",
    "my results show", "my tests show", "natijet tahlil",
]
_LAB_RE = re.compile(
    "|".join(re.escape(s) for s in _LAB_SUBSTRINGS), re.IGNORECASE
)

# ---- Suicidal ideation (single-trigger, highest priority) ------------------

_SUICIDAL_SUBSTRINGS = [
    "\u0628\u062f\u064a \u0645\u0648\u062a",                            # بدي موت
    "\u0628\u062f\u064a \u0642\u062a\u0644 \u062d\u0627\u0644\u064a",  # بدي قتل حالي
    "\u0645\u0627 \u0628\u062f\u064a \u0639\u064a\u0634",              # ما بدي عيش
    "\u0627\u0646\u062a\u062d\u0627\u0631",                             # انتحار
    "kill myself", "end my life", "suicide", "want to die",
    "no reason to live", "better off dead", "baddi mout",
]
_SUICIDAL_RE = re.compile(
    "|".join(re.escape(s) for s in _SUICIDAL_SUBSTRINGS), re.IGNORECASE
)

# ---- Compound red-flag patterns (require TWO symptom groups) ---------------

_RED_FLAG_PATTERNS: list[_RedFlagPattern] = [
    # MI / Cardiac
    _RedFlagPattern(
        name="cardiac_mi",
        triggers_a=[
            "chest pain", "waja3 sadr", "chest tightness", "chest pressure",
            "\u0623\u0644\u0645 \u0635\u062f\u0631",   # ألم صدر
            "\u0648\u062c\u0639 \u0635\u062f\u0631",   # وجع صدر
        ],
        triggers_b=[
            "arm numbness", "arm pain", "left arm", "jaw pain", "jaw numbness",
            "shoulder pain", "shoulder numbness", "radiating",
            "\u062e\u062f\u0631 \u064a\u062f",    # خدر يد
            "\u0630\u0631\u0627\u0639",            # ذراع
            "\u0643\u062a\u0641",                  # كتف
            "\u0641\u0643",                        # فك
        ],
    ),
    # Anaphylaxis
    _RedFlagPattern(
        name="anaphylaxis",
        triggers_a=[
            "throat swelling", "swollen throat", "can't swallow",
            "hives", "allergic reaction", "anaphylaxis",
            "\u062a\u0648\u0631\u0645 \u0632\u0648\u0631",              # تورم زور
            "\u062d\u0633\u0627\u0633\u064a\u0629 \u0634\u062f\u064a\u062f\u0629",  # حساسية شديدة
        ],
        triggers_b=[
            "difficulty breathing", "can't breathe", "cant breathe",
            "shortness of breath", "throat closing",
            "\u0635\u0639\u0648\u0628\u0629 \u062a\u0646\u0641\u0633",  # صعوبة تنفس
            "\u0636\u064a\u0642 \u062a\u0646\u0641\u0633",              # ضيق تنفس
        ],
    ),
    # Head trauma
    _RedFlagPattern(
        name="head_trauma",
        triggers_a=[
            "head injury", "hit my head", "hit head", "head trauma",
            "fell and hit", "bang on head",
            "\u0636\u0631\u0628\u062a \u0631\u0627\u0633\u064a",              # ضربت راسي
            "\u0648\u0642\u0639\u062a \u0639\u0644\u0649 \u0631\u0627\u0633\u064a",  # وقعت على راسي
            "darabt rasi",
        ],
        triggers_b=[
            "vomiting", "throwing up", "unconscious", "lost consciousness",
            "confusion", "blurred vision", "seizure",
            "\u0631\u062c\u0651\u0639",                                        # رجّع
            "\u0636\u064a\u0627\u0639 \u0648\u0639\u064a",                     # ضياع وعي
        ],
    ),
]

# ---- Medication / dosage detection in LLM output --------------------------

_DOSAGE_RE = re.compile(
    r"\b\d+\s*(?:mg|ml|mcg|microgram|gram|tablet|pill|dose|capsule)s?\b",
    re.IGNORECASE,
)

_DRUG_RE = re.compile(
    r"\b(?:"
    r"ibuprofen|paracetamol|acetaminophen|aspirin|amoxicillin|"
    r"metformin|atorvastatin|omeprazole|diazepam|tramadol|"
    r"codeine|morphine|warfarin|prednisone|methotrexate|"
    r"[a-z]{4,}(?:cillin|mycin|oxacin|statin|prazole|sartan|dipine|olol)"
    r")\b",
    re.IGNORECASE,
)

_TAKE_DRUG_RE = re.compile(
    r"\b(?:take|خذ|خذي|تناول|تناولي)\s+\w+(?:\s+\d+)?",
    re.IGNORECASE,
)

# ---- Diagnosis language in LLM output ------------------------------------

_DIAGNOSIS_RE = re.compile(
    r"\byou\s+(?:have|are\s+diagnosed\s+with|suffer\s+from)\b"
    r"|"
    r"\bthis\s+is\s+(?:definitely|clearly|certainly)\b"
    r"|"
    r"\b(?:diagnosis|diagnose)\b",
    re.IGNORECASE,
)

_HEDGING_RE = re.compile(
    r"\b(?:"
    r"may|might|could|possible|possibly|likely|probably|"
    r"suggest|indicate|appear|seem|consider|"
    r"\u0642\u062f|\u0631\u0628\u0645\u0627|\u0645\u062d\u062a\u0645\u0644|"  # قد ربما محتمل
    r"\u064a\u0645\u0643\u0646|\u064a\u0628\u062f\u0648"                      # يمكن يبدو
    r")\b",
    re.IGNORECASE,
)

# ---- Disclaimers -----------------------------------------------------------

DISCLAIMER = (
    "\u26a0\ufe0f This information does not replace a doctor. "
    "If symptoms worsen, please seek medical care."
)
EMERGENCY_DISCLAIMER = (
    "\U0001f6a8 These symptoms require IMMEDIATE emergency care. "
    "Call 140 or go to the ER now."
)
UNCERTAINTY_TEXT = (
    "I'm not certain about this case. "
    "Please consult a doctor for a proper evaluation."
)

# ---- Rejection messages ---------------------------------------------------

_REJECTION: dict[ViolationType, str] = {
    ViolationType.SCOPE_INFANT: (
        "I'm not able to provide triage for children under 2 years old. "
        "Please take your child to a pediatrician or ER immediately."
    ),
    ViolationType.SCOPE_PREGNANCY: (
        "I'm not able to advise on pregnancy complications. "
        "Please contact your OB/GYN or go to the nearest maternity unit."
    ),
    ViolationType.SCOPE_LAB_RESULTS: (
        "I'm not able to interpret lab results, imaging, or medical reports. "
        "Please discuss these directly with your doctor."
    ),
    ViolationType.EMERGENCY_RED_FLAG: (
        "These symptoms indicate a possible medical emergency. "
        "Call 140 or go to the ER immediately. Do not wait."
    ),
    ViolationType.SUICIDAL_IDEATION: (
        "I'm very concerned about you. Please call a crisis helpline or "
        "go to the nearest emergency room right now. "
        "You are not alone, and help is available."
    ),
}


# ---------------------------------------------------------------------------
# SafetyGuardrails
# ---------------------------------------------------------------------------


class SafetyGuardrails:
    """Enforce hard safety rules before and after the triage pipeline."""

    # ------------------------------------------------------------------
    # Pre-input gate
    # ------------------------------------------------------------------

    def check_query(self, query: str) -> GuardrailResult:
        """Check user input before processing.

        Priority order:
          1. Suicidal ideation  (mental health crisis)
          2. Scope: infant      (send to pediatrician)
          3. Scope: pregnancy   (send to OB/GYN)
          4. Scope: lab results (refer to doctor)
          5. Compound emergency red flags (force RED)
        """
        if _SUICIDAL_RE.search(query):
            return GuardrailResult(
                is_safe=False,
                violation_type=ViolationType.SUICIDAL_IDEATION,
                rejection_message=_REJECTION[ViolationType.SUICIDAL_IDEATION],
                force_red=False,
            )
        if _INFANT_RE.search(query):
            return GuardrailResult(
                is_safe=False,
                violation_type=ViolationType.SCOPE_INFANT,
                rejection_message=_REJECTION[ViolationType.SCOPE_INFANT],
            )
        if _PREGNANCY_RE.search(query):
            return GuardrailResult(
                is_safe=False,
                violation_type=ViolationType.SCOPE_PREGNANCY,
                rejection_message=_REJECTION[ViolationType.SCOPE_PREGNANCY],
            )
        if _LAB_RE.search(query):
            return GuardrailResult(
                is_safe=False,
                violation_type=ViolationType.SCOPE_LAB_RESULTS,
                rejection_message=_REJECTION[ViolationType.SCOPE_LAB_RESULTS],
            )
        flag = self._check_red_flags(query)
        if flag:
            return GuardrailResult(
                is_safe=False,
                violation_type=ViolationType.EMERGENCY_RED_FLAG,
                rejection_message=_REJECTION[ViolationType.EMERGENCY_RED_FLAG],
                force_red=True,
            )
        return GuardrailResult(is_safe=True)

    # ------------------------------------------------------------------
    # Post-output gate
    # ------------------------------------------------------------------

    def check_response(self, text: str) -> GuardrailResult:
        """Check LLM-generated text for prohibited content.

        Returns is_safe=False when diagnosis language or medication
        references are detected.
        """
        if _DIAGNOSIS_RE.search(text):
            return GuardrailResult(
                is_safe=False,
                violation_type=ViolationType.DIAGNOSIS_LANGUAGE,
                add_uncertainty=True,
            )
        if (
            _DOSAGE_RE.search(text)
            or _DRUG_RE.search(text)
            or _TAKE_DRUG_RE.search(text)
        ):
            return GuardrailResult(
                is_safe=False,
                violation_type=ViolationType.MEDICATION_REFERENCE,
            )
        return GuardrailResult(is_safe=True)

    # ------------------------------------------------------------------
    # Output transformation
    # ------------------------------------------------------------------

    def sanitize_response(self, text: str) -> str:
        """Remove prohibited phrases from LLM output.

        Softens definitive diagnosis assertions and strips dosage /
        drug references.
        """
        # Soften hard diagnosis assertions
        text = re.sub(r"\byou\s+have\b", "you may have", text, flags=re.IGNORECASE)
        text = re.sub(
            r"\byou\s+are\s+diagnosed\s+with\b",
            "your symptoms may suggest",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\bthis\s+is\s+(?:definitely|clearly|certainly)\b",
            "this may be",
            text,
            flags=re.IGNORECASE,
        )
        # Strip dosage expressions ("500 mg of paracetamol")
        text = re.sub(
            r"\b\d+\s*(?:mg|ml|mcg|gram|tablet|pill|capsule)s?\b(?:\s+of\s+\w+)?",
            "[dosage removed]",
            text,
            flags=re.IGNORECASE,
        )
        # Strip "take X" medication advice
        text = re.sub(
            r"\b(?:take|خذ|خذي|تناول|تناولي)\s+\w+(?:\s+\d+)?",
            "[medication advice removed]",
            text,
            flags=re.IGNORECASE,
        )
        return text

    def ensure_disclaimer(self, text: str, is_emergency: bool = False) -> str:
        """Append the appropriate disclaimer if not already present."""
        disclaimer = EMERGENCY_DISCLAIMER if is_emergency else DISCLAIMER
        if disclaimer in text:
            return text
        return f"{text}\n\n{disclaimer}"

    def needs_uncertainty(self, response_text: str) -> bool:
        """True when the text makes confident claims without hedging language."""
        has_confident_claim = bool(_DIAGNOSIS_RE.search(response_text))
        has_hedging = bool(_HEDGING_RE.search(response_text))
        return has_confident_claim and not has_hedging

    def apply_uncertainty_if_needed(self, text: str) -> str:
        """Prepend the uncertainty notice when the response lacks hedging."""
        if self.needs_uncertainty(text):
            return f"{UNCERTAINTY_TEXT}\n\n{text}"
        return text

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_red_flags(query: str) -> _RedFlagPattern | None:
        """Return the first matching compound red-flag pattern, or None."""
        lower = query.lower()
        for pattern in _RED_FLAG_PATTERNS:
            a_hit = any(t.lower() in lower for t in pattern.triggers_a)
            b_hit = any(t.lower() in lower for t in pattern.triggers_b)
            if a_hit and b_hit:
                return pattern
        return None

    @staticmethod
    def is_emergency_violation(result: GuardrailResult) -> bool:
        """True when the guardrail result requires immediate emergency escalation."""
        return result.force_red or result.violation_type in (
            ViolationType.EMERGENCY_RED_FLAG,
            ViolationType.SUICIDAL_IDEATION,
        )
