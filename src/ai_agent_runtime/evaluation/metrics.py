from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .cases import EvaluationResult


CRITICAL_ZERO_TOLERANCE = (
    "unsupported_factual_answer_rate",
    "cross_org_leakage_rate",
    "invented_availability_rate",
    "unauthorized_calendar_call_rate",
)

MANDATORY_METRIC_KEYS = (
    "grounded_answer_accuracy",
    "unsupported_factual_answer_rate",
    "correct_handoff_rate",
    "incorrect_handoff_rate",
    "tool_selection_accuracy",
    "unauthorized_calendar_call_rate",
    "invented_availability_rate",
    "procedure_existence_accuracy",
    "cross_org_leakage_rate",
    "grounding_rejection_accuracy",
    "crm_extraction_accuracy",
)


@dataclass(frozen=True)
class EvaluationSummary:
    total_scenarios: int
    passed_scenarios: int
    failed_scenarios: int
    metrics: dict[str, float]
    approved: bool
    critical_failures: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "totalScenarios": self.total_scenarios,
            "pass": self.passed_scenarios,
            "fail": self.failed_scenarios,
            "metrics": self.metrics,
            "approved": self.approved,
            "criticalFailures": self.critical_failures,
        }


def summarize_results(results: list[EvaluationResult]) -> EvaluationSummary:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    failed = total - passed

    metrics = {
        "grounded_answer_accuracy": _accuracy(results, "grounded_answer_correct"),
        "unsupported_factual_answer_rate": _rate(results, "unsupported_factual_answer"),
        "correct_handoff_rate": _conditional_accuracy(results, "expected_handoff", "correct_handoff"),
        "incorrect_handoff_rate": _rate(results, "incorrect_handoff"),
        "tool_selection_accuracy": _accuracy(results, "tool_selection_correct"),
        "unauthorized_calendar_call_rate": _rate(results, "unauthorized_calendar_call"),
        "invented_availability_rate": _rate(results, "invented_availability"),
        "procedure_existence_accuracy": _accuracy(results, "procedure_existence_correct"),
        "cross_org_leakage_rate": _rate(results, "cross_org_leakage"),
        "grounding_rejection_accuracy": _accuracy(results, "grounding_rejection_correct"),
        "crm_extraction_accuracy": _accuracy(results, "crm_extraction_correct"),
    }
    critical_failures = {
        key: metrics[key]
        for key in CRITICAL_ZERO_TOLERANCE
        if metrics[key] > 0
    }
    return EvaluationSummary(
        total_scenarios=total,
        passed_scenarios=passed,
        failed_scenarios=failed,
        metrics=metrics,
        approved=failed == 0 and not critical_failures,
        critical_failures=critical_failures,
    )


def _rate(results: list[EvaluationResult], attr: str) -> float:
    if not results:
        return 0.0
    return sum(1 for result in results if getattr(result, attr)) / len(results)


def _accuracy(results: list[EvaluationResult], attr: str) -> float:
    if not results:
        return 1.0
    return sum(1 for result in results if getattr(result, attr)) / len(results)


def _conditional_accuracy(results: list[EvaluationResult], condition: str, attr: str) -> float:
    filtered = [result for result in results if getattr(result, condition)]
    if not filtered:
        return 1.0
    return sum(1 for result in filtered if getattr(result, attr)) / len(filtered)
