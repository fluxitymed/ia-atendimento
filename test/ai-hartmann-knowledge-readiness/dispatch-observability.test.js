'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

function runPython(source) {
  const result = spawnSync('python3', ['-c', source], {
    cwd: process.cwd(), env: { ...process.env, PYTHONPATH: 'src' }, encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return JSON.parse(result.stdout);
}

const fixture = String.raw`
import io
import json
import logging
from ai_agent_runtime.crm_dispatch import CrmDispatchProcessor, handle_crm_dispatch, _safe_crm_log
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.organization_config import InMemoryOrganizationConfigRepository, OrganizationRuntimeConfig
from ai_agent_runtime.state import AgentDecision, AgentStage

ORG = '38002ccb-9edb-4dcb-aacf-76c0b6ca1692'
CORRELATION = '142f8614-97c4-4f85-a202-df0cb51b39d0'
VERSION = '178d4876-0428-4286-87c5-8711e090a767'
CHUNK = 'f69e2b48-e389-586b-b84f-9ebe80ef6756'
DOCUMENT = '99999999-9999-4999-8999-999999999999'
TOKEN = 'local-test-service-token-000000000000'
SECRET = 'patient-and-token-must-not-appear'
event = {
    'version': '1', 'correlationId': CORRELATION, 'organizationId': ORG,
    'conversationId': 'a341db43-d53d-4f19-b4d3-3c1a7c6f5409',
    'providerConnectionId': '44444444-4444-4444-8444-444444444444',
    'contactId': None, 'inboundMessageId': '55555555-5555-4555-8555-555555555555',
    'mode': 'AI', 'modeVersion': 1,
    'message': {'type': 'text', 'text': SECRET, 'timestamp': '2026-10-08T00:46:49Z'},
}
repo = InMemoryOrganizationConfigRepository([OrganizationRuntimeConfig(organization_id=ORG)])
def invoke(graph, question=None):
    logs = []
    worker = CrmDispatchProcessor(config_repository=repo, graph_factory=lambda _: graph,
                                  logger=lambda name, fields: logs.append((name, fields)))
    payload = {**event, 'message': {**event['message'], 'text': question or SECRET}}
    status, body = handle_crm_dispatch(json.dumps(payload).encode(), 'Bearer ' + TOKEN,
                                       token=TOKEN, processor=worker)
    terminal = [fields for name, fields in logs if name == 'crm_dispatch_decision']
    return {'status': status, 'body': body, 'terminal': terminal, 'logs': logs}
`;

test('@spec:AC-533 terminal trace distinguishes grounded answer, grounding handoff and explicit no action', () => {
  const result = runPython(fixture + String.raw`
class Generator:
    def __init__(self, handoff=False): self.handoff = handoff
    def generate(self, state, emit):
        emit('retrieval_completed', {'status': 'EXECUTED', 'hitCount': 2,
             'documentIds': [DOCUMENT], 'documentVersionIds': [VERSION], 'chunkIds': [CHUNK], 'content': SECRET})
        emit('turn_classified', {'interpreted_intent': 'ATTRIBUTE_QUERY',
             'handoff_decision': 'NONE', 'query': SECRET})
        emit('model_call_started', {'provider': 'openai', 'prompt': SECRET})
        emit('model_called', {'provider': 'openai', 'response': SECRET})
        if self.handoff:
            emit('grounding_result', {'passed': False, 'reason': 'UNSUPPORTED_FACTUAL_CLAIM'})
            emit('grounding_failed', {'reason': 'UNSUPPORTED_FACTUAL_CLAIM',
                 'grounding_failure_origin': 'USER_REQUESTED_UNSUPPORTED_FACT'})
            state.decision = AgentDecision.HUMAN_HANDOFF_REQUIRED
            state.stage = AgentStage.HANDOFF
            state.handoff_context = {'reason': 'UNSUPPORTED_FACTUAL_CLAIM', 'messages': [SECRET]}
            return ''
        emit('grounding_result', {'passed': True, 'requiresEvidence': True})
        state.decision = AgentDecision.ANSWER_GROUNDED
        return 'Resposta controlada'
class NoActionGraph:
    def run(self, state):
        state.context['noAction'] = True
        state.context['runtimeEvents'] = [{'stage': 'retrieval_completed',
            'details': {'status': 'SKIPPED_NOT_REQUIRED', 'hitCount': 0}}]
        return state
class RetrievalFailureGraph:
    def run(self, state):
        state.decision = AgentDecision.HUMAN_HANDOFF_REQUIRED
        state.handoff_context = {'reason': 'RETRIEVAL_UNAVAILABLE_FOR_FACTUAL_QUERY'}
        state.context['runtimeEvents'] = [
            {'stage': 'retrieval_completed', 'details': {'status': 'FAILED_TRANSIENT_EXHAUSTED', 'hitCount': 0}},
            {'stage': 'controlled_retrieval_failure', 'details': {'body': SECRET}},
        ]
        return state
answer = invoke(AgentRuntimeGraph(response_generator=Generator()))
handoff = invoke(AgentRuntimeGraph(response_generator=Generator(handoff=True)))
silent = invoke(NoActionGraph())
requested = invoke(AgentRuntimeGraph(response_generator=Generator()), 'Quero falar com atendente')
unavailable = invoke(RetrievalFailureGraph())
print(json.dumps({'answer': answer, 'handoff': handoff, 'silent': silent, 'requested': requested, 'unavailable': unavailable}))
`);
  assert.deepEqual(result.answer.terminal.map((x) => [x.action, x.decisionOrigin, x.reasonCode, x.modelInvoked, x.groundingStatus]),
    [['SEND_MESSAGE', 'MODEL', 'GROUNDED_MODEL_RESPONSE', true, 'PASSED']]);
  assert.deepEqual(result.handoff.terminal.map((x) => [x.action, x.decisionOrigin, x.reasonCode, x.groundingFailureOrigin]),
    [['HANDOFF', 'GROUNDING', 'UNSUPPORTED_FACTUAL_CLAIM', 'USER_REQUESTED_UNSUPPORTED_FACT']]);
  assert.equal(result.answer.terminal[0].commercialEvidencePresent, true);
  assert.equal(result.handoff.terminal[0].commercialEvidencePresent, false);
  assert.deepEqual(result.silent.terminal.map((x) => [x.action, x.decisionOrigin, x.reasonCode, x.modelInvoked]),
    [['NO_ACTION', 'DETERMINISTIC_RULE', 'EXPLICIT_NO_ACTION', false]]);
  assert.deepEqual(result.requested.terminal.map((x) => [x.action, x.decisionOrigin, x.reasonCode, x.modelInvoked]),
    [['HANDOFF', 'DETERMINISTIC_RULE', 'PATIENT_REQUESTED_HUMAN', false]]);
  assert.deepEqual(result.requested.terminal.map((x) => [x.groundingStatus, x.groundingPassed]),
    [['NOT_RUN', null]]);
  assert.deepEqual(result.unavailable.terminal.map((x) => [x.action, x.decisionOrigin, x.retrievalStatus, x.retrievalExecuted]),
    [['HANDOFF', 'ERROR_POLICY', 'FAILED_TRANSIENT_EXHAUSTED', true]]);
  assert.deepEqual(result.unavailable.terminal.map((x) => [x.groundingStatus, x.groundingPassed]),
    [['NOT_RUN', null]]);
  for (const item of [result.answer, result.handoff, result.silent, result.requested, result.unavailable]) {
    assert.equal(item.status, 200);
    assert.equal(item.terminal[0].correlationId, '142f8614-97c4-4f85-a202-df0cb51b39d0');
    assert.equal(item.terminal[0].organizationId, '38002ccb-9edb-4dcb-aacf-76c0b6ca1692');
    assert.equal(item.terminal[0].conversationId, 'a341db43-d53d-4f19-b4d3-3c1a7c6f5409');
    assert.equal(Object.hasOwn(item.terminal[0], 'dispatchId'), false);
  }
  assert.deepEqual(result.answer.terminal[0].documentIds, ['99999999-9999-4999-8999-999999999999']);
  assert.deepEqual(result.answer.terminal[0].documentVersionIds, ['178d4876-0428-4286-87c5-8711e090a767']);
  assert.deepEqual(result.answer.terminal[0].chunkIds, ['f69e2b48-e389-586b-b84f-9ebe80ef6756']);
});

test('@spec:AC-534 terminal diagnostics are allowlisted, visible and never leak content or secrets', () => {
  const result = runPython(fixture + String.raw`
class FailureGraph:
    def run(self, state):
        state.context['runtimeEvents'] = [
            {'stage': 'retrieval_completed', 'details': {'status': SECRET, 'hitCount': SECRET,
              'documentVersionIds': [SECRET], 'chunkIds': [SECRET], 'content': SECRET}},
            {'stage': 'model_call_started', 'details': {'prompt': SECRET}},
            {'stage': 'model_call_failed', 'details': {'body': SECRET, 'token': SECRET}},
            {'stage': 'grounding_failed', 'details': {'reason': SECRET, 'prompt': SECRET}},
        ]
        raise RuntimeError(SECRET)
failed = invoke(FailureGraph())
missing_logs = []
missing_worker = CrmDispatchProcessor(config_repository=InMemoryOrganizationConfigRepository([]),
    logger=lambda name, fields: missing_logs.append((name, fields)))
missing_status, missing_body = handle_crm_dispatch(json.dumps(event).encode(),
    'Bearer ' + TOKEN, token=TOKEN, processor=missing_worker)
def failing_terminal_logger(name, fields):
    if name == 'crm_dispatch_decision':
        raise RuntimeError(SECRET)
class AnswerGraph:
    def run(self, state):
        state.response_text = 'Resposta controlada'
        return state
worker = CrmDispatchProcessor(config_repository=repo, graph_factory=lambda _: AnswerGraph(),
                              logger=failing_terminal_logger)
business_status, business_body = handle_crm_dispatch(json.dumps(event).encode(),
    'Bearer ' + TOKEN, token=TOKEN, processor=worker)
stream = io.StringIO()
logger = logging.getLogger('ai_agent_runtime.crm_dispatch')
handler = logging.StreamHandler(stream)
logger.addHandler(handler)
try:
    _safe_crm_log('crm_dispatch_decision', {'action': 'HANDOFF', 'correlationId': CORRELATION})
finally:
    logger.removeHandler(handler)
print(json.dumps({'failed': failed, 'defaultLog': stream.getvalue(),
                  'businessStatus': business_status, 'businessAction': business_body.get('action'),
                  'missingStatus': missing_status,
                  'missingTerminal': [fields for name, fields in missing_logs if name == 'crm_dispatch_decision']}))
`);
  assert.equal(result.failed.status, 503);
  assert.deepEqual(result.failed.body, { error: 'RUNTIME_UNAVAILABLE' });
  assert.equal(result.failed.terminal.length, 1);
  assert.equal(result.failed.terminal[0].action, 'ERROR');
  assert.equal(result.failed.terminal[0].reasonCode, 'MODEL_FAILURE');
  assert.equal(result.failed.terminal[0].modelInvoked, null);
  assert.equal(result.failed.terminal[0].retrievalStatus, 'UNKNOWN');
  assert.deepEqual(result.failed.terminal[0].documentVersionIds, []);
  assert.deepEqual([result.businessStatus, result.businessAction], [200, 'SEND_MESSAGE']);
  assert.equal(result.missingStatus, 503);
  assert.equal(result.missingTerminal[0].reasonCode, 'CONFIG_UNAVAILABLE');
  assert.match(result.defaultLog, /crm_dispatch_decision/);
  assert.doesNotMatch(JSON.stringify(result), /patient-and-token-must-not-appear|local-test-service-token/);
});

test('@spec:AC-533 real runtime generator reports retrieved version and chunks with a controlled model transport', () => {
  const result = runPython(fixture + String.raw`
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
POLICY_CHUNK = '77777777-7777-4777-8777-777777777777'
class Retrieval:
    def search(self, organization_id, query):
        assert organization_id == ORG
        return [
            {'id': CHUNK, 'organization_id': ORG, 'document_version_id': VERSION,
             'content': 'Procedimentos e Valores: Botox, unidade sem reposição — R$ 75. Botox com revisão em 15 dias — R$ 750.'},
            {'id': POLICY_CHUNK, 'organization_id': ORG, 'document_version_id': VERSION,
             'content': 'O orçamento final é definido após a avaliação gratuita.'},
        ]
    def closed_world_procedure_decision(self, organization_id, query):
        return None
class Transport:
    def post_json(self, url, *, headers, payload):
        return {'id': 'controlled-model', 'status': 'completed',
                'output_text': 'Botox com revisão em 15 dias custa R$ 750.'}
graph = AgentRuntimeGraph(response_generator=OpenAIWhatsAppResponseGenerator(
    OpenAIResponsesProvider(IntegrationConfig(openai_api_key='test-only-key'), Transport()),
    retrieval=Retrieval()))
print(json.dumps(invoke(graph, 'Quanto custa botox?')))
`);
  assert.equal(result.status, 200);
  assert.equal(result.body.action, 'SEND_MESSAGE');
  assert.equal(result.terminal[0].decisionOrigin, 'MODEL');
  assert.equal(result.terminal[0].retrievalHitCount, 2);
  assert.deepEqual(result.terminal[0].documentVersionIds, ['178d4876-0428-4286-87c5-8711e090a767']);
  assert.deepEqual(result.terminal[0].chunkIds, [
    'f69e2b48-e389-586b-b84f-9ebe80ef6756', '77777777-7777-4777-8777-777777777777',
  ]);
  assert.equal(result.terminal[0].modelCallsCompleted, 1);
  assert.equal(result.terminal[0].groundingStatus, 'PASSED');
  assert.doesNotMatch(JSON.stringify(result.logs), /test-only-key|orçamento final|Botox com revisão/);
});

test('@spec:AC-533 safe regeneration is distinguished from direct model answer', () => {
  const result = runPython(fixture + String.raw`
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
class EmptyRetrieval:
    def search(self, organization_id, query): return []
    def closed_world_procedure_decision(self, organization_id, query): return None
class ScriptedTransport:
    def __init__(self): self.calls = 0
    def post_json(self, url, *, headers, payload):
        self.calls += 1
        answer = ('Nao tenho essa informacao na minha base.' if self.calls == 1
                  else 'Qual procedimento voce procura?')
        return {'id': 'controlled', 'status': 'completed', 'output_text': answer}
transport = ScriptedTransport()
graph = AgentRuntimeGraph(response_generator=OpenAIWhatsAppResponseGenerator(
    OpenAIResponsesProvider(IntegrationConfig(openai_api_key='test-only-key'), transport),
    retrieval=EmptyRetrieval()))
print(json.dumps({'dispatch': invoke(graph, 'Vocês fazem botox?'), 'calls': transport.calls}))
`);
  assert.equal(result.dispatch.status, 200);
  assert.equal(result.dispatch.body.action, 'SEND_MESSAGE');
  assert.deepEqual(result.dispatch.terminal.map((x) => [x.decisionOrigin, x.reasonCode, x.regenerationUsed, x.modelCallsCompleted]),
    [['FALLBACK', 'CONVERSATIONAL_REGENERATION_ACCEPTED', true, 2]]);
  assert.equal(result.calls, 2);
});
