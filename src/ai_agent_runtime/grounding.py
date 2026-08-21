from __future__ import annotations

from dataclasses import dataclass, field

from .state import AgentDecision


@dataclass(frozen=True)
class GroundingResult:
    passed: bool
    reason: str | None = None
    document_versions_used: list[str] = field(default_factory=list)


def decide_after_grounding(result: GroundingResult) -> AgentDecision:
    if result.passed:
        return AgentDecision.ANSWER_GROUNDED
    return AgentDecision.HUMAN_HANDOFF_REQUIRED
