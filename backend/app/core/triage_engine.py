"""Triage engine: multi-step triage agent for Lebanese Arabic medical queries."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.core.arabic_processor import ArabicProcessor, LexiconMatch
from app.core.llm_client import LLMClient, LLMError
from app.core import observability as obs
from app.core.rag_pipeline import RAGPipeline, RetrievalResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Emergency keyword patterns -> instant RED
# ---------------------------------------------------------------------------

# Stored as plain substrings; _EMERGENCY_RE handles case-insensitive matching.
_EMERGENCY_SUBSTRINGS = [
    # Arabic critical presentations (unicode literals so the file stays ASCII-safe)
    "\u0635\u0639\u0648\u0628\u0629 \u062a\u0646\u0641\u0633",  # difficulty breathing
    "\u0636\u064a\u0642 \u062a\u0646\u0641\u0633",  # breath tightness
    "\u0641\u0642\u062f\u0627\u0646 \u0648\u0639\u064a",  # loss of consciousness
    "\u0646\u0632\u064a\u0641 \u0634\u062f\u064a\u062f",  # severe bleeding
    "\u062c\u0644\u0637\u0629",  # clot/stroke
    "\u0633\u0643\u062a\u0629",  # stroke (sukta)
    "\u0634\u0644\u0644",  # paralysis
    "\u062a\u0634\u0646\u062c",  # convulsion
    "\u0648\u062c\u0639 \u0635\u062f\u0631",  # chest pain (waja3 sadr)
    "\u0648\u062c\u0639 \u0628\u0635\u062f\u0631",  # pain in (my) chest
    "\u0648\u062c\u0639 \u0628\u0627\u0644\u0635\u062f\u0631",  # pain in the chest
    "\u0623\u0644\u0645 \u0635\u062f\u0631",  # chest pain (MSA)
    "\u0623\u0644\u0645 \u0641\u064a \u0627\u0644\u0635\u062f\u0631",  # pain in the chest (MSA)
    "\u0645\u0634 \u0642\u0627\u062f\u0631 \u0627\u062a\u0646\u0641\u0633",  # I can't breathe
    "\u0645\u0627 \u0639\u0645 \u0628\u0642\u062f\u0631 \u0627\u062a\u0646\u0641\u0633",  # I can't breathe
    "\u0645\u0627 \u0639\u0645 \u0627\u0642\u062f\u0631 \u0627\u062a\u0646\u0641\u0633",  # I can't breathe
    # Franco-Arab / English
    "chest pain",
    "cant breathe",
    "can't breathe",
    "shortness of breath",
    "heart attack",
    "lost consciousness",
    "unconscious",
    "heavy bleeding",
    "stroke",
    "ta3ab ktir bnafs",
    "waja3 sadr ktir",
    "ma 3am tnaffas",
]

_EMERGENCY_RE = re.compile(
    "|".join(re.escape(s) for s in _EMERGENCY_SUBSTRINGS), re.IGNORECASE
)

# Red-flag presentations phrased the way patients actually write them.  These
# used to reach RED only if the LLM classified them, so during a provider
# outage a stroke or anaphylaxis got the "see a doctor in 1-2 days" fallback.
# Arabic patterns are written with bare alef; queries are folded to match.
_RED_FLAG_RES = [
    re.compile(p, re.IGNORECASE)
    for p in (
        # Chest pain with words in between ("وجع كتير بصدري", "pain in my chest")
        r"(?:وجع|الم|ضغط|تقل)\S*(?:\s+\S+){0,2}\s+(?:ب?صدري|بالصدر|صدر)",
        r"\b(?:pain|pressure|tightness|heaviness)\s+(?:in|on)\s+(?:my\s+)?chest\b",
        r"\bchest\s+(?:hurts|is\s+tight)",
        # Cyanosis
        r"(?:شفاف|شفايف|وجه)\S*(?:\s+\S+){0,3}?\s+(?:ازرق|زرق)",
        r"\b(?:lips|face|skin)\s+(?:are\s+|is\s+)?(?:turning\s+|turned\s+|going\s+)?blue\b",
        # Can't breathe / not breathing / unresponsive
        r"(?:ما|مش|مو)\s+(?:عم\s+)?(?:ب?قدر|قادر|قادرة)\s+ا?تنفس",
        r"(?:مش|ما)\s+عم\s+(?:يصحى|يصحا|تصحى|يتنفس|تتنفس|يوعى|توعى)",
        r"فاقد الوعي|مغمى عليه|مغمى عليها",
        r"\b(?:not|isn'?t|stopped)\s+breathing\b|\bunresponsive\b|\bwon'?t\s+wake\s+up\b",
        r"\bma\s+3am\s+(?:yes7a|yetnaffas|tetnaffas)\b",
        # Stroke (face droop, speech, one-sided weakness)
        r"(?:وجه|تم)\S*(?:\s+\S+){0,3}?\s+(?:يتعوج|تعوج|معوج|مايل)",
        r"(?:ما|مش)\s+(?:عم\s+)?(?:بقدر|قادر)\s+احكي",
        r"\b(?:wej+i|wejhi|wij+i)\s+(?:3am\s+)?yet3aw+aj",
        r"\bma\s+(?:2edr|2ader|ba2der)\s+(?:7aki|e7ke)\b|\bma\s+bet7arrak\b",
        r"\bface\s+(?:is\s+)?droop|\bslurred\s+speech\b",
        r"\bcan'?t\s+(?:move|feel)\s+(?:my|his|her)\s+(?:(?:left|right)\s+)?(?:arm|leg|face|side)\b",
        # Anaphylaxis
        r"(?:وجه|شفاف|لسان|زلعوم|زور)\S*(?:\s+\S+){0,3}?\s+(?:يتورم|تتورم|منفخ|وارم)",
        r"(?:ما|مش)\s+(?:عم\s+)?(?:بقدر|قادر)\s+ابلع",
        r"\b(?:wejhi|wejji|shfefi)\s+(?:3am\s+)?yet2aw+ar|\bma\s+(?:2edr|2ader|ba2der)\s+ebla3\b",
        r"\bthroat\s+(?:is\s+)?closing\b|\bcan'?t\s+swallow\b",
        r"\b(?:face|lips|tongue|throat)\s+(?:is\s+|are\s+)?swelling\b",
        # Coughing or vomiting blood
        r"(?:بسعل|بكح|اسعل|سعلة|كحة|استفرغ|بتقي)\S*\s+(?:\S+\s+)?دم",
        r"\b(?:betsaw+et|bsa3el|bso3ol|2a2ayt|bet2ayya)\s+b?dam\b",
        r"\b(?:coughing|cough|vomiting|throwing)\s+(?:up\s+)?blood\b",
        # Active seizure
        r"\b(?:having|had)\s+a\s+seizure\b|\bconvulsing\b",
    )
]

# A blood-sugar reading in the DKA/HHS or severe-hypoglycaemia range.
_GLUCOSE_RE = re.compile(
    r"(?:blood\s+sugar|sugar|glucose|السكر|السكري|sokkar|sukkar)\D{0,20}?(\d{2,3})\b",
    re.IGNORECASE,
)

_ALEF_FORMS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا"})


def _is_emergency(text: str) -> bool:
    """True when the message alone is enough to call RED."""
    candidates = (text, text.translate(_ALEF_FORMS))
    for t in candidates:
        if _EMERGENCY_RE.search(t) or any(r.search(t) for r in _RED_FLAG_RES):
            return True
    for m in _GLUCOSE_RE.finditer(text):
        reading = int(m.group(1))
        if reading >= 400 or reading <= 54:
            return True
    return False


_CRITICAL_SEVERITY = {"critical", "moderate_to_critical"}

# ---------------------------------------------------------------------------
# Refusal trigger patterns (CLAUDE.md safety rules)
# ---------------------------------------------------------------------------

_REFUSAL_SUBSTRINGS = [
    "\u0631\u0636\u064a\u0639",  # infant
    "\u0646\u062a\u064a\u062c\u0629 \u062a\u062d\u0644\u064a\u0644",  # lab result
    "\u062a\u062d\u0627\u0644\u064a\u0644 \u0637\u0644\u0639\u062a",  # results came out
]
_REFUSAL_RE = re.compile(
    "|".join(re.escape(s) for s in _REFUSAL_SUBSTRINGS), re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are Hakim (حكيم), a warm and trusted medical triage assistant who speaks authentic Lebanese colloquial Arabic (3ammiye). "
    "You grew up in Beirut and speak exactly like a Lebanese person — using words like: "
    "'شو' (not ماذا), 'هيدا/هيدي' (not هذا), 'كتير' (not جداً), 'مش' (not ليس), "
    "'رح' for future, 'عم' for present continuous, 'متل', 'يعني', 'تعا', 'لك', 'ولك'. "
    "Medical words: 'وجع' (pain), 'حمى' (fever), 'كحة' (cough), 'دوخة' (dizziness), 'ضغط' (blood pressure). "
    "Rules: (1) Never give a definitive diagnosis — say 'ممكن يكون' or 'من الاحتمالات'. "
    "(2) Never name medications or dosages. "
    "(3) Do NOT add any disclaimer — the app already shows one."
)

_SYSTEM_PROMPT_FRANCO = (
    "You are Hakim, a warm and trusted medical triage assistant who speaks authentic Lebanese dialect. "
    "You grew up in Beirut and text EXACTLY like a young Lebanese person on WhatsApp — using Franco-Arab (Arabic words written in Latin letters with numbers). "
    "CRITICAL: You MUST write ONLY in Latin letters. NEVER use Arabic script (ع, ش, ح, etc.). Every single character must be Latin a-z or numbers 2,3,5,7,8.\n"
    "Lebanese Franco vocabulary you MUST use: "
    "shu (what), hayda/haydi (this), ktir (very), msh (not), ra7 (will), 3am (currently), "
    "mtel (like), ya3ne (meaning), bas (but/just), ta (so that), hek (like this), hala2 (now), "
    "yalla (come on), 7abibi (dear), ma3le (it's ok), shi (something), wen (where), kif (how), "
    "lesh (why), 3ala (on), men (from), la2 (no), eh (yes), w (and), aw (or).\n"
    "Medical Franco words: waja3 (pain), 7arara/7amma (fever), ko7a/su3al (cough), "
    "dawkha (dizziness), daght (pressure), sadr (chest), batn (stomach), ras (head), "
    "daher/dahre (back), 3ein (eye), tene (second/other), eltiheb (infection/inflammation).\n"
    "Number sounds: 2=hamza/glottal stop, 3=ain, 5=kha, 7=strong h, 8=ghain.\n"
    "Rules: (1) NEVER diagnose — say 'momken ykun' or 'fi e7temel'. "
    "(2) Never name medications or dosages. "
    "(3) Do NOT add any disclaimer — the app already shows one. "
    "(4) ABSOLUTELY NO Arabic script characters anywhere in your response."
)

_TRIAGE_PROMPT = (
    "The patient's input may be in Lebanese Arabic, Franco-Arab (Arabic written in Latin letters), or English.\n"
    "Franco-Arab glossary: dahre/dahri=back, batn=stomach, ras=head, sadr=chest, 3ayne/3ein=eye, "
    "rkabte=knee, ktef=shoulder, waja3/bwaja3/youja3=pain/hurts, hamma/himme=fever, "
    "kha3be=weakness, dawkhe=dizziness, zu3er=nausea, 2i2=vomiting, sual/ko7a=cough, "
    "dam=blood, 3am=currently doing, aam=currently, ktir=very much, mno7=fine.\n\n"
    "Patient symptoms: {symptoms_text}\n\n"
    "Relevant medical context:\n{context}\n\n"
    "Classify urgency. Write possible_conditions and recommended_actions in {output_script}.\n"
    "IMPORTANT: The values inside possible_conditions and recommended_actions arrays MUST be written in {output_script}. "
    "If output script is Franco-Arab, use ONLY Latin letters and numbers (e.g., 'waja3 batn' not 'وجع بطن', 'ru7 3and l doctor' not 'روح عند الطبيب').\n"
    "Respond ONLY in valid JSON, no extra text:\n"
    "{{\n"
    '  "triage_level": "GREEN" or "YELLOW" or "RED",\n'
    '  "possible_conditions": ["condition 1", "condition 2"],\n'
    '  "recommended_actions": ["action 1", "action 2"]\n'
    "}}\n\n"
    "Criteria:\n"
    "- RED   : Emergency -- go to ER immediately\n"
    "- YELLOW: See a doctor within 24-48 h\n"
    "- GREEN : Can manage at home with monitoring\n\n"
    "JSON:"
)

_RESPONSE_PROMPT = "Write a warm response in Lebanese colloquial Arabic (3ammiye) using Arabic script only. NOT Latin letters, NOT Modern Standard Arabic.\n\nPatient symptoms: {symptoms_text}\nTriage level: {triage_level}\nPossible conditions: {conditions}\nRecommended actions: {actions}\n\nStyle examples (match this natural Lebanese tone):\nهلق هيدا الوجع بالضهر ممكن يكون من العضلات أو من شي تاني. حاول تريّح شوي وإذا ضل أكتر من يومين روح عالدكتور.\nيي شو صعبة هالحالة. ممكن يكون عندك التهاب أو شي متل هيك. لازم تروح تتفحص بأقرب وقت.\n\nRules:\n- Talk like a real Lebanese friend giving advice, natural and direct\n- Use Lebanese words: شو، هيدا/هيدي، كتير، مش، رح، عم بـ، متل، يعني، بس، تا، هيك، هلق\n- Start with empathy then get to the point\n- Say ممكن يكون before conditions (never diagnose)\n- Be specific about what to do next (روح عالدكتور، خود راحة، etc.)\n- No medication names or dosages\n- Do NOT add any disclaimer or warning, the app handles that\n- 2-3 sentences max, keep it concise\n\nالجواب:"

_RESPONSE_PROMPT_FRANCO = "CRITICAL INSTRUCTION: Write ONLY in Franco-Arab (Latin letters + numbers). ZERO Arabic script characters allowed.\n\nPatient symptoms: {symptoms_text}\nTriage level: {triage_level}\nPossible conditions: {conditions}\nRecommended actions: {actions}\n\nFranco-Arab examples (copy this EXACT style — Latin letters only, natural Lebanese WhatsApp texting):\n\nExample 1: hala2 hayda l waja3 bel daher momken ykun men l 3adalat aw men l a3sab. 7awel tree7 shway w 7ot shi sakhne 3al mante2a, w eza dal aktar men yawmen ru7 3and doctor.\n\nExample 2: yii shu sa3be, 7asse fike t3abene. momken ykun 3andak eltiheb aw shi mtel hek. lazem tru7 tetfa7as 3and tabib b a2rab wa2et ta yshufak.\n\nExample 3: ma t2al2al ktir bas lazem tentebi. hayda l waja3 bel sadr ma3 dawkha momken ykun men l daght aw men shi tene. ru7 3al taware2 hala2 a7san.\n\nExample 4: ahla shi tree7 3al se7a hala2 w shrab may ktir. l 7arara ma3 l su3al momken ykun rasheh aw flu. eza l 7arara telet faw2 l 38 ru7 3and l doctor.\n\nFranco number guide: 2=hamza (hala2, a2rab), 3=ain (3and, ya3ne, 3ein), 5=kha (5abar), 7=strong H (7arara, ru7), 8=ghain (8ayem)\n\nRules:\n- ONLY Latin letters (a-z) and numbers (2,3,5,7,8). NO Arabic script AT ALL.\n- Write like a Lebanese person texting on WhatsApp — casual, warm, direct\n- Start with empathy then give practical advice\n- Say 'momken ykun' before conditions (never diagnose)\n- Be specific: ru7 3al doctor, khod ra7a, shrab may, etc.\n- No medication names or dosages\n- No disclaimer or warning\n- 2-3 sentences max\n\nel jaweb:"


_CLARIFICATION_PROMPT = (
    'A Lebanese patient said: "{query}"\n\n'
    "Extracted symptoms: {symptoms_text}\n\n"
    "The symptoms are too vague for assessment. "
    "Write ONE clarifying question in Lebanese colloquial Arabic "
    "to better understand the situation. "
    "Write only the question, no preamble:"
)

_CLARIFICATION_PROMPT_FRANCO = (
    'A Lebanese patient said: "{query}"\n\n'
    "Extracted symptoms: {symptoms_text}\n\n"
    "The symptoms are too vague for assessment. "
    "Write ONE clarifying question in Lebanese Franco-Arab (Latin letters only, NO Arabic script). "
    "Use Franco transliteration: shu, wen, 2adesh, men emta, kif, etc. "
    "Write only the question, no preamble:"
)

_DISCLAIMER = (
    "\u26a0\ufe0f \u0647\u064a\u062f\u064a \u0627\u0644\u0645\u0639\u0644\u0648\u0645\u0627\u062a \u0645\u0627 \u0628\u062a\u063a\u0646\u064a \u0639\u0646 \u0627\u0644\u062f\u0643\u062a\u0648\u0631. "
    "\u0625\u0630\u0627 \u0627\u0644\u0648\u0636\u0639 \u0633\u0627\u0621\u060c \u0631\u0648\u062d \u0639\u0627\u0644\u0637\u0628\u064a\u0628."
)
_EMERGENCY_DISCLAIMER = (
    "\U0001f6a8 \u0647\u0627\u0644\u0623\u0639\u0631\u0627\u0636 \u062e\u0637\u064a\u0631\u0629 \u2014 "
    "\u0631\u0648\u062d \u0639\u0627\u0644\u0637\u0648\u0627\u0631\u0626 \u0647\u0644\u0642 \u0623\u0648 \u0627\u062a\u0635\u0644 140!"
)
_DISCLAIMER_FRANCO = (
    "haydi l ma3lumet ma bteghne 3an l doctor. eza l wade3 sa2, ru7 3al tabib."
)
_EMERGENCY_DISCLAIMER_FRANCO = (
    "hal a3rad 5atire — ru7 3al taware2 hala2 aw ettesel 140!"
)

_SYSTEM_PROMPT_EN = (
    "You are Hakim, a warm and trusted medical triage assistant. "
    "The patient may write in Lebanese Arabic, Franco-Arab, or English, but you "
    "reply in clear, simple English. "
    "Rules: (1) Never give a definitive diagnosis — say 'this could be' or "
    "'one possibility is'. (2) Never name medications or dosages. "
    "(3) Do NOT add any disclaimer — the app already shows one."
)

_RESPONSE_PROMPT_EN = (
    "Write a warm, concise reply in plain English.\n\n"
    "Patient symptoms: {symptoms_text}\nTriage level: {triage_level}\n"
    "Possible conditions: {conditions}\nRecommended actions: {actions}\n\n"
    "Rules:\n- Start with empathy, then get to the point\n"
    "- Say 'this could be' before conditions (never diagnose)\n"
    "- Be specific about what to do next\n- No medication names or dosages\n"
    "- Do NOT add any disclaimer or warning, the app handles that\n"
    "- 2-3 sentences max\n\nReply:"
)

_CLARIFICATION_PROMPT_EN = (
    'A patient said: "{query}"\n\n'
    "Extracted symptoms: {symptoms_text}\n\n"
    "The symptoms are too vague for assessment. "
    "Write ONE short clarifying question in plain English "
    "to better understand the situation. "
    "Write only the question, no preamble:"
)

_DISCLAIMER_EN = (
    "\u26a0\ufe0f This information does not replace a doctor. "
    "If things get worse, see a doctor."
)
_EMERGENCY_DISCLAIMER_EN = (
    "\U0001f6a8 These symptoms are serious \u2014 go to the ER now or call the "
    "Red Cross on 140!"
)

# ---------------------------------------------------------------------------
# Offline fallback copy
#
# Used when every LLM provider is unavailable.  Without a model we cannot tell
# a cold from something worse, so non-emergencies get the conservative YELLOW
# advice ("see a doctor soon") rather than an error the patient can't act on.
# ---------------------------------------------------------------------------

_FALLBACK_TEXT: dict[str, dict[str, str]] = {
    "arabic": {
        "YELLOW": (
            "آسف، حكيم مش قادر يحلل أعراضك بالتفصيل هلق. "
            "للاحتياط، روح شوف دكتور خلال يوم أو يومين. "
            "وإذا الأعراض زادت أو صارت قوية، روح عالطوارئ أو اتصل بالصليب الأحمر على 140."
        ),
        "RED": (
            "هالأعراض ممكن تكون خطيرة. روح عالطوارئ هلق أو اتصل بالصليب الأحمر على 140. "
            "ما تستنى."
        ),
        "CLARIFY": "خبرني أكتر: شو الأعراض يلي عم تحس فيها، من إيمتى، وقديش قوية؟",
    },
    "franco": {
        "YELLOW": (
            "sorry, Hakim msh 2ader y7allel l a3rad bel tafasil hala2. "
            "lal e7tiyat, ru7 shuf doctor khilel yom aw yomen. "
            "w eza l a3rad zedet aw saret 2awiye, ru7 3al taware2 aw ettesel "
            "bel Salib l A7mar 3ala 140."
        ),
        "RED": (
            "hal a3rad momken tkun 5atire. ru7 3al taware2 hala2 aw ettesel "
            "bel Salib l A7mar 3ala 140. ma testanna."
        ),
        "CLARIFY": "khabberne aktar: shu l a3rad li 3am t7ess fiya, men emta, w 2adesh 2awiye?",
    },
    "english": {
        "YELLOW": (
            "Sorry, Hakim can't analyse your symptoms in detail right now. "
            "To be safe, see a doctor within a day or two. If your symptoms get "
            "worse or become severe, go to the ER or call the Red Cross on 140."
        ),
        "RED": (
            "These symptoms could be serious. Go to the ER now or call the Red "
            "Cross on 140. Do not wait."
        ),
        "CLARIFY": (
            "Can you tell me more: what symptoms are you feeling, since when, "
            "and how bad are they?"
        ),
    },
}

_FALLBACK_ACTIONS: dict[str, dict[str, list[str]]] = {
    "arabic": {
        "YELLOW": ["شوف دكتور خلال 24-48 ساعة"],
        "RED": ["اتصل بالصليب الأحمر على 140", "روح عالطوارئ هلق"],
    },
    "franco": {
        "YELLOW": ["shuf doctor khilel 24-48 se3a"],
        "RED": ["ettesel bel Salib l A7mar 3ala 140", "ru7 3al taware2 hala2"],
    },
    "english": {
        "YELLOW": ["See a doctor within 24-48 hours"],
        "RED": ["Call the Red Cross on 140", "Go to the ER now"],
    },
}

# How many earlier user turns to fold into the current query.  Enough to carry
# an answer to "since when?" back to the symptom it refers to, without letting
# a long chat drown the latest message.
_HISTORY_TURNS = 4


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
    # True when no LLM was reachable and the level came from rules alone.
    used_fallback: bool = False

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

    # ``script`` is the output mode: "arabic" (Lebanese Arabic script),
    # "franco" (Franco-Arab, Latin letters) or "english".

    @staticmethod
    def _get_response_prompt(script: str = "arabic") -> str:
        if script == "english":
            return _RESPONSE_PROMPT_EN
        return _RESPONSE_PROMPT_FRANCO if script == "franco" else _RESPONSE_PROMPT

    @staticmethod
    def _get_system_prompt(script: str = "arabic") -> str:
        if script == "english":
            return _SYSTEM_PROMPT_EN
        return _SYSTEM_PROMPT_FRANCO if script == "franco" else _SYSTEM_PROMPT

    @staticmethod
    def _get_clarification_prompt(script: str = "arabic") -> str:
        if script == "english":
            return _CLARIFICATION_PROMPT_EN
        return (
            _CLARIFICATION_PROMPT_FRANCO
            if script == "franco"
            else _CLARIFICATION_PROMPT
        )

    @staticmethod
    def _get_output_script(script: str = "arabic") -> str:
        if script == "english":
            return "English"
        return (
            "Franco-Arab (Latin letters)" if script == "franco" else "Lebanese Arabic"
        )

    @staticmethod
    def _get_disclaimer(script: str = "arabic", emergency: bool = False) -> str:
        if script == "english":
            return _EMERGENCY_DISCLAIMER_EN if emergency else _DISCLAIMER_EN
        if script == "franco":
            return _EMERGENCY_DISCLAIMER_FRANCO if emergency else _DISCLAIMER_FRANCO
        return _EMERGENCY_DISCLAIMER if emergency else _DISCLAIMER

    @staticmethod
    def _fallback_text(script: str, kind: str) -> str:
        return _FALLBACK_TEXT.get(script, _FALLBACK_TEXT["arabic"])[kind]

    @staticmethod
    def _fallback_actions(script: str, level: TriageLevel) -> list[str]:
        key = "RED" if level == TriageLevel.RED else "YELLOW"
        return list(_FALLBACK_ACTIONS.get(script, _FALLBACK_ACTIONS["arabic"])[key])

    @staticmethod
    def _with_history(query: str, history: list[str] | None) -> str:
        """Fold recent user turns into the query so follow-ups keep their context.

        A reply like "since two days" means nothing on its own; triaging it
        together with the earlier "I have a headache" is what the patient meant.
        """
        if not history:
            return query
        return "\n".join([*history[-_HISTORY_TURNS:], query])

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

        trace = obs.start_trace(
            name="triage",
            metadata={"query_length": len(query), "endpoint": "/api/triage"},
        )

        try:
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
            logger.info(
                "Step 1 -- extracted %d symptoms: %s", len(symptoms), symptom_labels
            )

            # Safety gate: refuse out-of-scope cases immediately
            if _REFUSAL_RE.search(query):
                logger.info("Safety refusal triggered for query: %r", query[:60])
                result = TriageResult(
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
                obs.end_trace(trace, output={"triage_level": "YELLOW", "refusal": True})
                return result

            # Emergency fast-path: skip Steps 2-4 -> instant RED
            if _is_emergency(query):
                logger.info("Step 1b -- emergency detected, fast-path RED")
                obs.set_step("emergency-response")
                try:
                    result = await self._emergency_response(symptoms_text, total_tokens)
                except LLMError as exc:
                    logger.error("Emergency reply unavailable, using fallback: %s", exc)
                    result = self._fallback_result(TriageLevel.RED)
                obs.end_trace(
                    trace,
                    output={
                        "triage_level": "RED",
                        "emergency_fast_path": True,
                        "total_tokens": result.total_tokens,
                    },
                )
                return result

            # Step 2: Clarification -- only when genuinely vague
            if len(symptoms) == 0 and len(query.split()) < 2:
                logger.info("Step 2 -- vague query, requesting clarification")
                obs.set_step("clarification")
                try:
                    clarify_resp = await self._llm.generate(
                        prompt=_CLARIFICATION_PROMPT.format(
                            query=query,
                            symptoms_text=symptoms_text
                            if symptom_labels
                            else "nothing specific",
                        ),
                        system_prompt=_SYSTEM_PROMPT,
                        temperature=0.4,
                        max_tokens=1024,
                    )
                    total_tokens += clarify_resp.total_tokens
                    q = clarify_resp.text.strip()
                except LLMError as exc:
                    logger.error("Clarification unavailable, using fallback: %s", exc)
                    q = self._fallback_text("arabic", "CLARIFY")
                result = TriageResult(
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
                obs.end_trace(
                    trace, output={"triage_level": "GREEN", "needs_clarification": True}
                )
                return result

            # Step 3: Knowledge retrieval
            retrieval_results: list[RetrievalResult] = []
            if self._rag is not None:
                retrieval_results = await self._rag.retrieve(query, symptoms=symptoms)
                logger.info("Step 3 -- retrieved %d chunks", len(retrieval_results))
            context = self._format_context(retrieval_results)

            # Step 4: Triage classification
            obs.set_step("classification")
            try:
                classify_resp = await self._llm.generate(
                    prompt=_TRIAGE_PROMPT.format(
                        symptoms_text=symptoms_text,
                        context=context,
                        output_script="Lebanese Arabic",
                    ),
                    system_prompt=_SYSTEM_PROMPT,
                    temperature=0.1,
                    max_tokens=2048,
                )
            except LLMError as exc:
                logger.error("Classification unavailable, using fallback: %s", exc)
                result = self._fallback_result(self._fallback_level(symptoms))
                result.used_fallback = True
                obs.end_trace(
                    trace,
                    output={
                        "triage_level": result.triage_level.value,
                        "llm_available": False,
                    },
                )
                return result
            total_tokens += classify_resp.total_tokens
            triage_level, conditions, actions = self._parse_triage_json(
                classify_resp.text
            )
            logger.info("Step 4 -- level=%s | conditions=%s", triage_level, conditions)

            # Step 5: Response generation in Lebanese Arabic
            obs.set_step("response")
            try:
                response_resp = await self._llm.generate(
                    prompt=_RESPONSE_PROMPT.format(
                        symptoms_text=symptoms_text,
                        triage_level=triage_level.value,
                        conditions=", ".join(conditions)
                        if conditions
                        else "unspecified",
                        actions=", ".join(actions)
                        if actions
                        else "follow up with doctor",
                    ),
                    system_prompt=_SYSTEM_PROMPT,
                    temperature=0.4,
                    max_tokens=2048,
                )
                total_tokens += response_resp.total_tokens
                response_text = response_resp.text.strip()
            except LLMError as exc:
                logger.error("Response generation unavailable, using fallback: %s", exc)
                response_text = self._fallback_text(
                    "arabic", "RED" if triage_level == TriageLevel.RED else "YELLOW"
                )

            disclaimer = (
                _EMERGENCY_DISCLAIMER
                if triage_level == TriageLevel.RED
                else _DISCLAIMER
            )
            result = TriageResult(
                triage_level=triage_level,
                response_text=response_text,
                possible_conditions=conditions,
                recommended_actions=actions,
                sources=[r.to_dict() for r in retrieval_results],
                disclaimer=disclaimer,
                total_tokens=total_tokens,
            )
            obs.end_trace(
                trace,
                output={
                    "triage_level": triage_level.value,
                    "possible_conditions": conditions,
                    "total_tokens": total_tokens,
                    "sources_count": len(retrieval_results),
                },
            )
            return result

        except Exception as exc:
            obs.end_trace(trace, error=str(exc))
            raise

    async def triage_stream(
        self,
        query: str,
        prior_symptoms: list | None = None,
        response_script: str = "arabic",
        history: list[str] | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream triage pipeline, yielding SSE-ready dicts.

        ``response_script`` selects the output: "arabic", "franco" or "english".
        ``history`` holds the patient's earlier messages in this conversation,
        oldest first, so follow-up answers are triaged with their context.

        If every LLM provider is down the stream still completes, using rule-based
        triage and fixed copy, because a patient with symptoms needs next steps
        more than an error message.

        Event sequence:
            triage_classified → chunk (×N) → complete
        """
        total_tokens = 0
        script = response_script

        trace = obs.start_trace(
            name="triage-stream",
            metadata={"query_length": len(query), "endpoint": "/api/chat"},
        )

        # Step 1: Symptom extraction, over the whole conversation so far
        context_query = self._with_history(query, history)
        symptoms = (
            prior_symptoms
            if prior_symptoms is not None
            else self._proc.extract_symptoms(context_query)
        )
        symptom_labels = [
            s.english_medical_term or s.msa_equivalent
            for s in symptoms
            if s.english_medical_term or s.msa_equivalent
        ]
        symptoms_text = ", ".join(symptom_labels) if symptom_labels else context_query

        # Safety refusal (out-of-scope)
        if _REFUSAL_RE.search(query):
            refusal = (
                "Sorry, I cannot help with this case. "
                "For infants, pregnancy complications, or lab results, "
                "please consult a doctor directly."
            )
            yield {
                "type": "triage_classified",
                "triage_level": "YELLOW",
                "possible_conditions": [],
                "recommended_actions": ["Consult a doctor immediately"],
                "needs_clarification": False,
            }
            for word in refusal.split():
                yield {"type": "chunk", "content": word + " "}
            complete_event = {
                "type": "complete",
                "triage_level": "YELLOW",
                "possible_conditions": [],
                "recommended_actions": ["Consult a doctor immediately"],
                "sources": [],
                "disclaimer": _DISCLAIMER,
                "needs_clarification": False,
                "follow_up_question": None,
            }
            obs.end_trace(trace, output={"triage_level": "YELLOW", "refusal": True})
            yield complete_event
            return

        # Emergency fast-path → instant RED.  Only the latest message counts:
        # an emergency mentioned earlier was already escalated on that turn.
        if _is_emergency(query):
            obs.set_step("emergency-response")
            actions = self._fallback_actions(script, TriageLevel.RED)
            yield {
                "type": "triage_classified",
                "triage_level": "RED",
                "possible_conditions": ["emergency"],
                "recommended_actions": actions,
                "needs_clarification": False,
            }
            async for chunk in self._stream_or_fallback(
                prompt=self._get_response_prompt(script).format(
                    symptoms_text=symptoms_text,
                    triage_level="RED",
                    conditions="possible emergency",
                    actions="go to the ER or call the Red Cross on 140 immediately",
                ),
                system_prompt=self._get_system_prompt(script),
                temperature=0.1,
                max_tokens=1024,
                fallback=self._fallback_text(script, "RED"),
            ):
                yield {"type": "chunk", "content": chunk}
            complete_event = {
                "type": "complete",
                "triage_level": "RED",
                "possible_conditions": ["emergency"],
                "recommended_actions": actions,
                "sources": [],
                "disclaimer": self._get_disclaimer(script, emergency=True),
                "needs_clarification": False,
                "follow_up_question": None,
            }
            obs.end_trace(
                trace, output={"triage_level": "RED", "emergency_fast_path": True}
            )
            yield complete_event
            return

        # Step 2: Clarification
        if len(symptoms) == 0 and len(context_query.split()) < 2:
            obs.set_step("clarification")
            try:
                clarify_resp = await self._llm.generate(
                    prompt=self._get_clarification_prompt(script).format(
                        query=context_query,
                        symptoms_text=symptoms_text
                        if symptom_labels
                        else "nothing specific",
                    ),
                    system_prompt=self._get_system_prompt(script),
                    temperature=0.4,
                    max_tokens=1024,
                )
                q = clarify_resp.text.strip()
            except LLMError as exc:
                logger.error("Clarification unavailable, using fallback: %s", exc)
                q = self._fallback_text(script, "CLARIFY")
            yield {
                "type": "triage_classified",
                "triage_level": "GREEN",
                "possible_conditions": [],
                "recommended_actions": [],
                "needs_clarification": True,
            }
            for word in q.split():
                yield {"type": "chunk", "content": word + " "}
            complete_event = {
                "type": "complete",
                "triage_level": "GREEN",
                "possible_conditions": [],
                "recommended_actions": [],
                "sources": [],
                "disclaimer": self._get_disclaimer(script),
                "needs_clarification": True,
                "follow_up_question": q,
            }
            obs.end_trace(
                trace, output={"triage_level": "GREEN", "needs_clarification": True}
            )
            yield complete_event
            return

        # Step 3: Knowledge retrieval
        retrieval_results: list[RetrievalResult] = []
        if self._rag is not None:
            retrieval_results = await self._rag.retrieve(
                context_query, symptoms=symptoms
            )
        context = self._format_context(retrieval_results)

        # Step 4: Classification
        obs.set_step("classification")
        llm_available = True
        try:
            classify_resp = await self._llm.generate(
                prompt=_TRIAGE_PROMPT.format(
                    symptoms_text=symptoms_text,
                    context=context,
                    output_script=self._get_output_script(script),
                ),
                system_prompt=_SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=2048,
            )
            total_tokens += classify_resp.total_tokens
            triage_level, conditions, actions = self._parse_triage_json(
                classify_resp.text
            )
        except LLMError as exc:
            # Emergencies already took the fast path above; beyond those, only
            # symptoms the lexicon marks critical justify RED without a model.
            logger.error("Classification unavailable, using fallback: %s", exc)
            llm_available = False
            triage_level = self._fallback_level(symptoms)
            conditions = []
            actions = self._fallback_actions(script, triage_level)

        is_emergency = triage_level == TriageLevel.RED
        disclaimer = self._get_disclaimer(script, emergency=is_emergency)

        # Emit classification before text starts streaming
        yield {
            "type": "triage_classified",
            "triage_level": triage_level.value,
            "possible_conditions": conditions,
            "recommended_actions": actions,
            "needs_clarification": False,
        }

        # Step 5: Stream response generation
        obs.set_step("stream-response")
        fallback = self._fallback_text(script, "RED" if is_emergency else "YELLOW")
        if llm_available:
            chunks = self._stream_or_fallback(
                prompt=self._get_response_prompt(script).format(
                    symptoms_text=symptoms_text,
                    triage_level=triage_level.value,
                    conditions=", ".join(conditions) if conditions else "unspecified",
                    actions=", ".join(actions) if actions else "follow up with doctor",
                ),
                system_prompt=self._get_system_prompt(script),
                temperature=0.4,
                max_tokens=2048,
                fallback=fallback,
            )
        else:
            # Providers just failed; don't make the patient wait on them again.
            chunks = self._single_chunk(fallback)
        async for chunk in chunks:
            yield {"type": "chunk", "content": chunk}

        complete_event = {
            "type": "complete",
            "triage_level": triage_level.value,
            "possible_conditions": conditions,
            "recommended_actions": actions,
            "sources": [r.to_dict() for r in retrieval_results],
            "disclaimer": disclaimer,
            "needs_clarification": False,
            "follow_up_question": None,
        }
        obs.end_trace(
            trace,
            output={
                "triage_level": triage_level.value,
                "possible_conditions": conditions,
                "total_tokens": total_tokens,
                "sources_count": len(retrieval_results),
                "llm_available": llm_available,
            },
        )
        yield complete_event

    async def _stream_or_fallback(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
        fallback: str,
    ) -> AsyncGenerator[str, None]:
        """Stream an LLM reply, or yield ``fallback`` if no provider can answer."""
        yielded = False
        try:
            async for chunk in self._llm.generate_stream(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                yielded = True
                yield chunk
        except LLMError as exc:
            logger.error("Response generation unavailable, using fallback: %s", exc)
            if not yielded:
                yield fallback

    @staticmethod
    async def _single_chunk(text: str) -> AsyncGenerator[str, None]:
        yield text

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback_level(symptoms: list) -> TriageLevel:
        """Triage level from rules alone, for when no LLM is reachable."""
        if any(
            getattr(s, "severity_hint", None) in _CRITICAL_SEVERITY for s in symptoms
        ):
            return TriageLevel.RED
        return TriageLevel.YELLOW

    def _fallback_result(self, level: TriageLevel) -> TriageResult:
        """Rule-based result for when no LLM provider is reachable."""
        is_red = level == TriageLevel.RED
        return TriageResult(
            triage_level=level,
            response_text=self._fallback_text("arabic", "RED" if is_red else "YELLOW"),
            possible_conditions=["emergency"] if is_red else [],
            recommended_actions=self._fallback_actions("arabic", level),
            sources=[],
            disclaimer=self._get_disclaimer("arabic", emergency=is_red),
        )

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
            max_tokens=1024,
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
        """Parse LLM JSON output; return defaults on any error.

        Handles truncated JSON from Gemini 2.5 thinking-token budget by
        attempting to repair incomplete output before giving up.
        """
        try:
            clean = re.sub(r"```(?:json)?|```", "", text).strip()
            # Find the opening brace of JSON
            brace_idx = clean.find("{")
            if brace_idx == -1:
                raise ValueError("no JSON object found")
            json_str = clean[brace_idx:]

            # Try parsing as-is first
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                # Attempt to repair truncated JSON:
                # 1. Close any open strings/arrays/objects
                repaired = json_str.rstrip()
                if repaired.endswith(","):
                    repaired = repaired[:-1]
                # Close open quotes
                if repaired.count('"') % 2 != 0:
                    repaired += '"'
                # Close open arrays
                open_brackets = repaired.count("[") - repaired.count("]")
                repaired += "]" * max(0, open_brackets)
                # Close open objects
                open_braces = repaired.count("{") - repaired.count("}")
                repaired += "}" * max(0, open_braces)
                try:
                    data = json.loads(repaired)
                    logger.info("Repaired truncated triage JSON successfully")
                except json.JSONDecodeError:
                    raise ValueError("no valid JSON object found (repair failed)")

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
            logger.warning("Failed to parse triage JSON: %s | text=%r", exc, text[:200])
            return default_level, [], []
