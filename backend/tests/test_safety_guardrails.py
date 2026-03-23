"""Extensive tests for SafetyGuardrails — each guardrail tested independently."""

from __future__ import annotations

import pytest

from app.core.safety_guardrails import (
    DISCLAIMER,
    EMERGENCY_DISCLAIMER,
    UNCERTAINTY_TEXT,
    GuardrailResult,
    SafetyGuardrails,
    ViolationType,
)


@pytest.fixture
def g() -> SafetyGuardrails:
    return SafetyGuardrails()


# ===========================================================================
# ViolationType
# ===========================================================================


class TestViolationType:
    def test_all_values_are_strings(self):
        for vt in ViolationType:
            assert isinstance(vt, str)

    def test_expected_members(self):
        names = set(ViolationType.__members__)
        assert names == {
            "SCOPE_INFANT",
            "SCOPE_PREGNANCY",
            "SCOPE_LAB_RESULTS",
            "EMERGENCY_RED_FLAG",
            "SUICIDAL_IDEATION",
            "DIAGNOSIS_LANGUAGE",
            "MEDICATION_REFERENCE",
        }


# ===========================================================================
# GuardrailResult
# ===========================================================================


class TestGuardrailResult:
    def test_safe_defaults(self):
        r = GuardrailResult(is_safe=True)
        assert r.violation_type is None
        assert r.rejection_message is None
        assert r.force_red is False
        assert r.add_uncertainty is False

    def test_unsafe_with_rejection(self):
        r = GuardrailResult(
            is_safe=False,
            violation_type=ViolationType.SCOPE_INFANT,
            rejection_message="Please see a pediatrician.",
        )
        assert not r.is_safe
        assert r.rejection_message


# ===========================================================================
# 1. Suicidal ideation
# ===========================================================================


class TestSuicidalIdeation:
    def test_english_kill_myself(self, g):
        r = g.check_query("I want to kill myself")
        assert not r.is_safe
        assert r.violation_type == ViolationType.SUICIDAL_IDEATION

    def test_english_end_my_life(self, g):
        r = g.check_query("I want to end my life")
        assert not r.is_safe
        assert r.violation_type == ViolationType.SUICIDAL_IDEATION

    def test_english_no_reason_to_live(self, g):
        r = g.check_query("I have no reason to live anymore")
        assert not r.is_safe
        assert r.violation_type == ViolationType.SUICIDAL_IDEATION

    def test_arabic_badi_mout(self, g):
        r = g.check_query("\u0628\u062f\u064a \u0645\u0648\u062a")  # بدي موت
        assert not r.is_safe
        assert r.violation_type == ViolationType.SUICIDAL_IDEATION

    def test_arabic_suicide_word(self, g):
        r = g.check_query(
            "\u0639\u0646\u062f\u064a \u0623\u0641\u0643\u0627\u0631 \u0627\u0646\u062a\u062d\u0627\u0631"
        )
        assert not r.is_safe
        assert r.violation_type == ViolationType.SUICIDAL_IDEATION

    def test_rejection_message_present(self, g):
        r = g.check_query("I want to kill myself")
        assert r.rejection_message is not None
        assert len(r.rejection_message) > 0

    def test_force_red_is_false_for_suicidal(self, g):
        # Suicidal ideation is handled as a crisis referral, not a physical emergency
        r = g.check_query("I want to end my life")
        assert r.force_red is False

    def test_is_emergency_violation_true_for_suicidal(self, g):
        r = g.check_query("I want to kill myself")
        assert SafetyGuardrails.is_emergency_violation(r)

    def test_normal_query_not_flagged_as_suicidal(self, g):
        r = g.check_query("3andi waja3 ras w 7arara")
        assert r.violation_type != ViolationType.SUICIDAL_IDEATION


# ===========================================================================
# 2. Scope: children under 2
# ===========================================================================


class TestScopeInfant:
    def test_english_infant(self, g):
        r = g.check_query("my infant has a fever")
        assert not r.is_safe
        assert r.violation_type == ViolationType.SCOPE_INFANT

    def test_english_newborn(self, g):
        r = g.check_query("my newborn is not feeding")
        assert not r.is_safe
        assert r.violation_type == ViolationType.SCOPE_INFANT

    def test_english_6_months(self, g):
        r = g.check_query("my 6 months old has diarrhea")
        assert not r.is_safe
        assert r.violation_type == ViolationType.SCOPE_INFANT

    def test_english_under_2_years(self, g):
        r = g.check_query("a child under 2 years has rash")
        assert not r.is_safe
        assert r.violation_type == ViolationType.SCOPE_INFANT

    def test_arabic_radi3(self, g):
        r = g.check_query(
            "\u0627\u0644\u0631\u0636\u064a\u0639 \u0639\u0646\u062f\u0647 \u062d\u0645\u0649"
        )
        assert not r.is_safe
        assert r.violation_type == ViolationType.SCOPE_INFANT

    def test_rejection_directs_to_pediatrician(self, g):
        r = g.check_query("my infant is sick")
        assert r.rejection_message
        assert (
            "pediatrician" in r.rejection_message.lower() or "ER" in r.rejection_message
        )

    def test_adult_query_not_flagged(self, g):
        r = g.check_query("3andi waja3 ras w 7arara")
        assert r.violation_type != ViolationType.SCOPE_INFANT

    def test_older_child_not_flagged(self, g):
        # "5 years old" should not be flagged as infant
        r = g.check_query("my 5 years old has a cold")
        assert r.violation_type != ViolationType.SCOPE_INFANT


# ===========================================================================
# 3. Scope: pregnancy complications
# ===========================================================================


class TestScopePregnancy:
    def test_english_pregnant_with_symptom(self, g):
        r = g.check_query("I am pregnant and have severe pain")
        assert not r.is_safe
        assert r.violation_type == ViolationType.SCOPE_PREGNANCY

    def test_english_contractions(self, g):
        r = g.check_query("I have contractions every 5 minutes")
        assert not r.is_safe
        assert r.violation_type == ViolationType.SCOPE_PREGNANCY

    def test_english_preeclampsia(self, g):
        r = g.check_query("I think I have preeclampsia")
        assert not r.is_safe
        assert r.violation_type == ViolationType.SCOPE_PREGNANCY

    def test_arabic_hamila(self, g):
        r = g.check_query(
            "\u0623\u0646\u0627 \u062d\u0627\u0645\u0644\u0629 \u0648\u0639\u0646\u062f\u064a \u0623\u0644\u0645"
        )
        assert not r.is_safe
        assert r.violation_type == ViolationType.SCOPE_PREGNANCY

    def test_rejection_directs_to_obgyn(self, g):
        r = g.check_query("I am pregnant and bleeding")
        assert r.rejection_message
        msg = r.rejection_message.lower()
        assert "ob" in msg or "gynecolog" in msg or "maternity" in msg

    def test_water_broke(self, g):
        r = g.check_query("my water broke")
        assert not r.is_safe
        assert r.violation_type == ViolationType.SCOPE_PREGNANCY


# ===========================================================================
# 4. Scope: lab results / imaging
# ===========================================================================


class TestScopeLabResults:
    def test_english_lab_result(self, g):
        r = g.check_query("my lab result shows high white blood cells")
        assert not r.is_safe
        assert r.violation_type == ViolationType.SCOPE_LAB_RESULTS

    def test_english_blood_test_result(self, g):
        r = g.check_query("my blood test result came back abnormal")
        assert not r.is_safe
        assert r.violation_type == ViolationType.SCOPE_LAB_RESULTS

    def test_english_mri_result(self, g):
        r = g.check_query("I got my MRI result and need help")
        assert not r.is_safe
        assert r.violation_type == ViolationType.SCOPE_LAB_RESULTS

    def test_english_xray_result(self, g):
        r = g.check_query("x-ray result shows something")
        assert not r.is_safe
        assert r.violation_type == ViolationType.SCOPE_LAB_RESULTS

    def test_arabic_lab_result(self, g):
        # نتيجة تحليل
        r = g.check_query(
            "\u0646\u062a\u064a\u062c\u0629 \u062a\u062d\u0644\u064a\u0644\u064a \u0637\u0644\u0639\u062a \u0639\u0627\u0644\u064a\u0629"
        )
        assert not r.is_safe
        assert r.violation_type == ViolationType.SCOPE_LAB_RESULTS

    def test_rejection_directs_to_doctor(self, g):
        r = g.check_query("my lab result is strange")
        assert r.rejection_message
        assert "doctor" in r.rejection_message.lower()

    def test_ecg_result(self, g):
        r = g.check_query("my ecg result shows abnormal rhythm")
        assert not r.is_safe
        assert r.violation_type == ViolationType.SCOPE_LAB_RESULTS

    def test_normal_query_no_lab_flag(self, g):
        r = g.check_query("I have a headache and fever")
        assert r.violation_type != ViolationType.SCOPE_LAB_RESULTS


# ===========================================================================
# 5. Red flag detection (compound emergency patterns)
# ===========================================================================


class TestRedFlagDetection:
    # --- Cardiac MI pattern ---

    def test_chest_pain_plus_arm_numbness(self, g):
        r = g.check_query("I have chest pain and arm numbness")
        assert not r.is_safe
        assert r.violation_type == ViolationType.EMERGENCY_RED_FLAG
        assert r.force_red is True

    def test_chest_pain_plus_left_arm(self, g):
        r = g.check_query("chest pain radiating to left arm")
        assert not r.is_safe
        assert r.violation_type == ViolationType.EMERGENCY_RED_FLAG

    def test_chest_pain_plus_jaw_pain(self, g):
        r = g.check_query("I have chest tightness and jaw pain")
        assert not r.is_safe
        assert r.violation_type == ViolationType.EMERGENCY_RED_FLAG

    def test_chest_pain_alone_not_compound_flag(self, g):
        # Chest pain alone doesn't trigger the compound cardiac flag
        r = g.check_query("I have mild chest pain since yesterday")
        assert r.violation_type != ViolationType.EMERGENCY_RED_FLAG

    # --- Anaphylaxis pattern ---

    def test_throat_swelling_plus_difficulty_breathing(self, g):
        r = g.check_query("I have throat swelling and difficulty breathing")
        assert not r.is_safe
        assert r.violation_type == ViolationType.EMERGENCY_RED_FLAG

    def test_hives_plus_shortness_of_breath(self, g):
        r = g.check_query("I have hives and shortness of breath")
        assert not r.is_safe
        assert r.violation_type == ViolationType.EMERGENCY_RED_FLAG

    def test_hives_alone_not_emergency(self, g):
        r = g.check_query("I have hives on my arm")
        assert r.violation_type != ViolationType.EMERGENCY_RED_FLAG

    # --- Head trauma pattern ---

    def test_head_injury_plus_vomiting(self, g):
        r = g.check_query("I hit my head and I'm vomiting")
        assert not r.is_safe
        assert r.violation_type == ViolationType.EMERGENCY_RED_FLAG

    def test_head_trauma_plus_unconscious(self, g):
        r = g.check_query("head injury and lost consciousness")
        assert not r.is_safe
        assert r.violation_type == ViolationType.EMERGENCY_RED_FLAG

    def test_head_injury_alone_not_compound(self, g):
        r = g.check_query("I have a head injury with some pain")
        assert r.violation_type != ViolationType.EMERGENCY_RED_FLAG

    def test_red_flag_rejection_message_present(self, g):
        r = g.check_query("chest pain and arm numbness")
        assert r.rejection_message is not None
        assert "ER" in r.rejection_message or "emergency" in r.rejection_message.lower()

    def test_force_red_set_for_red_flag(self, g):
        r = g.check_query("I have hives and difficulty breathing")
        assert r.force_red is True

    def test_is_emergency_violation_true_for_red_flag(self, g):
        r = g.check_query("chest pain and left arm numbness")
        assert SafetyGuardrails.is_emergency_violation(r)

    # --- Normal queries pass ---

    def test_normal_headache_passes(self, g):
        r = g.check_query("3andi waja3 ras w 7arara")
        assert r.is_safe

    def test_normal_stomach_pain_passes(self, g):
        r = g.check_query("I have stomach ache and nausea")
        assert r.is_safe


# ===========================================================================
# 6. check_response — diagnosis language
# ===========================================================================


class TestCheckResponseDiagnosis:
    def test_you_have_disease(self, g):
        r = g.check_response("You have hypertension.")
        assert not r.is_safe
        assert r.violation_type == ViolationType.DIAGNOSIS_LANGUAGE

    def test_you_are_diagnosed_with(self, g):
        r = g.check_response("You are diagnosed with diabetes.")
        assert not r.is_safe
        assert r.violation_type == ViolationType.DIAGNOSIS_LANGUAGE

    def test_this_is_definitely(self, g):
        r = g.check_response("This is definitely appendicitis.")
        assert not r.is_safe
        assert r.violation_type == ViolationType.DIAGNOSIS_LANGUAGE

    def test_diagnosis_word(self, g):
        r = g.check_response("My diagnosis is that you have a cold.")
        assert not r.is_safe
        assert r.violation_type == ViolationType.DIAGNOSIS_LANGUAGE

    def test_add_uncertainty_true_for_diagnosis(self, g):
        r = g.check_response("You have pneumonia.")
        assert r.add_uncertainty is True

    def test_clean_response_passes(self, g):
        r = g.check_response("This may be related to a viral infection.")
        assert r.is_safe

    def test_hedged_response_passes(self, g):
        r = g.check_response("Your symptoms could suggest a possible infection.")
        assert r.is_safe


# ===========================================================================
# 7. check_response — medication references
# ===========================================================================


class TestCheckResponseMedication:
    def test_dosage_mg(self, g):
        r = g.check_response("Take 500 mg of ibuprofen.")
        assert not r.is_safe
        assert r.violation_type == ViolationType.MEDICATION_REFERENCE

    def test_drug_name_ibuprofen(self, g):
        r = g.check_response("You can take ibuprofen for pain.")
        assert not r.is_safe
        assert r.violation_type == ViolationType.MEDICATION_REFERENCE

    def test_drug_name_paracetamol(self, g):
        r = g.check_response("Paracetamol can help with fever.")
        assert not r.is_safe
        assert r.violation_type == ViolationType.MEDICATION_REFERENCE

    def test_drug_name_amoxicillin(self, g):
        r = g.check_response("The doctor may prescribe amoxicillin.")
        assert not r.is_safe
        assert r.violation_type == ViolationType.MEDICATION_REFERENCE

    def test_take_drug_pattern(self, g):
        r = g.check_response("Take aspirin immediately.")
        assert not r.is_safe
        assert r.violation_type == ViolationType.MEDICATION_REFERENCE

    def test_tablet_dosage(self, g):
        r = g.check_response("Take 2 tablets three times a day.")
        assert not r.is_safe
        assert r.violation_type == ViolationType.MEDICATION_REFERENCE

    def test_clean_no_medication_passes(self, g):
        r = g.check_response("Rest, drink fluids, and see a doctor.")
        assert r.is_safe

    def test_general_advice_passes(self, g):
        r = g.check_response(
            "You should stay hydrated and rest. If it gets worse, consult a doctor."
        )
        assert r.is_safe


# ===========================================================================
# 8. sanitize_response
# ===========================================================================


class TestSanitizeResponse:
    def test_softens_you_have(self, g):
        out = g.sanitize_response("You have a cold.")
        assert "you have" not in out.lower()
        assert "may have" in out.lower()

    def test_softens_you_are_diagnosed_with(self, g):
        out = g.sanitize_response("You are diagnosed with bronchitis.")
        assert "are diagnosed with" not in out.lower()
        assert "may suggest" in out.lower()

    def test_softens_this_is_definitely(self, g):
        out = g.sanitize_response("This is definitely a sinus infection.")
        assert "definitely" not in out.lower()
        assert "may be" in out.lower()

    def test_removes_dosage_mg(self, g):
        out = g.sanitize_response("Take 500 mg of paracetamol.")
        assert "500" not in out or "mg" not in out
        assert "[dosage removed]" in out

    def test_removes_take_medication_advice(self, g):
        out = g.sanitize_response("Take aspirin right away.")
        assert "[medication advice removed]" in out

    def test_clean_text_unchanged(self, g):
        text = "Rest, drink water, and consult a doctor if it worsens."
        out = g.sanitize_response(text)
        assert out == text

    def test_multiple_violations_all_sanitized(self, g):
        text = "You have a cold. Take 500 mg of ibuprofen twice a day."
        out = g.sanitize_response(text)
        assert "you have" not in out.lower()
        assert "[dosage removed]" in out


# ===========================================================================
# 9. ensure_disclaimer
# ===========================================================================


class TestEnsureDisclaimer:
    def test_appends_disclaimer_when_absent(self, g):
        out = g.ensure_disclaimer("Here is some advice.")
        assert DISCLAIMER in out

    def test_does_not_duplicate_disclaimer(self, g):
        text = f"Some advice.\n\n{DISCLAIMER}"
        out = g.ensure_disclaimer(text)
        assert out.count(DISCLAIMER) == 1

    def test_emergency_disclaimer_appended(self, g):
        out = g.ensure_disclaimer("Go to ER.", is_emergency=True)
        assert EMERGENCY_DISCLAIMER in out

    def test_emergency_disclaimer_not_duplicated(self, g):
        text = f"Go to ER.\n\n{EMERGENCY_DISCLAIMER}"
        out = g.ensure_disclaimer(text, is_emergency=True)
        assert out.count(EMERGENCY_DISCLAIMER) == 1


# ===========================================================================
# 10. needs_uncertainty / apply_uncertainty_if_needed
# ===========================================================================


class TestUncertaintyHandling:
    def test_confident_claim_without_hedging_needs_uncertainty(self, g):
        text = "You have hypertension. Your diagnosis is clear."
        assert g.needs_uncertainty(text) is True

    def test_hedged_claim_does_not_need_uncertainty(self, g):
        text = "This may be related to hypertension."
        assert g.needs_uncertainty(text) is False

    def test_clean_text_no_uncertainty_needed(self, g):
        text = "Rest and drink fluids."
        assert g.needs_uncertainty(text) is False

    def test_apply_prepends_uncertainty_text(self, g):
        text = "You have a diagnosis of hypertension."
        out = g.apply_uncertainty_if_needed(text)
        assert out.startswith(UNCERTAINTY_TEXT)

    def test_apply_does_not_prepend_when_hedged(self, g):
        text = "This could possibly be a viral infection."
        out = g.apply_uncertainty_if_needed(text)
        assert not out.startswith(UNCERTAINTY_TEXT)
        assert out == text


# ===========================================================================
# 11. is_emergency_violation (static helper)
# ===========================================================================


class TestIsEmergencyViolation:
    def test_force_red_is_emergency(self):
        r = GuardrailResult(
            is_safe=False,
            violation_type=ViolationType.EMERGENCY_RED_FLAG,
            force_red=True,
        )
        assert SafetyGuardrails.is_emergency_violation(r)

    def test_suicidal_is_emergency(self):
        r = GuardrailResult(
            is_safe=False,
            violation_type=ViolationType.SUICIDAL_IDEATION,
        )
        assert SafetyGuardrails.is_emergency_violation(r)

    def test_scope_infant_not_emergency(self):
        r = GuardrailResult(
            is_safe=False,
            violation_type=ViolationType.SCOPE_INFANT,
        )
        assert not SafetyGuardrails.is_emergency_violation(r)

    def test_safe_result_not_emergency(self):
        r = GuardrailResult(is_safe=True)
        assert not SafetyGuardrails.is_emergency_violation(r)


# ===========================================================================
# 12. Priority ordering (suicidal takes precedence over scope)
# ===========================================================================


class TestPriorityOrdering:
    def test_suicidal_before_infant(self, g):
        # A query mentioning both infant and suicidal ideation -> suicidal wins
        r = g.check_query("my infant, I want to kill myself")
        assert r.violation_type == ViolationType.SUICIDAL_IDEATION

    def test_suicidal_before_red_flag(self, g):
        r = g.check_query("I have chest pain and arm numbness and want to die")
        assert r.violation_type == ViolationType.SUICIDAL_IDEATION

    def test_infant_before_pregnancy(self, g):
        # Infant before pregnancy in priority order
        r = g.check_query("my infant is ill and I am pregnant")
        assert r.violation_type == ViolationType.SCOPE_INFANT
