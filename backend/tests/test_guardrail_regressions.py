"""Regression cases for guardrail false positives/negatives seen in production."""

from __future__ import annotations

import pytest

from app.core.safety_guardrails import SafetyGuardrails, ViolationType, detect_script


@pytest.fixture
def g() -> SafetyGuardrails:
    return SafetyGuardrails()


@pytest.mark.parametrize(
    "query",
    [
        "ابني عمرو 3 أشهر وعندو حرارة",
        "ابني عمرو ٣ اشهر وعندو حرارة",
        "بنتي عمرها شهرين وعم تستفرغ",
        "ابني عمرو سنة وعندو كحة",
        "my 3 month old has a fever",
        "my son is 1 year old and has diarrhea",
        "ebne 3emro 5 ashhor w 3ando 7arara",
        "my baby has a rash",
    ],
)
def test_children_under_two_are_referred(g, query):
    assert g.check_query(query).violation_type == ViolationType.SCOPE_INFANT


@pytest.mark.parametrize(
    "query",
    [
        "ابني عمرو 5 سنين وعندو حرارة",
        "عندي وجع ضهر من 3 أشهر",
        "I've had back pain for 3 months",
        "my son is 30 months old with a cough",
        # "حمل" inside other words: lifting / bearing, not pregnancy
        "حملت شي تقيل ووجعني ضهري",
        "ما عم بقدر اتحمل الوجع براسي",
        # "فك" inside "بفكر" (I think), not jaw
        "عندي وجع صدر وبفكر انو من الأكل",
        "I have a cough and I take my inhaler",
        "عندي وجع راس من يومين",
    ],
)
def test_ordinary_adult_queries_are_not_blocked(g, query):
    result = g.check_query(query)
    assert result.violation_type not in (
        ViolationType.SCOPE_INFANT,
        ViolationType.SCOPE_PREGNANCY,
        ViolationType.SCOPE_MEDICATION,
    )


@pytest.mark.parametrize(
    "query",
    ["انا حامل وعندي نزيف", "مرتي بالحمل الشهر السابع وعندها وجع", "I'm pregnant"],
)
def test_pregnancy_still_detected(g, query):
    assert g.check_query(query).violation_type == ViolationType.SCOPE_PREGNANCY


def test_lebanese_cardiac_phrasing_is_red(g):
    r = g.check_query("عندي وجع بصدري وبيوصل على دراعي")
    assert r.violation_type == ViolationType.EMERGENCY_RED_FLAG
    assert r.force_red


@pytest.mark.parametrize("query", ["I took too many pills", "my friend overdosed"])
def test_overdose_is_an_emergency(g, query):
    r = g.check_query(query)
    assert r.violation_type == ViolationType.EMERGENCY_RED_FLAG
    assert r.force_red


@pytest.mark.parametrize(
    "query",
    [
        "what dose of xanax should I take",
        "how many mg of ibuprofen can I take",
        "شو دوا بآخد للراس",
    ],
)
def test_medication_requests_are_referred(g, query):
    assert g.check_query(query).violation_type == ViolationType.SCOPE_MEDICATION


class TestFormatRejection:
    def test_crisis_message_has_lebanese_helplines_and_no_physical_warning(self, g):
        r = g.check_query("I want to kill myself")
        msg = g.format_rejection(r, "english")
        assert "1564" in msg and "140" in msg
        assert "require IMMEDIATE emergency care" not in msg

    def test_arabic_patient_gets_arabic_refusal(self, g):
        r = g.check_query("ابني عمرو 3 أشهر وعندو حرارة")
        msg = g.format_rejection(r, "arabic")
        assert detect_script(msg) == "arabic"

    def test_emergency_refusal_gets_emergency_disclaimer(self, g):
        r = g.check_query("chest pain and my left arm is numb")
        assert "140" in g.format_rejection(r, "franco")


class TestSanitizeKeepsOrdinaryAdvice:
    def test_take_a_rest_survives(self, g):
        text = "Please take a rest and drink water."
        assert g.sanitize_response(text) == text

    def test_drug_names_are_removed(self, g):
        out = g.sanitize_response("Some people use paracetamol for this.")
        assert "paracetamol" not in out.lower()
