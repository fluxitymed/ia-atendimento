from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .cases import EvaluationResult


CRITICAL_ZERO_TOLERANCE = (
    "unsupported_factual_answer_rate",
    "cross_org_leakage_rate",
    "invented_availability_rate",
    "unauthorized_calendar_call_rate",
    "model_induced_handoff_rate",
    "unsupported_model_claim_escape_rate",
    "unsupported_fact_escape_rate",
    "performative_empathy_rate",
    "forced_choice_rate",
    "internal_limitation_exposure_rate",
    "repeated_fact_rate",
    "repeated_free_evaluation_rate",
    "premature_appointment_intent_rate",
    "scheduling_stage_regression_rate",
    "operational_rag_call_rate",
    "cpf_rg_cep_confusion_rate",
    "redundant_confirmation_rate",
    "address_inference_rate",
    "repeated_question_rate",
    "redundant_phone_request_rate",
    "premature_technical_choice_rate",
    "premature_booking_confirmation_rate",
    "repetitive_acknowledgement_rate",
    "patient_name_overuse_rate",
    "correction_repetition_rate",
    "markdown_artificiality_rate",
    "em_dash_rate",
    "stale_context_reuse_rate",
    "inappropriate_context_carryover_rate",
    "forced_cta_rate",
    "unnecessary_commercial_advance_rate",
    "simple_question_overanswer_rate",
    "historical_fact_intrusion_rate",
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
    "silent_handoff_rate",
    "no_unnecessary_handoff_rate",
    "sales_progression_rate",
    "context_continuity_rate",
    "no_encyclopedia_first_rate",
    "one_main_question_rate",
    "model_induced_handoff_rate",
    "conversational_zero_retrieval_progression_rate",
    "unsupported_model_claim_escape_rate",
    "unsupported_user_fact_handoff_rate",
    "safe_regeneration_success_rate",
    "introduction_on_first_contact_rate",
    "no_repeated_introduction_rate",
    "discovery_efficiency_rate",
    "minimum_discovery_completion_rate",
    "excessive_question_rate",
    "excessive_recap_rate",
    "conversation_fatigue_response_rate",
    "objection_handling_rate",
    "appointment_progression_rate",
    "value_bridge_rate",
    "value_bridge_relevance_rate",
    "no_performative_empathy_rate",
    "assistant_name_not_patient_name_rate",
    "unsupported_fact_escape_rate",
    "performative_empathy_rate",
    "patient_context_retention_rate",
    "discovery_information_gain_rate",
    "anti_echo_rate",
    "forced_choice_rate",
    "contextual_short_answer_resolution_rate",
    "conversation_evidence_reuse_rate",
    "value_bridge_timing_rate",
    "naturalness_rate",
    "runtime_response_completion_rate",
    "internal_limitation_exposure_rate",
    "operational_memory_retention_rate",
    "repeated_fact_rate",
    "repeated_free_evaluation_rate",
    "introduction_accuracy",
    "premature_appointment_intent_rate",
    "scheduling_stage_regression_rate",
    "operational_rag_call_rate",
    "registration_field_extraction_accuracy",
    "cpf_rg_cep_confusion_rate",
    "redundant_confirmation_rate",
    "missing_field_precision",
    "address_inference_rate",
    "registration_completion_efficiency",
    "repeated_question_rate",
    "redundant_phone_request_rate",
    "registration_batch_efficiency_rate",
    "premature_technical_choice_rate",
    "premature_booking_confirmation_rate",
    "repetitive_acknowledgement_rate",
    "patient_name_overuse_rate",
    "correction_repetition_rate",
    "markdown_artificiality_rate",
    "em_dash_rate",
    "conversational_efficiency_rate",
    "scheduling_state_accuracy_rate",
    "next_action_clarity_rate",
    "current_turn_intent_accuracy",
    "stale_context_reuse_rate",
    "inappropriate_context_carryover_rate",
    "forced_cta_rate",
    "unnecessary_commercial_advance_rate",
    "simple_question_overanswer_rate",
    "topic_change_accuracy",
    "side_query_accuracy",
    "pending_cta_resolution_accuracy",
    "conversational_naturalness",
    "historical_fact_intrusion_rate",
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
        "silent_handoff_rate": _accuracy(results, "silent_handoff_correct"),
        "no_unnecessary_handoff_rate": 1 - _rate(results, "incorrect_handoff"),
        "sales_progression_rate": _accuracy(results, "sales_progression_correct"),
        "context_continuity_rate": _accuracy(results, "context_continuity_correct"),
        "no_encyclopedia_first_rate": _accuracy(results, "no_encyclopedia_first_correct"),
        "one_main_question_rate": _accuracy(results, "one_main_question_correct"),
        "model_induced_handoff_rate": _rate(results, "model_induced_handoff"),
        "conversational_zero_retrieval_progression_rate": _conditional_accuracy(results, "zero_retrieval_conversational_case", "conversational_zero_retrieval_progressed"),
        "unsupported_model_claim_escape_rate": _rate(results, "unsupported_model_claim_escape"),
        "unsupported_user_fact_handoff_rate": _conditional_accuracy(results, "user_requested_unsupported_fact_case", "unsupported_user_fact_handoff"),
        "safe_regeneration_success_rate": _conditional_accuracy(results, "safe_regeneration_case", "safe_regeneration_succeeded"),
        "introduction_on_first_contact_rate": _conditional_accuracy(results, "introduction_first_contact_case", "passed"),
        "no_repeated_introduction_rate": _conditional_accuracy(results, "no_repeated_introduction_case", "passed"),
        "discovery_efficiency_rate": _conditional_accuracy(results, "discovery_efficiency_case", "passed"),
        "minimum_discovery_completion_rate": _conditional_accuracy(results, "minimum_discovery_case", "passed"),
        "excessive_question_rate": _rate(results, "excessive_questions"),
        "excessive_recap_rate": _rate(results, "excessive_recap"),
        "conversation_fatigue_response_rate": _conditional_accuracy(results, "fatigue_response_case", "passed"),
        "objection_handling_rate": _conditional_accuracy(results, "objection_handling_case", "passed"),
        "appointment_progression_rate": _conditional_accuracy(results, "appointment_progression_case", "passed"),
        "value_bridge_rate": _conditional_accuracy(results, "value_bridge_case", "passed"),
        "value_bridge_relevance_rate": _conditional_accuracy(results, "value_bridge_relevance_case", "passed"),
        "no_performative_empathy_rate": 1 - _rate(results, "performative_empathy"),
        "assistant_name_not_patient_name_rate": _accuracy(results, "assistant_name_not_patient_name_correct"),
        "unsupported_fact_escape_rate": _rate(results, "unsupported_fact_escape"),
        "performative_empathy_rate": _rate(results, "performative_empathy"),
        "patient_context_retention_rate": _accuracy(results, "patient_context_retention_correct"),
        "discovery_information_gain_rate": _accuracy(results, "discovery_information_gain_correct"),
        "anti_echo_rate": _accuracy(results, "anti_echo_correct"),
        "forced_choice_rate": _rate(results, "forced_choice_used"),
        "contextual_short_answer_resolution_rate": _accuracy(results, "contextual_short_answer_resolution_correct"),
        "conversation_evidence_reuse_rate": _rate(results, "conversation_evidence_reused"),
        "value_bridge_timing_rate": _accuracy(results, "value_bridge_timing_correct"),
        "naturalness_rate": _accuracy(results, "naturalness_correct"),
        "runtime_response_completion_rate": _accuracy(results, "runtime_response_completion_correct"),
        "internal_limitation_exposure_rate": _rate(results, "internal_limitation_exposure"),
        "operational_memory_retention_rate": _accuracy(results, "operational_memory_retention_correct"),
        "repeated_fact_rate": _rate(results, "repeated_fact"),
        "repeated_free_evaluation_rate": _rate(results, "repeated_free_evaluation"),
        "introduction_accuracy": _accuracy(results, "introduction_accuracy_correct"),
        "premature_appointment_intent_rate": _rate(results, "premature_appointment_intent"),
        "scheduling_stage_regression_rate": _rate(results, "scheduling_stage_regression"),
        "operational_rag_call_rate": _rate(results, "operational_rag_call"),
        "registration_field_extraction_accuracy": _accuracy(results, "registration_field_extraction_correct"),
        "cpf_rg_cep_confusion_rate": _rate(results, "cpf_rg_cep_confusion"),
        "redundant_confirmation_rate": _rate(results, "redundant_confirmation"),
        "missing_field_precision": _accuracy(results, "missing_field_precision_correct"),
        "address_inference_rate": _rate(results, "address_inference"),
        "registration_completion_efficiency": _accuracy(results, "registration_completion_efficiency_correct"),
        "repeated_question_rate": _rate(results, "repeated_question"),
        "redundant_phone_request_rate": _rate(results, "redundant_phone_request"),
        "registration_batch_efficiency_rate": _accuracy(results, "registration_batch_efficiency_correct"),
        "premature_technical_choice_rate": _rate(results, "premature_technical_choice"),
        "premature_booking_confirmation_rate": _rate(results, "premature_booking_confirmation"),
        "repetitive_acknowledgement_rate": _rate(results, "repetitive_acknowledgement"),
        "patient_name_overuse_rate": _rate(results, "patient_name_overuse"),
        "correction_repetition_rate": _rate(results, "correction_repetition"),
        "markdown_artificiality_rate": _rate(results, "markdown_artificiality"),
        "em_dash_rate": _rate(results, "em_dash_usage"),
        "conversational_efficiency_rate": _accuracy(results, "conversational_efficiency_correct"),
        "scheduling_state_accuracy_rate": _accuracy(results, "scheduling_state_accuracy_correct"),
        "next_action_clarity_rate": _accuracy(results, "next_action_clarity_correct"),
        "current_turn_intent_accuracy": _accuracy(results, "current_turn_intent_accuracy_correct"),
        "stale_context_reuse_rate": _rate(results, "stale_context_reuse"),
        "inappropriate_context_carryover_rate": _rate(results, "inappropriate_context_carryover"),
        "forced_cta_rate": _rate(results, "forced_cta"),
        "unnecessary_commercial_advance_rate": _rate(results, "unnecessary_commercial_advance"),
        "simple_question_overanswer_rate": _rate(results, "simple_question_overanswer"),
        "topic_change_accuracy": _accuracy(results, "topic_change_accuracy_correct"),
        "side_query_accuracy": _accuracy(results, "side_query_accuracy_correct"),
        "pending_cta_resolution_accuracy": _accuracy(results, "pending_cta_resolution_accuracy_correct"),
        "conversational_naturalness": _accuracy(results, "conversational_naturalness_correct"),
        "historical_fact_intrusion_rate": _rate(results, "historical_fact_intrusion"),
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
