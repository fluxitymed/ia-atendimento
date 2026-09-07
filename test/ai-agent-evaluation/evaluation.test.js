'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

function runPython(source) {
  const result = spawnSync('python3', ['-c', source], {
    cwd: process.cwd(),
    env: { ...process.env, PYTHONPATH: 'src' },
    encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout.trim();
}

test('@spec:AC-067 @spec:AC-068 @spec:AC-069 evaluation cases, runner, and fictitious dataset are reusable offline', () => {
  const output = runPython(`
import json
from ai_agent_runtime.evaluation import EvaluationDecision, load_initial_dataset, run_evaluation

cases = load_initial_dataset()
results = run_evaluation(cases)
sample = cases[0]
print(json.dumps({
  "count": len(cases),
  "allPass": all(result.passed for result in results),
  "allVersioned": all(case.version == "2026-08-20.offline.v1" for case in cases),
  "realCaseIds": sorted(case.id for case in cases if not case.fictitious_data),
  "sample": {
    "id": sample.id,
    "description": sample.description,
    "organization": sample.organization_id,
    "messages": list(sample.messages),
    "knowledgeCount": len(sample.knowledge),
    "decision": sample.expected.decision.value,
    "toolCalls": list(sample.expected.tool_calls),
    "forbiddenToolCalls": list(sample.expected.forbidden_tool_calls),
    "handoff": sample.expected.handoff_required,
    "facts": list(sample.expected.expected_facts),
    "forbiddenClaims": list(sample.expected.forbidden_claims),
  },
  "statuses": sorted(set("PASS" if result.passed else "FAIL" for result in results)),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.count, 71);
  assert.equal(parsed.allPass, true);
  assert.equal(parsed.allVersioned, true);
  assert.deepEqual(parsed.realCaseIds, ['SALES-019', 'SALES-020', 'SALES-021', 'SALES-022', 'SALES-023', 'SALES-024', 'SALES-025', 'SALES-026']);
  assert.equal(parsed.sample.id, 'RAG-001');
  assert.equal(parsed.sample.organization, 'CLINICA_A_FICTICIA');
  assert.deepEqual(parsed.sample.messages, ['Vocês fazem Botox?']);
  assert.equal(parsed.sample.knowledgeCount, 1);
  assert.equal(parsed.sample.decision, 'ANSWER_GROUNDED');
  assert.deepEqual(parsed.sample.facts, ['Botox oferecido']);
  assert.deepEqual(parsed.statuses, ['PASS']);
});

test('@spec:AC-070 @spec:AC-071 metrics report mandatory rates and fail zero-tolerance violations', () => {
  const output = runPython(`
import json
from dataclasses import replace
from ai_agent_runtime.evaluation import MANDATORY_METRIC_KEYS, build_report, load_initial_dataset, run_evaluation, summarize_results
from ai_agent_runtime.evaluation.cases import AgentObservedOutput, EvaluationDecision

cases = load_initial_dataset()
summary = summarize_results(run_evaluation(cases))
bad_case = replace(
    next(case for case in cases if case.id == "SRC-003"),
    observed=AgentObservedOutput(
        decision=EvaluationDecision.ANSWER_GROUNDED,
        response="A consulta custa R$ 900.",
        claims=("Consulta dermatologica custa R$ 900",),
        evidence_ids=("doc-consulta-b",),
        grounding_passed=True,
    ),
)
bad_summary = summarize_results(run_evaluation([bad_case]))
report = build_report(summary, run_evaluation(cases))
print(json.dumps({
  "keys": sorted(summary.metrics.keys()),
  "mandatory": sorted(MANDATORY_METRIC_KEYS),
  "approved": summary.approved,
  "badApproved": bad_summary.approved,
  "badCritical": bad_summary.critical_failures,
    "reportHasTotal": "Total scenarios: 71" in report,
}))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed.keys, parsed.mandatory);
  assert.equal(parsed.approved, true);
  assert.equal(parsed.badApproved, false);
  assert.equal(parsed.badCritical.cross_org_leakage_rate, 1);
  assert.equal(parsed.badCritical.unsupported_factual_answer_rate, 1);
  assert.equal(parsed.reportHasTotal, true);
});

test('@spec:AC-231 @spec:AC-232 @spec:AC-233 @spec:AC-234 @spec:AC-240 @spec:AC-241 @spec:AC-249 @spec:AC-250 @spec:AC-251 @spec:AC-252 @spec:AC-253 @spec:AC-273 @spec:AC-274 @spec:AC-275 @spec:AC-276 @spec:AC-277 @spec:AC-278 @spec:AC-279 @spec:AC-286 @spec:AC-287 @spec:AC-288 @spec:AC-289 @spec:AC-290 commercial evaluation covers sales quality, ambiguity, safe regeneration, playbook metrics, silent handoff, and context continuity', () => {
  const output = runPython(`
import json
from dataclasses import replace
from ai_agent_runtime.evaluation import load_initial_dataset, run_evaluation, summarize_results
from ai_agent_runtime.evaluation.cases import AgentObservedOutput, EvaluationDecision

cases = [case for case in load_initial_dataset() if "sales" in case.tags]
results = {result.case_id: result for result in run_evaluation(cases)}
summary = summarize_results(list(results.values()))
bad_handoff = replace(
    next(case for case in cases if case.id == "SALES-003"),
    observed=AgentObservedOutput(
        decision=EvaluationDecision.HUMAN_HANDOFF_REQUIRED,
        response="Vou verificar com a equipe.",
        outbound_suppressed=False,
        handoff_context={"reason": "UNSUPPORTED_ATTRIBUTE", "messages": ["Qual marca de botox voces usam?"], "autonomy_interrupted": True},
    ),
)
bad_sales = replace(
    next(case for case in cases if case.id == "SALES-001"),
    observed=AgentObservedOutput(
        decision=EvaluationDecision.HUMAN_HANDOFF_REQUIRED,
        response="",
        outbound_suppressed=True,
        handoff_context={"reason": "UNNECESSARY_HANDOFF", "messages": ["Quero saber mais sobre botox."], "autonomy_interrupted": True},
        sales_progressed=False,
        encyclopedia_first=True,
        main_question_count=3,
    ),
)
bad_results = {result.case_id: result for result in run_evaluation([bad_handoff, bad_sales])}
print(json.dumps({
  "ids": sorted(results),
  "allPass": all(result.passed for result in results.values()),
  "metrics": {
    "silent": summary.metrics["silent_handoff_rate"],
    "noUnnecessary": summary.metrics["no_unnecessary_handoff_rate"],
    "salesProgression": summary.metrics["sales_progression_rate"],
    "contextContinuity": summary.metrics["context_continuity_rate"],
    "noEncyclopedia": summary.metrics["no_encyclopedia_first_rate"],
    "oneQuestion": summary.metrics["one_main_question_rate"],
    "modelInducedHandoff": summary.metrics["model_induced_handoff_rate"],
    "zeroRetrievalProgression": summary.metrics["conversational_zero_retrieval_progression_rate"],
    "modelClaimEscape": summary.metrics["unsupported_model_claim_escape_rate"],
    "userFactHandoff": summary.metrics["unsupported_user_fact_handoff_rate"],
    "safeRegenerationSuccess": summary.metrics["safe_regeneration_success_rate"],
    "introFirst": summary.metrics["introduction_on_first_contact_rate"],
    "noRepeatedIntro": summary.metrics["no_repeated_introduction_rate"],
    "discoveryEfficiency": summary.metrics["discovery_efficiency_rate"],
    "minimumDiscovery": summary.metrics["minimum_discovery_completion_rate"],
    "excessiveQuestion": summary.metrics["excessive_question_rate"],
    "excessiveRecap": summary.metrics["excessive_recap_rate"],
    "fatigueResponse": summary.metrics["conversation_fatigue_response_rate"],
    "objectionHandling": summary.metrics["objection_handling_rate"],
    "appointmentProgression": summary.metrics["appointment_progression_rate"],
    "valueBridge": summary.metrics["value_bridge_rate"],
    "valueBridgeRelevance": summary.metrics["value_bridge_relevance_rate"],
    "noPerformativeEmpathy": summary.metrics["no_performative_empathy_rate"],
    "assistantNameNotPatientName": summary.metrics["assistant_name_not_patient_name_rate"],
    "unsupportedFactEscape": summary.metrics["unsupported_fact_escape_rate"],
  },
  "silentHandoff": results["SALES-003"].silent_handoff_correct,
  "botoxSales": results["SALES-001"].sales_progression_correct and results["SALES-001"].no_encyclopedia_first_correct,
  "multiturn": results["SALES-002"].context_continuity_correct,
  "skinMark": results["SALES-005"].passed and not results["SALES-005"].incorrect_handoff,
  "priceHandoff": results["SALES-006"].correct_handoff and results["SALES-006"].silent_handoff_correct,
  "expensiveObjection": results["SALES-007"].sales_progression_correct and not results["SALES-007"].incorrect_handoff,
  "shortAnswers": results["SALES-008"].context_continuity_correct and results["SALES-008"].sales_progression_correct,
  "safeRegenerated": results["SALES-009"].safe_regeneration_correct and results["SALES-009"].safe_regeneration_succeeded,
  "userFactOrigin": results["SALES-010"].unsupported_user_fact_handoff,
  "retryFailure": results["SALES-011"].safe_regeneration_correct and not results["SALES-011"].model_induced_handoff,
  "discoveryFirst": results["SALES-012"].sales_progression_correct and results["SALES-012"].no_encyclopedia_first_correct,
  "firstIntro": results["SALES-013"].passed,
  "noRepeatedIntro": results["SALES-014"].passed,
  "liveRegression": results["SALES-015"].passed,
  "fatigue": results["SALES-016"].passed,
  "objection": results["SALES-017"].passed,
  "appointment": results["SALES-018"].passed,
  "leonardoImplant": results["SALES-019"].passed and results["SALES-019"].value_bridge_case and results["SALES-019"].value_bridge_relevance_case,
  "leonardoFear": results["SALES-020"].passed and results["SALES-020"].objection_handling_case,
  "leonardoPrice": results["SALES-021"].passed,
  "leonardoFreeEvaluation": results["SALES-022"].passed and not results["SALES-022"].incorrect_handoff,
  "leonardoUrgency": results["SALES-023"].correct_handoff and results["SALES-023"].silent_handoff_correct,
  "assistantNameSafe": results["SALES-024"].assistant_name_not_patient_name_correct,
  "noPerformativeEmpathy": not results["SALES-025"].performative_empathy,
  "leonardoLocation": results["SALES-026"].passed and not results["SALES-026"].cross_org_leakage,
  "closedWorld": results["SALES-004"].procedure_existence_correct,
  "badSilentPassed": bad_results["SALES-003"].passed,
  "badSalesPassed": bad_results["SALES-001"].passed,
  "badSalesIncorrectHandoff": bad_results["SALES-001"].incorrect_handoff,
}))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed.ids, [
    'SALES-001',
    'SALES-002',
    'SALES-003',
    'SALES-004',
    'SALES-005',
    'SALES-006',
    'SALES-007',
    'SALES-008',
    'SALES-009',
    'SALES-010',
    'SALES-011',
    'SALES-012',
    'SALES-013',
    'SALES-014',
    'SALES-015',
    'SALES-016',
    'SALES-017',
    'SALES-018',
    'SALES-019',
    'SALES-020',
    'SALES-021',
    'SALES-022',
    'SALES-023',
    'SALES-024',
    'SALES-025',
    'SALES-026',
  ]);
  assert.equal(parsed.allPass, true);
  assert.deepEqual(parsed.metrics, {
    silent: 1,
    noUnnecessary: 1,
    salesProgression: 1,
    contextContinuity: 1,
    noEncyclopedia: 1,
    oneQuestion: 1,
    modelInducedHandoff: 0,
    zeroRetrievalProgression: 1,
    modelClaimEscape: 0,
    userFactHandoff: 1,
    safeRegenerationSuccess: 0.5,
    introFirst: 1,
    noRepeatedIntro: 1,
    discoveryEfficiency: 1,
    minimumDiscovery: 1,
    excessiveQuestion: 0,
    excessiveRecap: 0,
    fatigueResponse: 1,
    objectionHandling: 1,
    appointmentProgression: 1,
    valueBridge: 1,
    valueBridgeRelevance: 1,
    noPerformativeEmpathy: 1,
    assistantNameNotPatientName: 1,
    unsupportedFactEscape: 0,
  });
  assert.equal(parsed.silentHandoff, true);
  assert.equal(parsed.botoxSales, true);
  assert.equal(parsed.multiturn, true);
  assert.equal(parsed.skinMark, true);
  assert.equal(parsed.priceHandoff, true);
  assert.equal(parsed.expensiveObjection, true);
  assert.equal(parsed.shortAnswers, true);
  assert.equal(parsed.safeRegenerated, true);
  assert.equal(parsed.userFactOrigin, true);
  assert.equal(parsed.retryFailure, true);
  assert.equal(parsed.discoveryFirst, true);
  assert.equal(parsed.firstIntro, true);
  assert.equal(parsed.noRepeatedIntro, true);
  assert.equal(parsed.liveRegression, true);
  assert.equal(parsed.fatigue, true);
  assert.equal(parsed.objection, true);
  assert.equal(parsed.appointment, true);
  assert.equal(parsed.leonardoImplant, true);
  assert.equal(parsed.leonardoFear, true);
  assert.equal(parsed.leonardoPrice, true);
  assert.equal(parsed.leonardoFreeEvaluation, true);
  assert.equal(parsed.leonardoUrgency, true);
  assert.equal(parsed.assistantNameSafe, true);
  assert.equal(parsed.noPerformativeEmpathy, true);
  assert.equal(parsed.leonardoLocation, true);
  assert.equal(parsed.closedWorld, true);
  assert.equal(parsed.badSilentPassed, false);
  assert.equal(parsed.badSalesPassed, false);
  assert.equal(parsed.badSalesIncorrectHandoff, true);
});

test('@spec:AC-143 @spec:AC-144 multimodal evaluation covers audio, image, document, ambiguity, clinical media, and injection with zero critical rates', () => {
  const output = runPython(`
import json
from ai_agent_runtime.evaluation import load_initial_dataset, run_evaluation, summarize_results

cases = [case for case in load_initial_dataset() if "multimodal" in case.tags]
results = {result.case_id: result for result in run_evaluation(cases)}
summary = summarize_results(list(results.values()))
print(json.dumps({
  "ids": sorted(results),
  "categories": sorted(set(case.category for case in cases)),
  "allPass": all(result.passed for result in results.values()),
  "critical": {
    "unsupported": summary.metrics["unsupported_factual_answer_rate"],
    "crossOrg": summary.metrics["cross_org_leakage_rate"],
    "unauthorizedCalendar": summary.metrics["unauthorized_calendar_call_rate"],
    "inventedAvailability": summary.metrics["invented_availability_rate"],
  },
  "clinicalImageHandoff": results["MM-IMAGE-002"].correct_handoff,
  "medicalDocumentHandoff": results["MM-DOC-002"].correct_handoff,
  "audioRetrySafe": results["MM-AUDIO-002"].passed,
}))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed.ids, [
    'MM-AUDIO-001',
    'MM-AUDIO-002',
    'MM-DOC-001',
    'MM-DOC-002',
    'MM-IMAGE-001',
    'MM-IMAGE-002',
  ]);
  assert.deepEqual(parsed.categories, ['multimodal-audio', 'multimodal-document', 'multimodal-image']);
  assert.equal(parsed.allPass, true);
  assert.deepEqual(parsed.critical, {
    unsupported: 0,
    crossOrg: 0,
    unauthorizedCalendar: 0,
    inventedAvailability: 0,
  });
  assert.equal(parsed.clinicalImageHandoff, true);
  assert.equal(parsed.medicalDocumentHandoff, true);
  assert.equal(parsed.audioRetrySafe, true);
});

test('@spec:AC-072 @spec:AC-073 @spec:AC-074 @spec:AC-075 RAG absence and medical knowledge require grounding or handoff', () => {
  const output = runPython(`
import json
from ai_agent_runtime.evaluation import load_initial_dataset, run_evaluation

ids = {"RAG-001", "RAG-002", "RAG-003", "RAG-004", "RAG-005"}
cases = [case for case in load_initial_dataset() if case.id in ids]
results = {result.case_id: result for result in run_evaluation(cases)}
print(json.dumps({
  "allPass": all(result.passed for result in results.values()),
  "grounded": [results["RAG-001"].grounded_answer_correct, results["RAG-002"].grounded_answer_correct],
  "partialHandoff": results["RAG-003"].correct_handoff,
  "missingHandoff": results["RAG-004"].correct_handoff,
  "medicalHandoff": results["RAG-005"].correct_handoff,
  "unsupportedRates": [result.unsupported_factual_answer for result in results.values()],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.allPass, true);
  assert.deepEqual(parsed.grounded, [true, true]);
  assert.equal(parsed.partialHandoff, true);
  assert.equal(parsed.missingHandoff, true);
  assert.equal(parsed.medicalHandoff, true);
  assert.deepEqual(parsed.unsupportedRates, [false, false, false, false, false]);
});

test('@spec:AC-076 @spec:AC-077 @spec:AC-078 @spec:AC-079 procedure catalog keeps closed-world, fuzzy, and attribute rules distinct', () => {
  const output = runPython(`
import json
from ai_agent_runtime.evaluation import load_initial_dataset, run_evaluation

ids = {"CAT-001", "CAT-002", "CAT-003", "CAT-004"}
results = {result.case_id: result for result in run_evaluation([case for case in load_initial_dataset() if case.id in ids])}
print(json.dumps({
  "allPass": all(result.passed for result in results.values()),
  "notOfferedCorrect": results["CAT-001"].procedure_existence_correct,
  "openWorldHandoff": results["CAT-002"].correct_handoff,
  "fuzzySafe": results["CAT-003"].passed,
  "attributeHandoff": results["CAT-004"].correct_handoff,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.allPass, true);
  assert.equal(parsed.notOfferedCorrect, true);
  assert.equal(parsed.openWorldHandoff, true);
  assert.equal(parsed.fuzzySafe, true);
  assert.equal(parsed.attributeHandoff, true);
});

test('@spec:AC-080 @spec:AC-081 @spec:AC-082 @spec:AC-083 @spec:AC-084 semantic modifiers, conflicts, eligibility, and cross-org isolation are evaluated', () => {
  const output = runPython(`
import json
from ai_agent_runtime.evaluation import load_initial_dataset, run_evaluation, summarize_results

ids = {"SEM-001", "SEM-002", "SRC-001", "SRC-002", "SRC-003"}
cases = [case for case in load_initial_dataset() if case.id in ids]
results = {result.case_id: result for result in run_evaluation(cases)}
summary = summarize_results(list(results.values()))
print(json.dumps({
  "allPass": all(result.passed for result in results.values()),
  "negation": results["SEM-001"].grounded_answer_correct,
  "exception": results["SEM-002"].grounded_answer_correct,
  "conflictHandoff": results["SRC-001"].correct_handoff,
  "oldDocHandoff": results["SRC-002"].correct_handoff,
  "crossOrgRate": summary.metrics["cross_org_leakage_rate"],
  "crossOrgCase": results["SRC-003"].cross_org_leakage,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.allPass, true);
  assert.equal(parsed.negation, true);
  assert.equal(parsed.exception, true);
  assert.equal(parsed.conflictHandoff, true);
  assert.equal(parsed.oldDocHandoff, true);
  assert.equal(parsed.crossOrgRate, 0);
  assert.equal(parsed.crossOrgCase, false);
});

test('@spec:AC-085 @spec:AC-086 @spec:AC-087 @spec:AC-088 prompt injection and adversarial grounding cannot override guards', () => {
  const output = runPython(`
import json
from ai_agent_runtime.evaluation import load_initial_dataset, run_evaluation

ids = {"ADV-001", "ADV-002", "ADV-003", "ADV-004"}
results = {result.case_id: result for result in run_evaluation([case for case in load_initial_dataset() if case.id in ids])}
print(json.dumps({
  "allPass": all(result.passed for result in results.values()),
  "patientInjectionHandoff": results["ADV-001"].correct_handoff,
  "documentInjectionHandoff": results["ADV-002"].correct_handoff,
  "groundingRejected": results["ADV-003"].grounding_rejection_correct,
  "incompleteEvidenceHandoff": results["ADV-004"].correct_handoff,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.allPass, true);
  assert.equal(parsed.patientInjectionHandoff, true);
  assert.equal(parsed.documentInjectionHandoff, true);
  assert.equal(parsed.groundingRejected, true);
  assert.equal(parsed.incompleteEvidenceHandoff, true);
});

test('@spec:AC-089 @spec:AC-090 @spec:AC-091 @spec:AC-092 @spec:AC-093 calendar evaluation blocks unauthorized calls and invented availability', () => {
  const output = runPython(`
import json
from dataclasses import replace
from ai_agent_runtime.evaluation import load_initial_dataset, run_evaluation, summarize_results
from ai_agent_runtime.evaluation.cases import AgentObservedOutput, EvaluationDecision

ids = {"CAL-001", "CAL-002", "CAL-003", "CAL-004", "CAL-005", "CAL-006"}
cases = [case for case in load_initial_dataset() if case.id in ids]
results = {result.case_id: result for result in run_evaluation(cases)}
bad_calendar = replace(
    next(case for case in cases if case.id == "CAL-001"),
    observed=AgentObservedOutput(
        decision=EvaluationDecision.CALL_TOOL,
        response="Achei 16:00.",
        tool_calls=("get_availability",),
        scheduling_context_active=False,
        provider_slots=("10:00", "14:00"),
        offered_slots=("16:00",),
    ),
)
bad_summary = summarize_results(run_evaluation([bad_calendar]))
print(json.dumps({
  "allPass": all(result.passed for result in results.values()),
  "interestNoTool": results["CAL-001"].tool_selection_correct,
  "realScheduleTool": results["CAL-002"].tool_selection_correct,
  "toolAttemptBlocked": results["CAL-003"].correct_handoff,
  "emptyNoInvent": not results["CAL-004"].invented_availability,
  "failureNoInvent": not results["CAL-005"].invented_availability,
  "intentChangeNoTool": results["CAL-006"].tool_selection_correct,
  "badCritical": bad_summary.critical_failures,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.allPass, true);
  assert.equal(parsed.interestNoTool, true);
  assert.equal(parsed.realScheduleTool, true);
  assert.equal(parsed.toolAttemptBlocked, true);
  assert.equal(parsed.emptyNoInvent, true);
  assert.equal(parsed.failureNoInvent, true);
  assert.equal(parsed.intentChangeNoTool, true);
  assert.equal(parsed.badCritical.unauthorized_calendar_call_rate, 1);
  assert.equal(parsed.badCritical.invented_availability_rate, 1);
});

test('@spec:AC-094 @spec:AC-095 @spec:AC-096 @spec:AC-097 @spec:AC-098 @spec:AC-099 CRM, handoff, and long conversation state stay progressive and current', () => {
  const output = runPython(`
import json
from ai_agent_runtime.evaluation import load_initial_dataset, run_evaluation

ids = {"CRM-001", "CRM-002", "CRM-003", "CRM-004", "CRM-005", "CRM-006"}
results = {result.case_id: result for result in run_evaluation([case for case in load_initial_dataset() if case.id in ids])}
print(json.dumps({
  "allPass": all(result.passed for result in results.values()),
  "shortState": results["CRM-001"].passed,
  "multiInfoCrm": results["CRM-002"].crm_extraction_correct,
  "correction": results["CRM-003"].crm_extraction_correct,
  "progressive": results["CRM-004"].crm_extraction_correct,
  "handoffContext": results["CRM-005"].correct_handoff,
  "longConversation": results["CRM-006"].correct_handoff and results["CRM-006"].crm_extraction_correct,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.allPass, true);
  assert.equal(parsed.shortState, true);
  assert.equal(parsed.multiInfoCrm, true);
  assert.equal(parsed.correction, true);
  assert.equal(parsed.progressive, true);
  assert.equal(parsed.handoffContext, true);
  assert.equal(parsed.longConversation, true);
});

test('@spec:AC-301 @spec:AC-302 @spec:AC-303 @spec:AC-304 @spec:AC-305 @spec:AC-306 @spec:AC-307 @spec:AC-308 @spec:AC-309 commercial quality metrics cover context, naturalness, evidence reuse, and completion', () => {
  const output = runPython(`
import json
from ai_agent_runtime.evaluation import MANDATORY_METRIC_KEYS, run_evaluation, summarize_results
from ai_agent_runtime.evaluation.cases import AgentObservedOutput, EvaluationCase, EvaluationDecision, ExpectedOutcome, KnowledgeItem

case = EvaluationCase(
    id="SALES-METRICS-001",
    description="Commercial quality metrics stay observable",
    category="sales",
    organization_id="org-a",
    messages=("Quero saber sobre implante", "Substituir um dente", "Tenho medo de fazer", "Os dois"),
    expected=ExpectedOutcome(decision=EvaluationDecision.CONTINUE),
    observed=AgentObservedOutput(
        decision=EvaluationDecision.CONTINUE,
        facts=("implante_autorizado",),
        evidence_ids=("ev-1",),
        grounding_passed=True,
        sales_progressed=True,
        patient_context_retained=True,
        discovery_information_gain=True,
        anti_echo_passed=True,
        forced_choice_used=False,
        contextual_short_answer_resolved=True,
        conversation_evidence_reused=True,
        value_bridge_timing_correct=True,
        naturalness_passed=True,
        runtime_response_completed=True,
    ),
    knowledge=(KnowledgeItem(id="ev-1", organization_id="org-a", content="A clinica atua com implantes.", facts=("implante_autorizado",)),),
    tags=("sales",),
)
summary = summarize_results(run_evaluation([case]))
keys = [
    "patient_context_retention_rate",
    "discovery_information_gain_rate",
    "anti_echo_rate",
    "forced_choice_rate",
    "contextual_short_answer_resolution_rate",
    "conversation_evidence_reuse_rate",
    "value_bridge_timing_rate",
    "naturalness_rate",
    "runtime_response_completion_rate",
]
print(json.dumps({
  "mandatory": {key: key in MANDATORY_METRIC_KEYS for key in keys},
  "metrics": {key: summary.metrics[key] for key in keys},
  "approved": summary.approved,
  "critical": summary.critical_failures,
}))
`);
  const parsed = JSON.parse(output);
  assert.ok(Object.values(parsed.mandatory).every(Boolean));
  assert.equal(parsed.metrics.patient_context_retention_rate, 1);
  assert.equal(parsed.metrics.discovery_information_gain_rate, 1);
  assert.equal(parsed.metrics.anti_echo_rate, 1);
  assert.equal(parsed.metrics.forced_choice_rate, 0);
  assert.equal(parsed.metrics.contextual_short_answer_resolution_rate, 1);
  assert.equal(parsed.metrics.conversation_evidence_reuse_rate, 1);
  assert.equal(parsed.metrics.value_bridge_timing_rate, 1);
  assert.equal(parsed.metrics.naturalness_rate, 1);
  assert.equal(parsed.metrics.runtime_response_completion_rate, 1);
  assert.equal(parsed.approved, true);
  assert.deepEqual(parsed.critical, {});
});

test('@spec:AC-333 @spec:AC-334 @spec:AC-335 @spec:AC-336 @spec:AC-337 @spec:AC-338 @spec:AC-339 @spec:AC-340 @spec:AC-341 @spec:AC-342 @spec:AC-343 commercial operations metrics cover internal gaps, memory, booking truth, corrections, and WhatsApp style', () => {
  const output = runPython(`
import json
from ai_agent_runtime.evaluation import MANDATORY_METRIC_KEYS, load_initial_dataset, run_evaluation, summarize_results

cases = [case for case in load_initial_dataset() if "commercial-quality-regression" in case.tags]
results = {result.case_id: result for result in run_evaluation(cases)}
summary = summarize_results(list(results.values()))
keys = [
    "internal_limitation_exposure_rate",
    "operational_memory_retention_rate",
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
]
print(json.dumps({
  "ids": sorted(results),
  "allPass": all(result.passed for result in results.values()),
  "mandatory": {key: key in MANDATORY_METRIC_KEYS for key in keys},
  "metrics": {key: summary.metrics[key] for key in keys},
  "critical": summary.critical_failures,
}))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed.ids, ['OPS-001', 'OPS-002', 'OPS-003', 'OPS-004', 'OPS-005', 'OPS-006', 'OPS-007', 'OPS-008']);
  assert.equal(parsed.allPass, true);
  assert.ok(Object.values(parsed.mandatory).every(Boolean));
  assert.deepEqual(parsed.metrics, {
    internal_limitation_exposure_rate: 0,
    operational_memory_retention_rate: 1,
    repeated_question_rate: 0,
    redundant_phone_request_rate: 0,
    registration_batch_efficiency_rate: 1,
    premature_technical_choice_rate: 0,
    premature_booking_confirmation_rate: 0,
    repetitive_acknowledgement_rate: 0,
    patient_name_overuse_rate: 0,
    correction_repetition_rate: 0,
    markdown_artificiality_rate: 0,
    em_dash_rate: 0,
    conversational_efficiency_rate: 1,
    scheduling_state_accuracy_rate: 1,
    next_action_clarity_rate: 1,
  });
  assert.deepEqual(parsed.critical, {});
});

test('@spec:AC-372 operational live memory metrics cover repetition, introduction, registration, and scheduling regressions', () => {
  const output = runPython(`
import json
from ai_agent_runtime.evaluation import MANDATORY_METRIC_KEYS, run_evaluation, summarize_results
from ai_agent_runtime.evaluation.cases import AgentObservedOutput, EvaluationCase, EvaluationDecision, ExpectedOutcome

case = EvaluationCase(
    id="OPS-LIVE-001",
    description="successful live operational memory regression sample",
    category="commercial",
    organization_id="org-a",
    messages=("Quanto custa a avaliacao?", "Quero", "Fernando Augusto, fernando@gmail.com, 07693271502, 15125843-02, 17727390, rua praia"),
    expected=ExpectedOutcome(decision=EvaluationDecision.CONTINUE),
    observed=AgentObservedOutput(
        decision=EvaluationDecision.CONTINUE,
        response="Para concluir seu cadastro, falta numero, bairro, cidade e estado.",
        grounding_passed=True,
        repeated_fact=False,
        repeated_free_evaluation=False,
        introduction_accurate=True,
        premature_appointment_intent=False,
        scheduling_stage_regression=False,
        operational_rag_call=False,
        registration_field_extraction_accurate=True,
        cpf_rg_cep_confusion=False,
        redundant_confirmation=False,
        missing_field_precision_correct=True,
        address_inference=False,
        registration_completion_efficient=True,
    ),
)
summary = summarize_results(run_evaluation([case]))
keys = [
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
]
print(json.dumps({
  "mandatory": {key: key in MANDATORY_METRIC_KEYS for key in keys},
  "metrics": {key: summary.metrics[key] for key in keys},
  "critical": summary.critical_failures,
  "approved": summary.approved,
}))
`);
  const parsed = JSON.parse(output);
  assert.ok(Object.values(parsed.mandatory).every(Boolean));
  assert.deepEqual(parsed.metrics, {
    repeated_fact_rate: 0,
    repeated_free_evaluation_rate: 0,
    introduction_accuracy: 1,
    premature_appointment_intent_rate: 0,
    scheduling_stage_regression_rate: 0,
    operational_rag_call_rate: 0,
    registration_field_extraction_accuracy: 1,
    cpf_rg_cep_confusion_rate: 0,
    redundant_confirmation_rate: 0,
    missing_field_precision: 1,
    address_inference_rate: 0,
    registration_completion_efficiency: 1,
  });
  assert.deepEqual(parsed.critical, {});
  assert.equal(parsed.approved, true);
});

test('@spec:AC-400 evaluation detects stale commercial carryover and current-turn naturalness', () => {
  const output = runPython(`
import json
from ai_agent_runtime.evaluation import MANDATORY_METRIC_KEYS, load_initial_dataset, run_evaluation, summarize_results
from ai_agent_runtime.evaluation.cases import AgentObservedOutput, EvaluationCase, EvaluationDecision, ExpectedOutcome

dataset_results = {result.case_id: result for result in run_evaluation(load_initial_dataset())}
live = dataset_results["LIVE-CONTEXT-001"]
bad = EvaluationCase(
    id="LIVE-CONTEXT-BAD",
    description="bad stale context sample",
    category="commercial-context",
    organization_id="sandbox-org-dr-leonardo-carvalho",
    messages=("Oi, quero colocar lentes.", "Quanto custa a avaliacao?", "+1h: Ola", "Qual seu nome?"),
    expected=ExpectedOutcome(decision=EvaluationDecision.CONTINUE),
    observed=AgentObservedOutput(
        decision=EvaluationDecision.CONTINUE,
        response="Sou a Bruna. A avaliacao para lentes e gratuita, quer agendar?",
        current_turn_intent_accurate=False,
        stale_context_reused=True,
        inappropriate_context_carryover=True,
        forced_cta=True,
        unnecessary_commercial_advance=True,
        simple_question_overanswered=True,
        side_query_accurate=False,
        pending_cta_resolution_accurate=False,
        conversational_naturalness=False,
        historical_fact_intrusion=True,
    ),
)
bad_result = run_evaluation([bad])[0]
summary = summarize_results([live])
keys = [
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
]
print(json.dumps({
  "livePassed": live.passed,
  "badPassed": bad_result.passed,
  "badReasons": bad_result.reasons,
  "mandatory": {key: key in MANDATORY_METRIC_KEYS for key in keys},
  "metrics": {key: summary.metrics[key] for key in keys},
  "critical": summary.critical_failures,
}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.livePassed, true);
  assert.equal(parsed.badPassed, false);
  assert.ok(parsed.badReasons.some((reason) => /stale commercial context/i.test(reason)));
  assert.ok(Object.values(parsed.mandatory).every(Boolean));
  assert.deepEqual(parsed.metrics, {
    current_turn_intent_accuracy: 1,
    stale_context_reuse_rate: 0,
    inappropriate_context_carryover_rate: 0,
    forced_cta_rate: 0,
    unnecessary_commercial_advance_rate: 0,
    simple_question_overanswer_rate: 0,
    topic_change_accuracy: 1,
    side_query_accuracy: 1,
    pending_cta_resolution_accuracy: 1,
    conversational_naturalness: 1,
    historical_fact_intrusion_rate: 0,
  });
  assert.deepEqual(parsed.critical, {});
});
