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
    SCOPE_MEDICATION = "scope_medication"
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
    "\u0631\u0636\u064a\u0639",  # رضيع
    "\u0631\u0636\u064a\u0639\u0629",  # رضيعة
    "infant",
    "newborn",
    "2 months old",
    "6 months old",
    "1 year old",
    "18 months old",
    "under 2 years",
    "less than 2 years",
    "baby under 2",
]
_INFANT_RE = re.compile(
    "|".join(re.escape(s) for s in _INFANT_SUBSTRINGS), re.IGNORECASE
)

# Arabic letters, used to fake word boundaries: Python's \b treats Arabic
# letters as word characters, but not the Lebanese prefixes glued onto words.
_AR = "\u0600-\u06ff"
_ARABIC_DIGITS = str.maketrans(
    "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669", "0123456789"
)

# A stated age in months ("3 months old", "عمرو 3 أشهر", "3emro 3 ashhor").
# Only an *age* counts: "pain for 3 months" must not block an adult.
_AGE_MONTHS_RE = re.compile(
    r"\b(\d{1,2})[\s-]*(?:months?|mos?)[\s-]*old\b"
    r"|(?:عمر|3emr|3omr|3mr)\w*\s*(\d{1,2})?\s*"
    r"(?:شهر|أشهر|اشهر|شهور|ashhor|ashhur|shhur|shahr|shaher)",
    re.IGNORECASE,
)
# One-year-olds and "two months" said as a dual form.
_INFANT_AGE_RE = re.compile(
    r"\b(?:[01](?:\.\d)?|one)[\s-]*(?:years?|yrs?|yo)[\s-]*old\b"
    r"|(?:عمر)\S*\s*(?:سنة|سنه|شهرين)(?![" + _AR + r"])"
    r"|(?:3emr|3omr|3mr)\w*\s*(?:sene|seneh|shahren|shahrein)\b"
    r"|(?<![" + _AR + r"])(?:مولود|مولودة|بيبي)(?![" + _AR + r"])"
    r"|\b(?:my|our)\s+baby\b",
    re.IGNORECASE,
)


def _is_infant(query: str) -> bool:
    """True when the query is about a child under two."""
    if _INFANT_RE.search(query) or _INFANT_AGE_RE.search(query):
        return True
    for m in _AGE_MONTHS_RE.finditer(query.translate(_ARABIC_DIGITS)):
        months = m.group(1) or m.group(2)
        # "عمرو أشهر" with no number still means a baby
        if months is None or int(months) < 24:
            return True
    return False


# Arabic terms are matched as whole words (allowing the و/ب/ال prefixes):
# as a bare substring "حمل" also matched "بتحمل" (I can bear) and "حملت"
# (I lifted), which turned back pain from lifting into a pregnancy refusal.
_PREGNANCY_RE = re.compile(
    r"(?<![" + _AR + r"])(?:[وب]?(?:ال)?)(?:حامل|حاملة|حبلى|حبلة|حمل)(?![" + _AR + r"])"
    r"|\b(?:pregnant|pregnancy|contractions|water broke|preeclampsia|hamil|7amel|7amle)\b",
    re.IGNORECASE,
)

_LAB_SUBSTRINGS = [
    "\u0646\u062a\u064a\u062c\u0629 \u062a\u062d\u0644\u064a\u0644",  # نتيجة تحليل
    "\u062a\u062d\u0627\u0644\u064a\u0644 \u0637\u0644\u0639\u062a",  # تحاليل طلعت
    "\u0646\u062a\u064a\u062c\u0629 \u0635\u0648\u0631\u0629",  # نتيجة صورة
    "\u0635\u0648\u0631\u0629 \u0623\u0634\u0639\u0629",  # صورة أشعة
    "lab result",
    "blood test result",
    "test result",
    "x-ray result",
    "mri result",
    "ct scan result",
    "ultrasound result",
    "ecg result",
    "biopsy result",
    "my results show",
    "my tests show",
    "natijet tahlil",
]
_LAB_RE = re.compile("|".join(re.escape(s) for s in _LAB_SUBSTRINGS), re.IGNORECASE)

# ---- Suicidal ideation (single-trigger, highest priority) ------------------

_SUICIDAL_SUBSTRINGS = [
    "\u0628\u062f\u064a \u0645\u0648\u062a",  # بدي موت
    "\u0628\u062f\u064a \u0642\u062a\u0644 \u062d\u0627\u0644\u064a",  # بدي قتل حالي
    "\u0645\u0627 \u0628\u062f\u064a \u0639\u064a\u0634",  # ما بدي عيش
    "\u0627\u0646\u062a\u062d\u0627\u0631",  # انتحار
    "kill myself",
    "end my life",
    "suicide",
    "want to die",
    "no reason to live",
    "better off dead",
    "baddi mout",
]
_SUICIDAL_RE = re.compile(
    "|".join(re.escape(s) for s in _SUICIDAL_SUBSTRINGS), re.IGNORECASE
)

# ---- Overdose / poisoning (single-trigger emergency) ----------------------

_OVERDOSE_RE = re.compile(
    r"\boverdos(?:e|ed|ing)\b"
    r"|\b(?:took|swallowed|ate)\s+(?:too\s+many|a\s+lot\s+of|a\s+whole\s+(?:bottle|box|pack)\s+of)\s+\w+"
    r"|\bpoison(?:ed|ing)?\b"
    r"|جرعة زايدة|جرعة زائدة|تسمم|(?:بلعت|أخدت|اخدت|اخذت)\s+(?:حبوب|دوا|ادوية|أدوية)\s+(?:كتير|كثير)",
    re.IGNORECASE,
)

# ---- Requests for medication names or doses ------------------------------

_MEDICATION_REQUEST_RE = re.compile(
    r"\b(?:what|which|how\s+much|how\s+many)\b[^.?!]{0,40}\b(?:dose|dosage|mg|pills?|tablets?|medicine|medication|drug)s?\b"
    r"|\b(?:dose|dosage)\s+of\b"
    r"|\bshould\s+i\s+take\b"
    r"|\bwhat\s+(?:can|should)\s+i\s+take\b"
    r"|جرعة|(?:شو|أي|اي|ايا)\s+(?:دوا|دواء)|قديش\s+(?:حبة|حبات|حبوب)|شو\s+باخد"
    r"|\bshu\s+(?:dawa|bekhod|bokhod)\b|\b2adde(?:sh|ch)\s+7ab",
    re.IGNORECASE,
)

# ---- Compound red-flag patterns (require TWO symptom groups) ---------------

_RED_FLAG_PATTERNS: list[_RedFlagPattern] = [
    # MI / Cardiac
    _RedFlagPattern(
        name="cardiac_mi",
        triggers_a=[
            "chest pain",
            "waja3 sadr",
            "chest tightness",
            "chest pressure",
            "\u0623\u0644\u0645 \u0635\u062f\u0631",  # ألم صدر
            "\u0648\u062c\u0639 \u0635\u062f\u0631",  # وجع صدر
            "وجع بصدري",
            "وجع بالصدر",
            "ألم بالصدر",
            "ألم في الصدر",
        ],
        triggers_b=[
            "arm numbness",
            "arm pain",
            "left arm",
            "jaw pain",
            "jaw numbness",
            "shoulder pain",
            "shoulder numbness",
            "radiating",
            "\u062e\u062f\u0631 \u064a\u062f",  # خدر يد
            "\u0630\u0631\u0627\u0639",  # ذراع
            "دراع",  # arm, Lebanese spelling
            "\u0643\u062a\u0641",  # كتف
            # فك (jaw) is matched as a whole word in _check_red_flags: as a
            # substring it hit "بفكر" (I think) and "فكرة" (idea).
        ],
    ),
    # Anaphylaxis
    _RedFlagPattern(
        name="anaphylaxis",
        triggers_a=[
            "throat swelling",
            "swollen throat",
            "can't swallow",
            "hives",
            "allergic reaction",
            "anaphylaxis",
            "\u062a\u0648\u0631\u0645 \u0632\u0648\u0631",  # تورم زور
            "\u062d\u0633\u0627\u0633\u064a\u0629 \u0634\u062f\u064a\u062f\u0629",  # حساسية شديدة
        ],
        triggers_b=[
            "difficulty breathing",
            "can't breathe",
            "cant breathe",
            "shortness of breath",
            "throat closing",
            "\u0635\u0639\u0648\u0628\u0629 \u062a\u0646\u0641\u0633",  # صعوبة تنفس
            "\u0636\u064a\u0642 \u062a\u0646\u0641\u0633",  # ضيق تنفس
        ],
    ),
    # Head trauma
    _RedFlagPattern(
        name="head_trauma",
        triggers_a=[
            "head injury",
            "hit my head",
            "hit head",
            "head trauma",
            "fell and hit",
            "bang on head",
            "\u0636\u0631\u0628\u062a \u0631\u0627\u0633\u064a",  # ضربت راسي
            "\u0648\u0642\u0639\u062a \u0639\u0644\u0649 \u0631\u0627\u0633\u064a",  # وقعت على راسي
            "darabt rasi",
            "اصطدم راسي",  # my head struck (something)
            "خبطت راسي",  # I banged my head
            "انضرب راسي",  # my head got hit
            "wa2a3t 3ala rasi",
        ],
        triggers_b=[
            "vomiting",
            "throwing up",
            "unconscious",
            "lost consciousness",
            "confusion",
            "blurred vision",
            "seizure",
            "بتقي",  # vomiting (Lebanese)
            "استفرغ",  # vomit
            "صداع شديد",  # severe headache
            "بشوف مش منيح",  # can't see properly
            "2a2ayt",
            "ste3ta2",
            "\u0631\u062c\u0651\u0639",  # رجّع
            "\u0636\u064a\u0627\u0639 \u0648\u0639\u064a",  # ضياع وعي
        ],
    ),
]

# "فك" (jaw) as a whole word, with or without the و/ب/ال prefixes.
_JAW_RE = re.compile(r"(?<![" + _AR + r"])(?:[وب]?(?:ال)?)فك(?:ي)?(?![" + _AR + r"])")

# ---- Medication / dosage detection in LLM output --------------------------

_DOSAGE_RE = re.compile(
    r"\b\d+\s*(?:mg|ml|mcg|microgram|gram|tablet|pill|dose|capsule)s?\b",
    re.IGNORECASE,
)

_DRUG_NAMES = (
    r"(?:"
    r"ibuprofen|paracetamol|acetaminophen|aspirin|amoxicillin|"
    r"metformin|atorvastatin|omeprazole|diazepam|tramadol|"
    r"codeine|morphine|warfarin|prednisone|methotrexate|"
    r"panadol|advil|brufen|xanax|alprazolam|"
    r"[a-z]{4,}(?:cillin|mycin|oxacin|statin|prazole|sartan|dipine|olol)"
    r")"
)
_DRUG_RE = re.compile(r"\b" + _DRUG_NAMES + r"\b", re.IGNORECASE)

# "take" only counts as medication advice when a drug follows it; matching
# any word turned "take a rest" into "[medication advice removed] rest".
_TAKE_DRUG_RE = re.compile(
    r"\b(?:take|خذ|خذي|تناول|تناولي)\s+(?:some\s+|an?\s+)?" + _DRUG_NAMES + r"\b",
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
    r"\u064a\u0645\u0643\u0646|\u064a\u0628\u062f\u0648"  # يمكن يبدو
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
    "I'm not certain about this case. Please consult a doctor for a proper evaluation."
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
        "I'm very concerned about you. Please call the Embrace Lifeline on 1564 "
        "(emotional support and suicide prevention in Lebanon) or go to the "
        "nearest emergency room right now. If you are in immediate danger, call "
        "the Red Cross on 140. You are not alone, and help is available."
    ),
    ViolationType.SCOPE_MEDICATION: (
        "I can't recommend medications or doses. Please ask a pharmacist or "
        "your doctor. If you took too much of a medicine, go to the ER or call "
        "the Red Cross on 140 now."
    ),
}

# Same messages for patients writing in Arabic script or Franco-Arab.  Refusals
# in English were landing on people who had written to Hakim in Arabic.
_REJECTION_AR: dict[ViolationType, str] = {
    ViolationType.SCOPE_INFANT: (
        "ما بقدر قيّم حالة ولاد عمرن أقل من سنتين. "
        "خود الطفل عند دكتور الأطفال أو عالطوارئ فوراً."
    ),
    ViolationType.SCOPE_PREGNANCY: (
        "ما بقدر إعطي نصيحة عن مضاعفات الحمل. "
        "اتصلي بدكتورة النسائية أو روحي على أقرب قسم ولادة."
    ),
    ViolationType.SCOPE_LAB_RESULTS: (
        "ما بقدر إقرا نتائج التحاليل أو الصور أو التقارير الطبية. "
        "ناقشها مباشرة مع دكتورك."
    ),
    ViolationType.EMERGENCY_RED_FLAG: (
        "هالأعراض ممكن تكون حالة طارئة. "
        "اتصل بالصليب الأحمر على 140 أو روح عالطوارئ هلق. ما تستنى."
    ),
    ViolationType.SUICIDAL_IDEATION: (
        "أنا كتير قلقان عليك. اتصل بخط الحياة من Embrace على 1564 "
        "(دعم نفسي والوقاية من الانتحار بلبنان) أو روح على أقرب طوارئ هلق. "
        "إذا إنت بخطر فوري، اتصل بالصليب الأحمر على 140. "
        "إنت مش لحالك، وفي حدا بيقدر يساعدك."
    ),
    ViolationType.SCOPE_MEDICATION: (
        "ما بقدر إنصح بأدوية أو جرعات. اسأل الصيدلي أو دكتورك. "
        "إذا أخدت دوا أكتر من اللازم، روح عالطوارئ أو اتصل بالصليب الأحمر على 140 هلق."
    ),
}

_REJECTION_FRANCO: dict[ViolationType, str] = {
    ViolationType.SCOPE_INFANT: (
        "ma ba2der 2ayyem 7alet wled 3omron a2al men sentein. "
        "khod l walad 3and doctor l atfal aw 3al taware2 fawran."
    ),
    ViolationType.SCOPE_PREGNANCY: (
        "ma ba2der a3te nasi7a 3an mada3afet l 7aml. "
        "ettesle b doctora l nisa2iye aw ru7e 3a a2rab 2esm wilade."
    ),
    ViolationType.SCOPE_LAB_RESULTS: (
        "ma ba2der e2ra nata2ej l ta7alil aw l suwar aw l ta2arir l tebbiye. "
        "7ke fiyon ma3 l doctor."
    ),
    ViolationType.EMERGENCY_RED_FLAG: (
        "hal a3rad momken tkun 7ale tar2a. "
        "ettesel bel Salib l A7mar 3ala 140 aw ru7 3al taware2 hala2. ma testanna."
    ),
    ViolationType.SUICIDAL_IDEATION: (
        "ana ktir 2al2an 3alek. ettesel b khatt l 7aya men Embrace 3ala 1564 "
        "aw ru7 3a a2rab taware2 hala2. eza enta b khatar fawre, ettesel bel "
        "Salib l A7mar 3ala 140. enta msh la7alak, w fi 7ada fi ysa3dak."
    ),
    ViolationType.SCOPE_MEDICATION: (
        "ma ba2der ense7 b adwye aw jora3at. es2al l saydale aw l doctor. "
        "eza akhadt dawa aktar men l lezem, ru7 3al taware2 aw ettesel bel "
        "Salib l A7mar 3ala 140 hala2."
    ),
}

_DISCLAIMER_AR = (
    "\u26a0\ufe0f هيدي المعلومات ما بتغني عن الدكتور. إذا الأعراض ساءت، روح عالطبيب."
)
_EMERGENCY_DISCLAIMER_AR = "\U0001f6a8 هالأعراض بدها عناية طارئة فوراً. اتصل بالصليب الأحمر على 140 أو روح عالطوارئ هلق."
_DISCLAIMER_FRANCO = (
    "haydi l ma3lumet ma bteghne 3an l doctor. eza l a3rad sa2et, ru7 3al tabib."
)
_EMERGENCY_DISCLAIMER_FRANCO = "hal a3rad badda 3inaye tar2a fawran. ettesel bel Salib l A7mar 3ala 140 aw ru7 3al taware2 hala2."

_ALEF_FORMS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا"})


def _fold_alef(text: str) -> str:
    """Fold hamza/madda alef forms to a bare alef.

    Spelling of these varies freely in everyday Arabic, and a pattern written
    with one form silently missed the other: "أفكار إنتحارية" (suicidal
    thoughts) slipped past the "انتحار" rule.
    """
    return text.translate(_ALEF_FORMS)


_ARABIC_LETTER_RE = re.compile("[\u0621-\u064a]")


def detect_script(text: str) -> str:
    """Guess how a patient writes: "arabic" (Arabic script) or "english".

    Franco-Arab can't be told apart from English reliably, so callers that know
    the user picked Franco should pass that explicitly instead.
    """
    return "arabic" if _ARABIC_LETTER_RE.search(text) else "english"


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
          2. Overdose/poisoning (force RED)
          3. Scope: infant      (send to pediatrician)
          4. Scope: pregnancy   (send to OB/GYN)
          5. Scope: lab results (refer to doctor)
          6. Compound emergency red flags (force RED)
          7. Scope: medication or dose requests (refer to pharmacist)

        Infant and pregnancy refusals escalate to RED: their replies send the
        patient to the ER or maternity unit immediately, and the badge should
        agree with that.  Every rule is also checked against the query with
        hamza forms folded (see _fold_alef), since patients write "إنتحار" and
        "انتحار" interchangeably.
        """
        folded = _fold_alef(query)
        if folded != query:
            query = f"{query}\n{folded}"
        if _SUICIDAL_RE.search(query):
            return GuardrailResult(
                is_safe=False,
                violation_type=ViolationType.SUICIDAL_IDEATION,
                rejection_message=_REJECTION[ViolationType.SUICIDAL_IDEATION],
                force_red=False,
            )
        if _OVERDOSE_RE.search(query):
            return GuardrailResult(
                is_safe=False,
                violation_type=ViolationType.EMERGENCY_RED_FLAG,
                rejection_message=_REJECTION[ViolationType.EMERGENCY_RED_FLAG],
                force_red=True,
            )
        if _is_infant(query):
            return GuardrailResult(
                is_safe=False,
                violation_type=ViolationType.SCOPE_INFANT,
                rejection_message=_REJECTION[ViolationType.SCOPE_INFANT],
                force_red=True,
            )
        if _PREGNANCY_RE.search(query):
            return GuardrailResult(
                is_safe=False,
                violation_type=ViolationType.SCOPE_PREGNANCY,
                rejection_message=_REJECTION[ViolationType.SCOPE_PREGNANCY],
                force_red=True,
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
        if _MEDICATION_REQUEST_RE.search(query):
            return GuardrailResult(
                is_safe=False,
                violation_type=ViolationType.SCOPE_MEDICATION,
                rejection_message=_REJECTION[ViolationType.SCOPE_MEDICATION],
            )
        return GuardrailResult(is_safe=True)

    def format_rejection(self, result: GuardrailResult, script: str = "english") -> str:
        """The reply for a blocked query, in the patient's language.

        ``script`` is "arabic", "franco" or "english".  A crisis referral gets no
        extra disclaimer: its message already carries the helpline numbers, and
        the physical-emergency warning read as off-key next to it.
        """
        vt = result.violation_type
        table = {"arabic": _REJECTION_AR, "franco": _REJECTION_FRANCO}.get(
            script, _REJECTION
        )
        message = table.get(vt) if vt is not None else None
        message = message or result.rejection_message or ""
        if vt == ViolationType.SUICIDAL_IDEATION:
            return message
        return self.ensure_disclaimer(
            message, is_emergency=self.is_emergency_violation(result), script=script
        )

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
        # Strip "take <drug>" advice, then any drug name left on its own
        text = _TAKE_DRUG_RE.sub("[medication advice removed]", text)
        text = _DRUG_RE.sub("[medication removed]", text)
        return text

    def ensure_disclaimer(
        self, text: str, is_emergency: bool = False, script: str = "english"
    ) -> str:
        """Append the appropriate disclaimer if not already present."""
        if script == "arabic":
            disclaimer = _EMERGENCY_DISCLAIMER_AR if is_emergency else _DISCLAIMER_AR
        elif script == "franco":
            disclaimer = (
                _EMERGENCY_DISCLAIMER_FRANCO if is_emergency else _DISCLAIMER_FRANCO
            )
        else:
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
        jaw = bool(_JAW_RE.search(query))
        for pattern in _RED_FLAG_PATTERNS:
            a_hit = any(t.lower() in lower for t in pattern.triggers_a)
            b_hit = any(t.lower() in lower for t in pattern.triggers_b) or (
                jaw and pattern.name == "cardiac_mi"
            )
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
