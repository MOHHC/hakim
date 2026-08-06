"""Tests for the triage evaluation runner's metrics and exit-code semantics.

The escalation-recall gate is the project's one hard safety threshold, so it
must fire when — and only when — triage quality actually regressed.  A run in
which the LLM providers were exhausted produced no evidence either way and
must not be reported as a safety failure.
"""

from tests.eval.run_eval import (
    EvalMetrics,
    EvalOutcome,
    ScenarioResult,
    aggregate,
    build_json_report,
    build_markdown_report,
    decide_outcome,
)


def _red(
    sid: str, actual_level: str | None, error: str | None = None
) -> ScenarioResult:
    return ScenarioResult(
        id=sid,
        input_text="وجع بصدري وما فيي اتنفس",
        input_type="arabic",
        expected_level="RED",
        actual_level=actual_level,
        expected_body_system="cardiac",
        should_escalate=True,
        should_ask_followup=False,
        level_correct=actual_level == "RED",
        error=error,
    )


# ---------------------------------------------------------------------------
# Recall is undefined — not zero — when no RED scenario produced a verdict
# ---------------------------------------------------------------------------


def test_escalation_recall_is_none_when_no_red_scenarios_ran():
    metrics = aggregate(
        [_red(f"red_{i:03d}", None, "All providers failed.") for i in range(10)]
    )

    assert metrics.red_total == 0
    assert metrics.escalation_recall is None, (
        "zero RED scenarios evaluated is missing data, not 0% recall"
    )


def test_escalation_recall_is_computed_when_red_scenarios_ran():
    metrics = aggregate([_red("red_001", "RED"), _red("red_002", "YELLOW")])

    assert metrics.red_total == 2
    assert metrics.escalation_recall == 0.5


# ---------------------------------------------------------------------------
# Provider exhaustion is inconclusive, not a safety regression
# ---------------------------------------------------------------------------


def test_total_provider_failure_is_inconclusive_not_a_safety_failure():
    results = [_red(f"red_{i:03d}", None, "All providers failed.") for i in range(10)]
    outcome = decide_outcome(aggregate(results), total_scenarios=10)

    assert outcome is EvalOutcome.INCONCLUSIVE
    assert outcome.exit_code == 1
    assert outcome.exit_code != EvalOutcome.SAFETY_FAILURE.exit_code


def test_genuine_recall_regression_is_a_safety_failure():
    # 10 RED scenarios evaluated cleanly, only 8 escalated -> 80% recall.
    results = [_red(f"red_{i:03d}", "RED") for i in range(8)]
    results += [_red("red_008", "YELLOW"), _red("red_009", "GREEN")]
    outcome = decide_outcome(aggregate(results), total_scenarios=10)

    assert outcome is EvalOutcome.SAFETY_FAILURE
    assert outcome.exit_code == 2


def test_clean_run_above_threshold_passes():
    results = [_red(f"red_{i:03d}", "RED") for i in range(20)]
    outcome = decide_outcome(aggregate(results), total_scenarios=20)

    assert outcome is EvalOutcome.PASS
    assert outcome.exit_code == 0


def test_a_few_errors_do_not_invalidate_an_otherwise_clean_run():
    # 19/20 scenarios evaluated, all escalated correctly; one transient error.
    results = [_red(f"red_{i:03d}", "RED") for i in range(19)]
    results.append(_red("red_019", None, "timeout"))
    outcome = decide_outcome(aggregate(results), total_scenarios=20)

    assert outcome is EvalOutcome.PASS


def test_high_error_rate_is_inconclusive_even_with_some_red_data():
    # Only 2 of 20 scenarios produced a verdict — too little to judge safety on,
    # even though both happened to escalate correctly.
    results = [_red("red_000", "RED"), _red("red_001", "RED")]
    results += [
        _red(f"red_{i:03d}", None, "All providers failed.") for i in range(2, 20)
    ]
    outcome = decide_outcome(aggregate(results), total_scenarios=20)

    assert outcome is EvalOutcome.INCONCLUSIVE


# ---------------------------------------------------------------------------
# Reports must not cry wolf
# ---------------------------------------------------------------------------


def test_markdown_report_does_not_claim_critical_failure_without_red_data():
    results = [_red(f"red_{i:03d}", None, "All providers failed.") for i in range(10)]
    report = build_markdown_report(results, aggregate(results), None)

    assert "CRITICAL" not in report
    assert "INCONCLUSIVE" in report
    # The old report printed a "missed RED scenarios" heading with nothing under it.
    assert "Missed RED scenarios" not in report


def test_markdown_report_flags_a_real_regression():
    results = [_red(f"red_{i:03d}", "RED") for i in range(8)]
    results += [_red("red_008", "YELLOW"), _red("red_009", "GREEN")]
    report = build_markdown_report(results, aggregate(results), None)

    assert "CRITICAL" in report
    assert "Missed RED scenarios" in report
    assert "red_008" in report and "red_009" in report


def test_json_report_distinguishes_undefined_recall_from_zero():
    results = [_red(f"red_{i:03d}", None, "All providers failed.") for i in range(10)]
    summary = build_json_report(
        [{"id": r.id} for r in results], results, aggregate(results)
    )["summary"]

    assert summary["escalation_recall"] is None
    assert summary["escalation_recall_pass"] is None
    assert summary["outcome"] == "inconclusive"


def test_json_report_reports_a_real_regression():
    results = [_red(f"red_{i:03d}", "RED") for i in range(8)]
    results += [_red("red_008", "YELLOW"), _red("red_009", "GREEN")]
    summary = build_json_report(
        [{"id": r.id} for r in results], results, aggregate(results)
    )["summary"]

    assert summary["escalation_recall"] == 0.8
    assert summary["escalation_recall_pass"] is False
    assert summary["outcome"] == "safety_failure"


# ---------------------------------------------------------------------------
# Derived metrics stay well-defined on an empty run
# ---------------------------------------------------------------------------


def test_empty_metrics_do_not_report_misleading_zeros():
    m = EvalMetrics()

    assert m.escalation_recall is None
    assert m.triage_accuracy is None
    assert m.false_alarm_rate is None
