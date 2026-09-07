from __future__ import annotations

from collections.abc import Iterable

from .cases import AgentObservedOutput, EvaluationCase, EvaluationDecision, EvaluationResult, KnowledgeItem


INTERNAL_PATIENT_TERMS = (
    "rag",
    "retrieval",
    "base",
    "documento",
    "documentos",
    "score",
    "evidencia",
    "evidência",
    "nao encontrei",
    "não encontrei",
)

CALENDAR_TOOLS = ("get_availability", "consultar_agenda")


def run_evaluation(cases: Iterable[EvaluationCase]) -> list[EvaluationResult]:
    return [evaluate_case(case) for case in cases]


def evaluate_case(case: EvaluationCase) -> EvaluationResult:
    observed = case.observed
    expected = case.expected
    reasons: list[str] = []

    if observed.decision != expected.decision:
        if not (expected.allow_conflict_state and observed.decision == EvaluationDecision.CONFLICT):
            reasons.append(f"expected decision {expected.decision.value}, got {observed.decision.value}")

    missing_calls = set(expected.tool_calls) - set(observed.tool_calls)
    forbidden_calls = set(expected.forbidden_tool_calls) & set(observed.tool_calls)
    if missing_calls:
        reasons.append(f"missing expected tool calls: {sorted(missing_calls)}")
    if forbidden_calls:
        reasons.append(f"forbidden tool calls observed: {sorted(forbidden_calls)}")
    tool_selection_correct = not missing_calls and not forbidden_calls

    expected_handoff = expected.handoff_required or expected.decision == EvaluationDecision.HUMAN_HANDOFF_REQUIRED
    correct_handoff = expected_handoff and observed.decision == EvaluationDecision.HUMAN_HANDOFF_REQUIRED
    incorrect_handoff = (not expected_handoff) and observed.decision == EvaluationDecision.HUMAN_HANDOFF_REQUIRED
    if expected_handoff and observed.decision != EvaluationDecision.HUMAN_HANDOFF_REQUIRED:
        reasons.append("expected human handoff was not produced")

    if expected_handoff and not observed.handoff_context:
        reasons.append("handoff context was not preserved")
    if observed.handoff_context and observed.handoff_context.get("autonomy_interrupted") is False:
        reasons.append("handoff did not interrupt autonomous flow")
    silent_handoff_correct = True
    if "silent-handoff" in case.tags or observed.outbound_suppressed:
        silent_handoff_correct = expected_handoff and observed.outbound_suppressed and observed.response == ""
        if not silent_handoff_correct:
            reasons.append("handoff did not suppress outbound patient response")

    forbidden_claim_hits = _contained(expected.forbidden_claims, observed.response, observed.claims)
    if forbidden_claim_hits:
        reasons.append(f"forbidden claims observed: {sorted(forbidden_claim_hits)}")

    internal_terms = _internal_terms_in_response(observed.response)
    if internal_terms:
        reasons.append(f"patient response exposed internal terms: {sorted(internal_terms)}")

    evidence_by_id = {item.id: item for item in case.knowledge}
    used_evidence = [evidence_by_id[evidence_id] for evidence_id in observed.evidence_ids if evidence_id in evidence_by_id]
    unknown_evidence = [evidence_id for evidence_id in observed.evidence_ids if evidence_id not in evidence_by_id]
    if unknown_evidence:
        reasons.append(f"unknown evidence ids used: {sorted(unknown_evidence)}")

    cross_org_leakage = any(item.organization_id != case.organization_id for item in used_evidence)
    if cross_org_leakage:
        reasons.append("cross-organization evidence was used")

    ineligible_evidence = [item.id for item in used_evidence if not item.eligible_for(case.organization_id)]
    if ineligible_evidence:
        reasons.append(f"ineligible evidence was used: {sorted(ineligible_evidence)}")

    supported_facts = _supported_facts(case.organization_id, case.knowledge, observed.evidence_ids)
    unsupported_claims = [claim for claim in observed.claims if claim not in supported_facts]
    factual_decisions = {EvaluationDecision.ANSWER_GROUNDED, EvaluationDecision.NOT_OFFERED, EvaluationDecision.CALL_TOOL}
    unsupported_factual_answer = bool(unsupported_claims) and observed.decision in factual_decisions
    if unsupported_factual_answer:
        reasons.append(f"unsupported factual claims observed: {sorted(unsupported_claims)}")

    grounded_answer_correct = True
    if expected.decision == EvaluationDecision.ANSWER_GROUNDED:
        missing_facts = set(expected.expected_facts) - set(observed.facts)
        if missing_facts:
            reasons.append(f"missing expected facts: {sorted(missing_facts)}")
            grounded_answer_correct = False
        if not observed.grounding_passed:
            reasons.append("grounded answer did not pass grounding")
            grounded_answer_correct = False
        if not used_evidence:
            reasons.append("grounded answer did not cite eligible evidence")
            grounded_answer_correct = False

    grounding_rejection_correct = True
    if expected.requires_grounding_rejection:
        grounding_rejection_correct = (
            not observed.grounding_passed
            and observed.decision == EvaluationDecision.HUMAN_HANDOFF_REQUIRED
        )
        if not grounding_rejection_correct:
            reasons.append("expected grounding rejection did not force handoff")

    unauthorized_calendar_call = any(tool in CALENDAR_TOOLS for tool in observed.tool_calls) and not observed.scheduling_context_active
    if unauthorized_calendar_call:
        reasons.append("calendar tool was called outside active scheduling context")

    invented_availability = bool(set(observed.offered_slots) - set(observed.provider_slots))
    if invented_availability:
        reasons.append("offered availability not returned by provider")
    if observed.calendar_provider_error and observed.offered_slots:
        reasons.append("availability was offered after provider failure")
        invented_availability = True

    procedure_existence_correct = True
    if "procedure-existence" in case.tags and observed.decision != expected.decision:
        procedure_existence_correct = False

    crm_extraction_correct = observed.crm_fields == expected.crm_fields
    if not crm_extraction_correct:
        reasons.append(f"crm fields mismatch: expected {expected.crm_fields}, got {observed.crm_fields}")

    for key, value in expected.current_state.items():
        if observed.current_state.get(key) != value:
            reasons.append(f"state mismatch for {key}: expected {value!r}, got {observed.current_state.get(key)!r}")

    if observed.prompt_controls_changed:
        reasons.append("prompt or tool controls were changed by untrusted text")

    sales_progression_correct = True
    if "sales-progression" in case.tags:
        sales_progression_correct = observed.sales_progressed and observed.decision != EvaluationDecision.HUMAN_HANDOFF_REQUIRED
        if not sales_progression_correct:
            reasons.append("sales progression was not preserved")

    context_continuity_correct = True
    if "context-continuity" in case.tags:
        context_continuity_correct = observed.context_continuity
        if not context_continuity_correct:
            reasons.append("conversation context continuity was lost")

    no_encyclopedia_first_correct = True
    if "no-encyclopedia-first" in case.tags:
        no_encyclopedia_first_correct = not observed.encyclopedia_first
        if not no_encyclopedia_first_correct:
            reasons.append("response started as encyclopedia-style explanation")

    one_main_question_correct = True
    if "one-main-question" in case.tags:
        one_main_question_correct = observed.main_question_count <= 1
        if not one_main_question_correct:
            reasons.append("response asked too many main questions")

    grounding_failure_origin_correct = True
    if "model-introduced-unsupported-fact" in case.tags:
        grounding_failure_origin_correct = observed.grounding_failure_origin == "MODEL_INTRODUCED_UNSUPPORTED_FACT"
        if not grounding_failure_origin_correct:
            reasons.append("model-introduced grounding failure origin was not recorded")
    user_requested_unsupported_fact_case = "user-requested-unsupported-fact" in case.tags
    if "user-requested-unsupported-fact" in case.tags:
        grounding_failure_origin_correct = observed.grounding_failure_origin == "USER_REQUESTED_UNSUPPORTED_FACT"
        if not grounding_failure_origin_correct:
            reasons.append("user-requested grounding failure origin was not recorded")

    model_induced_handoff = (
        observed.grounding_failure_origin == "MODEL_INTRODUCED_UNSUPPORTED_FACT"
        and observed.decision == EvaluationDecision.HUMAN_HANDOFF_REQUIRED
    )
    if model_induced_handoff:
        reasons.append("model-introduced unsupported claim produced human handoff")

    safe_regeneration_correct = True
    safe_regeneration_case = "safe-regeneration" in case.tags
    if safe_regeneration_case:
        safe_regeneration_correct = (
            observed.response_regenerated
            and observed.grounding_failure_origin == "MODEL_INTRODUCED_UNSUPPORTED_FACT"
            and observed.decision != EvaluationDecision.HUMAN_HANDOFF_REQUIRED
        )
        if observed.safe_generation_failed:
            safe_regeneration_correct = observed.decision == EvaluationDecision.INTERNAL_GENERATION_FAILURE and observed.response == ""
        if not safe_regeneration_correct:
            reasons.append("safe regeneration did not follow the expected contract")

    conversational_zero_retrieval_progressed = True
    zero_retrieval_conversational_case = "zero-retrieval-conversational" in case.tags
    if zero_retrieval_conversational_case:
        conversational_zero_retrieval_progressed = (
            observed.retrieval_hit_count == 0
            and not observed.user_requires_evidence
            and observed.sales_progressed
            and observed.decision != EvaluationDecision.HUMAN_HANDOFF_REQUIRED
        )
        if not conversational_zero_retrieval_progressed:
            reasons.append("zero-retrieval conversational turn did not progress")

    unsupported_model_claim_escape = (
        observed.grounding_failure_origin == "MODEL_INTRODUCED_UNSUPPORTED_FACT"
        and observed.response_contains_factual_claims
        and observed.decision in {EvaluationDecision.ANSWER_GROUNDED, EvaluationDecision.CONTINUE}
        and not observed.response_regenerated
    )
    if unsupported_model_claim_escape:
        reasons.append("model-introduced unsupported factual claim escaped without safe regeneration")

    unsupported_user_fact_handoff = (
        observed.grounding_failure_origin == "USER_REQUESTED_UNSUPPORTED_FACT"
        and observed.user_requires_evidence
        and observed.decision == EvaluationDecision.HUMAN_HANDOFF_REQUIRED
        and observed.outbound_suppressed
    )
    safe_regeneration_succeeded = (
        safe_regeneration_case
        and observed.response_regenerated
        and not observed.safe_generation_failed
        and observed.decision != EvaluationDecision.INTERNAL_GENERATION_FAILURE
    )

    introduction_first_contact_case = "introduction-first-contact" in case.tags
    if introduction_first_contact_case and not observed.introduced_on_first_contact:
        reasons.append("assistant did not introduce itself on first contact")

    no_repeated_introduction_case = "no-repeated-introduction" in case.tags
    if no_repeated_introduction_case and observed.repeated_introduction:
        reasons.append("assistant repeated the initial introduction")

    minimum_discovery_case = "minimum-discovery-complete" in case.tags
    if minimum_discovery_case and not observed.minimum_discovery_complete:
        reasons.append("minimum discovery was not detected")

    discovery_efficiency_case = "discovery-efficiency" in case.tags
    if discovery_efficiency_case and not observed.discovery_efficient:
        reasons.append("discovery did not progress efficiently")

    if observed.excessive_questions:
        reasons.append("response asked excessive questions")
    if observed.excessive_recap:
        reasons.append("response repeated too much context")
    if observed.performative_empathy:
        reasons.append("response used performative empathy as default")
    if not observed.patient_context_retained:
        reasons.append("patient context was not retained")
    if not observed.discovery_information_gain:
        reasons.append("discovery did not extract new useful information")
    if not observed.anti_echo_passed:
        reasons.append("response echoed the patient mechanically")
    if observed.forced_choice_used:
        reasons.append("response used forced-choice questionnaire pattern")
    if not observed.contextual_short_answer_resolved:
        reasons.append("short contextual answer was not resolved")
    if not observed.value_bridge_timing_correct:
        reasons.append("value bridge timing was incorrect")
    if not observed.naturalness_passed:
        reasons.append("response failed naturalness checks")
    if not observed.runtime_response_completed:
        reasons.append("runtime did not complete response generation")
    if observed.internal_limitation_exposed:
        reasons.append("patient response exposed an internal limitation")
    if not observed.operational_memory_retained:
        reasons.append("operational memory was not retained")
    if observed.repeated_fact:
        reasons.append("factual information was repeated without need")
    if observed.repeated_free_evaluation:
        reasons.append("free evaluation fact was repeated without need")
    if not observed.introduction_accurate:
        reasons.append("assistant introduction state was inaccurate")
    if observed.premature_appointment_intent:
        reasons.append("appointment intent was activated prematurely")
    if observed.scheduling_stage_regression:
        reasons.append("scheduling flow regressed to discovery")
    if observed.operational_rag_call:
        reasons.append("operational registration or scheduling turn called RAG")
    if not observed.registration_field_extraction_accurate:
        reasons.append("registration field extraction was inaccurate")
    if observed.cpf_rg_cep_confusion:
        reasons.append("CPF, RG, or CEP were confused")
    if observed.redundant_confirmation:
        reasons.append("valid registration data triggered redundant confirmation")
    if not observed.missing_field_precision_correct:
        reasons.append("missing field request was imprecise")
    if observed.address_inference:
        reasons.append("address was inferred from external knowledge")
    if not observed.registration_completion_efficient:
        reasons.append("registration did not complete efficiently")
    if observed.repeated_question:
        reasons.append("known information was asked again")
    if observed.redundant_phone_request:
        reasons.append("WhatsApp phone was requested despite channel metadata")
    if not observed.registration_batch_efficient:
        reasons.append("registration data collection was not grouped efficiently")
    if observed.premature_technical_choice:
        reasons.append("patient was forced into premature technical choice")
    if observed.premature_booking_confirmation:
        reasons.append("appointment was confirmed before provider booking")
    if observed.repetitive_acknowledgement:
        reasons.append("response used repetitive acknowledgement pattern")
    if observed.patient_name_overused:
        reasons.append("patient name was overused")
    if observed.correction_repeated:
        reasons.append("name or language correction was repeated")
    if observed.markdown_artificiality:
        reasons.append("response used artificial markdown")
    if observed.em_dash_used:
        reasons.append("response overused em dash style")
    if not observed.conversational_efficiency:
        reasons.append("conversation did not stay efficient")
    if not observed.scheduling_state_accurate:
        reasons.append("scheduling state was inaccurate")
    if not observed.next_action_clear:
        reasons.append("next action was unclear")
    if not observed.current_turn_intent_accurate:
        reasons.append("current turn intent was inaccurate")
    if observed.stale_context_reused:
        reasons.append("stale commercial context was reused without current signal")
    if observed.inappropriate_context_carryover:
        reasons.append("commercial context carried over inappropriately")
    if observed.forced_cta:
        reasons.append("CTA was forced into a turn that should breathe")
    if observed.unnecessary_commercial_advance:
        reasons.append("commercial flow advanced unnecessarily")
    if observed.simple_question_overanswered:
        reasons.append("simple question was overanswered")
    if not observed.topic_change_accurate:
        reasons.append("topic change was not resolved accurately")
    if not observed.side_query_accurate:
        reasons.append("side query was not handled accurately")
    if not observed.pending_cta_resolution_accurate:
        reasons.append("pending CTA was resolved inaccurately")
    if not observed.conversational_naturalness:
        reasons.append("conversational naturalness was poor")
    if observed.historical_fact_intrusion:
        reasons.append("historical factual context intruded into current turn")

    fatigue_response_case = "fatigue-response" in case.tags
    if fatigue_response_case and not observed.fatigue_response_correct:
        reasons.append("conversation fatigue did not reduce discovery")

    objection_handling_case = "objection-handling" in case.tags
    if objection_handling_case and not observed.objection_handled:
        reasons.append("objection was not handled commercially")

    appointment_progression_case = "appointment-progression" in case.tags
    if appointment_progression_case and not observed.appointment_progressed:
        reasons.append("appointment or CTA progression did not happen")

    value_bridge_case = "value-bridge" in case.tags
    if value_bridge_case and not observed.value_bridge_used:
        reasons.append("value bridge was not used before CTA")

    value_bridge_relevance_case = "value-bridge-relevance" in case.tags
    if value_bridge_relevance_case and not observed.value_bridge_relevant:
        reasons.append("value bridge was not relevant to patient need")

    assistant_name_not_patient_name_correct = not observed.assistant_name_extracted_as_patient_name
    if not assistant_name_not_patient_name_correct:
        reasons.append("assistant name was extracted as patient name")

    unsupported_fact_escape = unsupported_factual_answer or observed.unsupported_fact_escape
    if observed.unsupported_fact_escape:
        reasons.append("unsupported factual content escaped in commercial flow")

    passed = not reasons
    return EvaluationResult(
        case_id=case.id,
        category=case.category,
        passed=passed,
        reasons=tuple(reasons),
        unsupported_factual_answer=unsupported_factual_answer,
        incorrect_handoff=incorrect_handoff,
        expected_handoff=expected_handoff,
        correct_handoff=correct_handoff,
        tool_selection_correct=tool_selection_correct,
        unauthorized_calendar_call=unauthorized_calendar_call,
        invented_availability=invented_availability,
        procedure_existence_correct=procedure_existence_correct,
        cross_org_leakage=cross_org_leakage,
        grounding_rejection_correct=grounding_rejection_correct,
        crm_extraction_correct=crm_extraction_correct,
        grounded_answer_correct=grounded_answer_correct,
        silent_handoff_correct=silent_handoff_correct,
        sales_progression_correct=sales_progression_correct,
        context_continuity_correct=context_continuity_correct,
        no_encyclopedia_first_correct=no_encyclopedia_first_correct,
        one_main_question_correct=one_main_question_correct,
        grounding_failure_origin_correct=grounding_failure_origin_correct,
        safe_regeneration_correct=safe_regeneration_correct,
        model_induced_handoff=model_induced_handoff,
        conversational_zero_retrieval_progressed=conversational_zero_retrieval_progressed,
        unsupported_model_claim_escape=unsupported_model_claim_escape,
        unsupported_user_fact_handoff=unsupported_user_fact_handoff,
        safe_regeneration_succeeded=safe_regeneration_succeeded,
        user_requested_unsupported_fact_case=user_requested_unsupported_fact_case,
        safe_regeneration_case=safe_regeneration_case,
        zero_retrieval_conversational_case=zero_retrieval_conversational_case,
        introduction_first_contact_case=introduction_first_contact_case,
        no_repeated_introduction_case=no_repeated_introduction_case,
        minimum_discovery_case=minimum_discovery_case,
        discovery_efficiency_case=discovery_efficiency_case,
        fatigue_response_case=fatigue_response_case,
        objection_handling_case=objection_handling_case,
        appointment_progression_case=appointment_progression_case,
        unsupported_fact_escape=unsupported_fact_escape,
        excessive_questions=observed.excessive_questions,
        excessive_recap=observed.excessive_recap,
        value_bridge_case=value_bridge_case,
        value_bridge_relevance_case=value_bridge_relevance_case,
        performative_empathy=observed.performative_empathy,
        assistant_name_not_patient_name_correct=assistant_name_not_patient_name_correct,
        patient_context_retention_correct=observed.patient_context_retained,
        discovery_information_gain_correct=observed.discovery_information_gain,
        anti_echo_correct=observed.anti_echo_passed,
        forced_choice_used=observed.forced_choice_used,
        contextual_short_answer_resolution_correct=observed.contextual_short_answer_resolved,
        conversation_evidence_reused=observed.conversation_evidence_reused,
        value_bridge_timing_correct=observed.value_bridge_timing_correct,
        naturalness_correct=observed.naturalness_passed,
        runtime_response_completion_correct=observed.runtime_response_completed,
        internal_limitation_exposure=observed.internal_limitation_exposed,
        operational_memory_retention_correct=observed.operational_memory_retained,
        repeated_fact=observed.repeated_fact,
        repeated_free_evaluation=observed.repeated_free_evaluation,
        introduction_accuracy_correct=observed.introduction_accurate,
        premature_appointment_intent=observed.premature_appointment_intent,
        scheduling_stage_regression=observed.scheduling_stage_regression,
        operational_rag_call=observed.operational_rag_call,
        registration_field_extraction_correct=observed.registration_field_extraction_accurate,
        cpf_rg_cep_confusion=observed.cpf_rg_cep_confusion,
        redundant_confirmation=observed.redundant_confirmation,
        missing_field_precision_correct=observed.missing_field_precision_correct,
        address_inference=observed.address_inference,
        registration_completion_efficiency_correct=observed.registration_completion_efficient,
        repeated_question=observed.repeated_question,
        redundant_phone_request=observed.redundant_phone_request,
        registration_batch_efficiency_correct=observed.registration_batch_efficient,
        premature_technical_choice=observed.premature_technical_choice,
        premature_booking_confirmation=observed.premature_booking_confirmation,
        repetitive_acknowledgement=observed.repetitive_acknowledgement,
        patient_name_overuse=observed.patient_name_overused,
        correction_repetition=observed.correction_repeated,
        markdown_artificiality=observed.markdown_artificiality,
        em_dash_usage=observed.em_dash_used,
        conversational_efficiency_correct=observed.conversational_efficiency,
        scheduling_state_accuracy_correct=observed.scheduling_state_accurate,
        next_action_clarity_correct=observed.next_action_clear,
        current_turn_intent_accuracy_correct=observed.current_turn_intent_accurate,
        stale_context_reuse=observed.stale_context_reused,
        inappropriate_context_carryover=observed.inappropriate_context_carryover,
        forced_cta=observed.forced_cta,
        unnecessary_commercial_advance=observed.unnecessary_commercial_advance,
        simple_question_overanswer=observed.simple_question_overanswered,
        topic_change_accuracy_correct=observed.topic_change_accurate,
        side_query_accuracy_correct=observed.side_query_accurate,
        pending_cta_resolution_accuracy_correct=observed.pending_cta_resolution_accurate,
        conversational_naturalness_correct=observed.conversational_naturalness,
        historical_fact_intrusion=observed.historical_fact_intrusion,
    )


def _supported_facts(organization_id: str, knowledge: tuple[KnowledgeItem, ...], evidence_ids: tuple[str, ...]) -> set[str]:
    evidence_by_id = {item.id: item for item in knowledge}
    facts: set[str] = set()
    for evidence_id in evidence_ids:
        item = evidence_by_id.get(evidence_id)
        if item and item.eligible_for(organization_id):
            facts.update(item.facts)
    return facts


def _contained(expected_terms: tuple[str, ...], response: str, claims: tuple[str, ...]) -> set[str]:
    haystack = " ".join((response, *claims)).lower()
    return {term for term in expected_terms if term.lower() in haystack}


def _internal_terms_in_response(response: str) -> set[str]:
    text = (response or "").lower()
    normalized = text.replace("ã", "a").replace("á", "a").replace("ç", "c").replace("é", "e").replace("ê", "e").replace("í", "i").replace("ó", "o").replace("ô", "o").replace("ú", "u")
    extra = (
        "nao consigo confirmar",
        "nao tenho essa informacao",
        "nao consigo afirmar",
        "nao tenho acesso",
        "segundo os dados disponiveis",
        "a equipe pode verificar",
        "falta de evidencia",
    )
    return {term for term in INTERNAL_PATIENT_TERMS if term in text or term in normalized} | {term for term in extra if term in normalized}
