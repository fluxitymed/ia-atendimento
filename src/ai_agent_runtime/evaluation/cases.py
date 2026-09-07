from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvaluationDecision(str, Enum):
    ANSWER_GROUNDED = "ANSWER_GROUNDED"
    HUMAN_HANDOFF_REQUIRED = "HUMAN_HANDOFF_REQUIRED"
    INTERNAL_GENERATION_FAILURE = "INTERNAL_GENERATION_FAILURE"
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
    outbound_suppressed: bool = False
    sales_progressed: bool = False
    main_question_count: int = 0
    encyclopedia_first: bool = False
    repeated_response: bool = False
    context_continuity: bool = True
    user_requires_evidence: bool = False
    response_contains_factual_claims: bool = False
    grounding_failure_origin: str | None = None
    response_regenerated: bool = False
    safe_generation_failed: bool = False
    retrieval_hit_count: int | None = None
    introduced_on_first_contact: bool = False
    repeated_introduction: bool = False
    minimum_discovery_complete: bool = False
    discovery_efficient: bool = True
    excessive_questions: bool = False
    excessive_recap: bool = False
    fatigue_response_correct: bool = True
    objection_handled: bool = True
    appointment_progressed: bool = True
    unsupported_fact_escape: bool = False
    value_bridge_used: bool = True
    value_bridge_relevant: bool = True
    performative_empathy: bool = False
    assistant_name_extracted_as_patient_name: bool = False
    patient_context_retained: bool = True
    discovery_information_gain: bool = True
    anti_echo_passed: bool = True
    forced_choice_used: bool = False
    contextual_short_answer_resolved: bool = True
    conversation_evidence_reused: bool = False
    value_bridge_timing_correct: bool = True
    naturalness_passed: bool = True
    runtime_response_completed: bool = True
    internal_limitation_exposed: bool = False
    operational_memory_retained: bool = True
    repeated_fact: bool = False
    repeated_free_evaluation: bool = False
    introduction_accurate: bool = True
    premature_appointment_intent: bool = False
    scheduling_stage_regression: bool = False
    operational_rag_call: bool = False
    registration_field_extraction_accurate: bool = True
    cpf_rg_cep_confusion: bool = False
    redundant_confirmation: bool = False
    missing_field_precision_correct: bool = True
    address_inference: bool = False
    registration_completion_efficient: bool = True
    repeated_question: bool = False
    redundant_phone_request: bool = False
    registration_batch_efficient: bool = True
    premature_technical_choice: bool = False
    premature_booking_confirmation: bool = False
    repetitive_acknowledgement: bool = False
    patient_name_overused: bool = False
    correction_repeated: bool = False
    markdown_artificiality: bool = False
    em_dash_used: bool = False
    conversational_efficiency: bool = True
    scheduling_state_accurate: bool = True
    next_action_clear: bool = True
    current_turn_intent_accurate: bool = True
    stale_context_reused: bool = False
    inappropriate_context_carryover: bool = False
    forced_cta: bool = False
    unnecessary_commercial_advance: bool = False
    simple_question_overanswered: bool = False
    topic_change_accurate: bool = True
    side_query_accurate: bool = True
    pending_cta_resolution_accurate: bool = True
    conversational_naturalness: bool = True
    historical_fact_intrusion: bool = False


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
    silent_handoff_correct: bool = True
    sales_progression_correct: bool = True
    context_continuity_correct: bool = True
    no_encyclopedia_first_correct: bool = True
    one_main_question_correct: bool = True
    grounding_failure_origin_correct: bool = True
    safe_regeneration_correct: bool = True
    model_induced_handoff: bool = False
    conversational_zero_retrieval_progressed: bool = True
    unsupported_model_claim_escape: bool = False
    unsupported_user_fact_handoff: bool = False
    safe_regeneration_succeeded: bool = False
    user_requested_unsupported_fact_case: bool = False
    safe_regeneration_case: bool = False
    zero_retrieval_conversational_case: bool = False
    introduction_first_contact_case: bool = False
    no_repeated_introduction_case: bool = False
    minimum_discovery_case: bool = False
    discovery_efficiency_case: bool = False
    fatigue_response_case: bool = False
    objection_handling_case: bool = False
    appointment_progression_case: bool = False
    unsupported_fact_escape: bool = False
    excessive_questions: bool = False
    excessive_recap: bool = False
    value_bridge_case: bool = False
    value_bridge_relevance_case: bool = False
    performative_empathy: bool = False
    assistant_name_not_patient_name_correct: bool = True
    patient_context_retention_correct: bool = True
    discovery_information_gain_correct: bool = True
    anti_echo_correct: bool = True
    forced_choice_used: bool = False
    contextual_short_answer_resolution_correct: bool = True
    conversation_evidence_reused: bool = False
    value_bridge_timing_correct: bool = True
    naturalness_correct: bool = True
    runtime_response_completion_correct: bool = True
    internal_limitation_exposure: bool = False
    operational_memory_retention_correct: bool = True
    repeated_fact: bool = False
    repeated_free_evaluation: bool = False
    introduction_accuracy_correct: bool = True
    premature_appointment_intent: bool = False
    scheduling_stage_regression: bool = False
    operational_rag_call: bool = False
    registration_field_extraction_correct: bool = True
    cpf_rg_cep_confusion: bool = False
    redundant_confirmation: bool = False
    missing_field_precision_correct: bool = True
    address_inference: bool = False
    registration_completion_efficiency_correct: bool = True
    repeated_question: bool = False
    redundant_phone_request: bool = False
    registration_batch_efficiency_correct: bool = True
    premature_technical_choice: bool = False
    premature_booking_confirmation: bool = False
    repetitive_acknowledgement: bool = False
    patient_name_overuse: bool = False
    correction_repetition: bool = False
    markdown_artificiality: bool = False
    em_dash_usage: bool = False
    conversational_efficiency_correct: bool = True
    scheduling_state_accuracy_correct: bool = True
    next_action_clarity_correct: bool = True
    current_turn_intent_accuracy_correct: bool = True
    stale_context_reuse: bool = False
    inappropriate_context_carryover: bool = False
    forced_cta: bool = False
    unnecessary_commercial_advance: bool = False
    simple_question_overanswer: bool = False
    topic_change_accuracy_correct: bool = True
    side_query_accuracy_correct: bool = True
    pending_cta_resolution_accuracy_correct: bool = True
    conversational_naturalness_correct: bool = True
    historical_fact_intrusion: bool = False
