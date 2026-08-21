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

test('@spec:AC-033 @spec:AC-034 @spec:AC-047 @spec:AC-048 runtime state and graph handle handoff without WhatsApp', () => {
  const output = runPython(`
import json
from ai_agent_runtime import AgentDecision, AgentRuntimeGraph, AgentState

state = AgentState(conversation_id="conv-1", organization_id="org-1", current_message="Preciso falar com atendente")
graph = AgentRuntimeGraph()
result = graph.run(state, inherited_decision=AgentDecision.HUMAN_HANDOFF_REQUIRED)
print(json.dumps({
  "snapshot": result.snapshot(),
  "nodes": graph.topology(),
  "langgraph": graph.langgraph_available,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.snapshot.conversationId, 'conv-1');
  assert.equal(parsed.snapshot.organizationId, 'org-1');
  assert.equal(parsed.snapshot.decision, 'HUMAN_HANDOFF_REQUIRED');
  assert.equal(parsed.snapshot.stage, 'HANDOFF');
  assert.equal(parsed.snapshot.handoffContext.reason, 'HUMAN_HANDOFF_REQUIRED');
  assert.deepEqual(parsed.nodes, ['interpret_message', 'decide_route', 'execute_tool', 'grounding', 'handoff']);
  assert.equal(typeof parsed.langgraph, 'boolean');
});

test('@spec:AC-035 @spec:AC-036 @spec:AC-037 @spec:AC-038 @spec:AC-039 scheduling guard blocks general interest and uses CalendarProvider only when active', () => {
  const output = runPython(`
import json
from ai_agent_runtime.state import AgentState
from ai_agent_runtime.scheduling import CalendarTools, SchedulingGuardError, can_get_availability, update_scheduling_context
from ai_agent_runtime.providers import CalendarProvider

class FakeCalendar(CalendarProvider):
    def __init__(self):
        self.calls = []
    def get_availability(self, *, organization_id, criteria):
        self.calls.append(("get_availability", organization_id, criteria))
        return [{"start": "2026-08-21T10:00:00-03:00"}]
    def create_appointment(self, *, organization_id, payload):
        return {"id": "appt-1", **payload}
    def reschedule_appointment(self, *, organization_id, appointment_id, payload):
        return {"id": appointment_id, **payload}
    def cancel_appointment(self, *, organization_id, appointment_id, reason=None):
        return {"id": appointment_id, "cancelled": True, "reason": reason}

general = update_scheduling_context(AgentState("conv-1", "org-1", "Quanto custa a consulta?"))
active = update_scheduling_context(AgentState("conv-2", "org-1", "Tem horario sexta?"))
provider = FakeCalendar()
tools = CalendarTools(provider)
blocked = False
try:
    tools.consultar_agenda(general, {})
except SchedulingGuardError:
    blocked = True
availability = tools.consultar_agenda(active, {"date": "sexta"})
print(json.dumps({
  "generalActive": general.scheduling_context_active,
  "activeScheduling": active.scheduling_context_active,
  "canGeneral": can_get_availability(general),
  "canActive": can_get_availability(active),
  "blocked": blocked,
  "availability": availability,
  "calls": provider.calls,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.generalActive, false);
  assert.equal(parsed.canGeneral, false);
  assert.equal(parsed.activeScheduling, true);
  assert.equal(parsed.canActive, true);
  assert.equal(parsed.blocked, true);
  assert.equal(parsed.availability[0].start, '2026-08-21T10:00:00-03:00');
  assert.equal(parsed.calls.length, 1);
});

test('@spec:AC-040 @spec:AC-041 CRM provider updates only trusted progressive fields', () => {
  const output = runPython(`
import json
from ai_agent_runtime.crm import CRMTools, TrustedField, build_crm_field_update
from ai_agent_runtime.providers import CRMProvider

class FakeCRM(CRMProvider):
    def __init__(self):
        self.fields = None
    def upsert_contact(self, *, organization_id, contact):
        return {"organization_id": organization_id, "contact": contact}
    def update_stage(self, *, organization_id, contact_id, stage):
        return {"stage": stage}
    def update_fields(self, *, organization_id, contact_id, fields):
        self.fields = fields
        return fields
    def add_note(self, *, organization_id, contact_id, note):
        return {"note": note}

update = build_crm_field_update({
  "name": TrustedField("Ana", "patient_message"),
  "phone": None,
  "procedure_interest": TrustedField("Botox", "patient_message"),
  "made_up_field": TrustedField("x", "llm_guess"),
  "unit": TrustedField("", "missing"),
})
crm = FakeCRM()
tools = CRMTools(crm)
result = tools.update_progressive_fields(organization_id="org-1", contact_id="contact-1", fields={
  "name": TrustedField("Ana", "patient_message"),
  "phone": None,
})
print(json.dumps({"update": update, "result": result}))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed.update, { name: 'Ana', procedure_interest: 'Botox' });
  assert.deepEqual(parsed.result, { name: 'Ana' });
});

test('@spec:AC-042 @spec:AC-043 @spec:AC-044 hybrid retrieval isolates organization and grounding gates high scores', () => {
  const output = runPython(`
import json
from ai_agent_runtime.grounding import GroundingResult, decide_after_grounding
from ai_agent_runtime.providers import RetrievalProvider, RetrievalResult
from ai_agent_runtime.retrieval import HybridRetrievalService, RetrievalIsolationError

class FakeRetrieval(RetrievalProvider):
    def lexical_search(self, *, organization_id, query):
        return [RetrievalResult("lex-1", organization_id, "v1", "texto lexical", 0.9, "lexical")]
    def vector_search(self, *, organization_id, query):
        return [RetrievalResult("vec-1", organization_id, "v2", "texto vetorial", 0.99, "vector")]

service = HybridRetrievalService(FakeRetrieval())
missing_org_blocked = False
try:
    service.search(organization_id="", query="preco")
except RetrievalIsolationError:
    missing_org_blocked = True
results = service.search(organization_id="org-1", query="preco")
decision_fail = decide_after_grounding(GroundingResult(False, "UNSUPPORTED", ["v2"])).value
decision_pass = decide_after_grounding(GroundingResult(True, None, ["v2"])).value
print(json.dumps({
  "missingOrgBlocked": missing_org_blocked,
  "sources": [r.source for r in results],
  "scores": [r.score for r in results],
  "decisionFail": decision_fail,
  "decisionPass": decision_pass,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.missingOrgBlocked, true);
  assert.deepEqual(parsed.sources, ['vector', 'lexical']);
  assert.deepEqual(parsed.scores, [0.99, 0.9]);
  assert.equal(parsed.decisionFail, 'HUMAN_HANDOFF_REQUIRED');
  assert.equal(parsed.decisionPass, 'ANSWER_GROUNDED');
});

test('@spec:AC-045 @spec:AC-046 operational audit survives optional observer failures', () => {
  const output = runPython(`
import json
from ai_agent_runtime.observability import AuditEvent, AuditStore, RuntimeObservability

class BrokenObserver:
    def trace(self, event):
        raise RuntimeError("no credentials")

store = AuditStore()
runtime = RuntimeObservability(store, BrokenObserver())
event = runtime.record_event(AuditEvent(
    conversation_id="conv-1",
    organization_id="org-1",
    intent="SCHEDULING_REQUEST",
    decision="CALL_TOOL",
    tool_called="consultar_agenda",
    grounding_result="PASS",
    handoff_reason=None,
))
print(json.dumps({
  "stored": len(store.events),
  "conversationId": event.conversation_id,
  "organizationId": event.organization_id,
  "toolCalled": event.tool_called,
  "hasTimestamp": bool(event.timestamp),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.stored, 1);
  assert.equal(parsed.conversationId, 'conv-1');
  assert.equal(parsed.organizationId, 'org-1');
  assert.equal(parsed.toolCalled, 'consultar_agenda');
  assert.equal(parsed.hasTimestamp, true);
});
