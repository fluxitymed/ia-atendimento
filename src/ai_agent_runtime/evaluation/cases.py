from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvaluationDecision(str, Enum):
    ANSWER_GROUNDED = "ANSWER_GROUNDED"
    HUMAN_HANDOFF_REQUIRED = "HUMAN_HANDOFF_REQUIRED"
    NOT_OFFERED = "NOT_OFFERED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    CALL_TOOL = "CALL_TOOL"
    CONFLICT = "CONFLICT"
    CONTINUE = "CONTINUE"


class KnowledgeStatus(str, Enum):
    PUBLISHED = "PUBLISHED"
    SUPERSEDED = "SUPERSEDED"
    INACTIVE = "INACTIVE"
    DRAFT = "DRAFT"
    FUTURE = "FUTURE"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class KnowledgeItem:
    id: str
    organization_id: str
    content: str
    facts: tuple[str, ...] = ()
    status: KnowledgeStatus = KnowledgeStatus.PUBLISHED
    approved: bool = True
    current: bool = True
    valid_now: bool = True
    source_type: str = "DOCUMENT"
    closed_world: bool = False
    complete: bool = False
    score: float = 0.0
    contains_prompt_injection: bool = False

    def eligible_for(self, organization_id: str) -> bool:
        return (
            self.organization_id == organization_id
            and self.status == KnowledgeStatus.PUBLISHED
            and self.approved
            and self.current
            and self.valid_now
        )

    def authoritative_closed_world_for(self, organization_id: str) -> bool:
        return self.eligible_for(organization_id) and self.closed_world and self.complete


@dataclass(frozen=True)
class ExpectedOutcome:
    decision: EvaluationDecision
    tool_calls: tuple[str, ...] = ()
    forbidden_tool_calls: tuple[str, ...] = ()
    handoff_required: bool = False
    expected_facts: tuple[str, ...] = ()
    forbidden_claims: tuple[str, ...] = ()
    crm_fields: dict[str, Any] = field(default_factory=dict)
    current_state: dict[str, Any] = field(default_factory=dict)
    requires_grounding_rejection: bool = False
    allow_conflict_state: bool = False


@dataclass(frozen=True)
class AgentObservedOutput:
    decision: EvaluationDecision
    response: str = ""
    tool_calls: tuple[str, ...] = ()
    facts: tuple[str, ...] = ()
    claims: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    grounding_passed: bool = False
    handoff_context: dict[str, Any] | None = None
    crm_fields: dict[str, Any] = field(default_factory=dict)
    current_state: dict[str, Any] = field(default_factory=dict)
    scheduling_context_active: bool = False
    provider_slots: tuple[str, ...] = ()
    offered_slots: tuple[str, ...] = ()
    calendar_provider_error: str | None = None
    prompt_controls_changed: bool = False


@dataclass(frozen=True)
class EvaluationCase:
    id: str
    description: str
    category: str
    organization_id: str
    messages: tuple[str, ...]
    expected: ExpectedOutcome
    observed: AgentObservedOutput
    knowledge: tuple[KnowledgeItem, ...] = ()
    version: str = "2026-08-20.offline.v1"
    fictitious_data: bool = True
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluationResult:
    case_id: str
    category: str
    passed: bool
    reasons: tuple[str, ...]
    unsupported_factual_answer: bool = False
    incorrect_handoff: bool = False
    expected_handoff: bool = False
    correct_handoff: bool = False
    tool_selection_correct: bool = True
    unauthorized_calendar_call: bool = False
    invented_availability: bool = False
    procedure_existence_correct: bool = True
    cross_org_leakage: bool = False
    grounding_rejection_correct: bool = True
    crm_extraction_correct: bool = True
    grounded_answer_correct: bool = True
