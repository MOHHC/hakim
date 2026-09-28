"""Emergency detection that doesn't depend on an LLM.

The phrasings here are deliberately different from the eval scenarios, so they
check the patterns generalise rather than memorise the eval set.
"""

from __future__ import annotations

import pytest

from app.core.arabic_processor import LexiconMatch
from app.core.safety_guardrails import SafetyGuardrails
from app.core.triage_engine import TriageEngine, TriageLevel, _is_emergency


@pytest.mark.parametrize(
    "query",
    [
        # chest pain with words between pain and chest
        "في ضغط قوي على صدري من ربع ساعة",
        "عندي ألم شديد بالصدر",
        "there's a heavy pressure on my chest",
        # cyanosis
        "شفايف ابني صارو زرق",
        "his lips are turning blue",
        # can't breathe / unresponsive
        "مش قادرة اتنفس",
        "بيي مش عم يوعى",
        "my dad is not breathing",
        "she won't wake up",
        "jiddo ma 3am yes7a",
        # stroke
        "وجه امي عم يتعوج وما عم تقدر تحكي",
        "ma ba2der e7ke mnee7 w wejji 3am yet3awwaj",
        "his face is drooping and he has slurred speech",
        "I can't move my left arm suddenly",
        # anaphylaxis
        "لساني عم يتورم بعد ما اكلت فستق",
        "ma ba2der ebla3 w shfefi 3am yet2awwaru",
        "my throat is closing up after a bee sting",
        # blood
        "عم بسعل دم من الصبح",
        "I've been coughing up blood",
        "2a2ayt dam",
        # glucose extremes
        "my sugar is 520 and I'm confused",
        "السكري عندي 45 وعم برجف",
        # seizure
        "my brother is having a seizure right now",
    ],
)
def test_unseen_emergency_phrasings_are_red(query):
    assert _is_emergency(query)


@pytest.mark.parametrize(
    "query",
    [
        "عندي كحة وبلغم من يومين",
        "صدري مسكّر شوي من الرشح",  # stuffy chest from a cold, no pain word
        "I have a mild cough and a runny nose",
        "my lips are dry and cracked",
        "I feel a bit short of energy today",
        "my sugar was 110 this morning",
        "السكري عندي 130",
        "I had blood test results last week",  # lab scope, not an emergency
        "3endi rash 3a idi",
        "وجعني ضهري من الشغل",
        "I watched a video about seizures",
    ],
)
def test_everyday_complaints_are_not_emergencies(query):
    assert not _is_emergency(query)


def test_hamza_spelling_does_not_hide_suicidal_ideation():
    g = SafetyGuardrails()
    for query in ("عندي أفكار إنتحارية", "عندي افكار انتحارية"):
        r = g.check_query(query)
        assert not r.is_safe
        assert g.is_emergency_violation(r)


@pytest.mark.parametrize(
    "query",
    ["عمري 30 وضربت راسي وعم استفرغ", "I hit my head and now I keep vomiting"],
)
def test_head_injury_with_vomiting_is_red(query):
    r = SafetyGuardrails().check_query(query)
    assert r.force_red


def test_infant_and_pregnancy_refusals_escalate():
    g = SafetyGuardrails()
    assert g.check_query("طفلي عمره شهر وعنده حرارة").force_red
    assert g.check_query("انا حامل وعندي نزيف").force_red


def _symptom(severity: str) -> LexiconMatch:
    return LexiconMatch(
        dialect_term="x",
        dialect_term_latin="x",
        msa_equivalent="x",
        english_medical_term="x",
        category="x",
        body_system="general",
        severity_hint=severity,
        matched_on="latin",
    )


def test_fallback_escalates_only_critical_symptoms():
    assert TriageEngine._fallback_level([_symptom("critical")]) == TriageLevel.RED
    assert TriageEngine._fallback_level([_symptom("severe")]) == TriageLevel.YELLOW
    assert TriageEngine._fallback_level([]) == TriageLevel.YELLOW
