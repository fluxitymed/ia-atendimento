from __future__ import annotations

from .cases import EvaluationResult
from .metrics import EvaluationSummary


def build_report(summary: EvaluationSummary, results: list[EvaluationResult]) -> str:
    lines = [
        f"Total scenarios: {summary.total_scenarios}",
        f"PASS: {summary.passed_scenarios}",
        f"FAIL: {summary.failed_scenarios}",
        "",
        "Metrics:",
    ]
    for key in sorted(summary.metrics):
        lines.append(f"- {key}: {summary.metrics[key]:.4f}")
    if summary.critical_failures:
        lines.append("")
        lines.append("Critical failures:")
        for key, value in sorted(summary.critical_failures.items()):
            lines.append(f"- {key}: {value:.4f}")
    failed = [result for result in results if not result.passed]
    if failed:
        lines.append("")
        lines.append("Failed scenarios:")
        for result in failed:
            lines.append(f"- {result.case_id}: {'; '.join(result.reasons)}")
    return "\n".join(lines)
