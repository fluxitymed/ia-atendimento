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
  "allFictitious": all(case.fictitious_data for case in cases),
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
  assert.equal(parsed.count, 30);
  assert.equal(parsed.allPass, true);
  assert.equal(parsed.allVersioned, true);
  assert.equal(parsed.allFictitious, true);
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
    cases[13],
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
  "reportHasTotal": "Total scenarios: 30" in report,
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
