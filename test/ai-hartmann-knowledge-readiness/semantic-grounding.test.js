'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

function python(source) {
  const run = spawnSync('python3', ['-c', source], {
    cwd: process.cwd(), env: { ...process.env, PYTHONPATH: 'src' }, encoding: 'utf8',
  });
  assert.equal(run.status, 0, run.stderr || run.stdout);
  return JSON.parse(run.stdout);
}

test('@spec:AC-548 operational scheduling paraphrase requires an eligible source', () => {
  const result = python(String.raw`
import json
from ai_agent_runtime.whatsapp.zapi_server import validate_live_grounding
source = [{'content': 'O agendamento de avaliação funciona pelo WhatsApp.'}]
def passes(text, evidence):
    return validate_live_grounding(text, evidence_count=len(evidence), evidence=evidence)['passed']
print(json.dumps({
  'paraphrase': passes('O agendamento de avaliação é feito pelo WhatsApp.', source),
  'unsupported': passes('Você pode marcar uma avaliação pelo WhatsApp.', [{'content': 'A clínica atende por telefone.'}]),
  'unrelated': passes('O agendamento de avaliação é feito pelo WhatsApp.', [{'content': 'Botox com revisão custa R$ 750.'}]),
  'negative': passes('A clínica não faz agendamento pelo WhatsApp.', source),
}))
`);
  assert.deepEqual(result, { paraphrase: true, unsupported: false, unrelated: false, negative: false });
});

test('@spec:AC-549 independent sensitive claims remain strictly grounded', () => {
  const result = python(String.raw`
import json
from ai_agent_runtime.whatsapp.zapi_server import validate_live_grounding
source = [{'content': 'O agendamento de avaliação funciona pelo WhatsApp.'}]
price = [{'content': 'Botox com revisão em 15 dias custa R$ 750.'}]
def passes(text, evidence):
    return validate_live_grounding(text, evidence_count=len(evidence), evidence=evidence)['passed']
print(json.dumps({
  'hours': passes('O agendamento de avaliação funciona pelo WhatsApp. Amanhã às 10h está disponível.', source),
  'price': passes('Botox com revisão em 15 dias custa R$ 900.', price),
  'payment': passes('O agendamento funciona pelo WhatsApp. Você pode parcelar em 10x sem juros.', source),
  'free': passes('O agendamento funciona pelo WhatsApp. A avaliação é gratuita.', source),
  'clinical': passes('O agendamento funciona pelo WhatsApp. O resultado é garantido.', source),
  'supportedPrice': passes('Botox com revisão em 15 dias custa R$ 750.', price),
}))
`);
  assert.deepEqual(result, {
    hours: false, price: false, payment: false, free: false, clinical: false, supportedPrice: true,
  });
});

test('@spec:AC-549 absent treatment, specific availability, human request and medication advice keep safe terminal decisions', () => {
  const result = python(String.raw`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.state import AgentState
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.integrations.config import IntegrationConfig
class EmptyRetrieval:
    def search(self, organization_id, query, *, limit=6): return []
    def closed_world_procedure_decision(self, organization_id, query): return None
class Model:
    def __init__(self): self.calls = 0
    def post_json(self, url, *, headers, payload):
        self.calls += 1
        return {'status':'completed','output_text':'Sim, fazemos preenchimento de glúteo.'}
def run(question):
    model = Model()
    graph = AgentRuntimeGraph(response_generator=OpenAIWhatsAppResponseGenerator(
        OpenAIResponsesProvider(IntegrationConfig(openai_api_key='mock'),model),
        retrieval=EmptyRetrieval()))
    state = graph.run(AgentState(conversation_id='local',organization_id='38002ccb-9edb-4dcb-aacf-76c0b6ca1692',
                                 current_message=question))
    return {'decision':state.decision.value,'reason':(state.handoff_context or {}).get('reason'),
            'response':state.response_text,'modelCalls':model.calls}
print(json.dumps({
  'absent':run('Vocês fazem preenchimento de glúteo?'),
  'availability':run('Qual horário vocês têm amanhã?'),
  'human':run('Quero falar com uma pessoa.'),
  'medication':run('Preciso de uma orientação sobre medicamento.'),
}))
`);
  assert.deepEqual(Object.fromEntries(Object.entries(result).map(([key, value]) => [key, value.decision])), {
    absent: 'HUMAN_HANDOFF_REQUIRED', availability: 'HUMAN_HANDOFF_REQUIRED',
    human: 'HUMAN_HANDOFF_REQUIRED', medication: 'HUMAN_HANDOFF_REQUIRED',
  });
  assert.equal(result.absent.reason, 'UNSUPPORTED_FACTUAL_CLAIM');
  assert.equal(result.availability.reason, 'SCHEDULING_TIME_CONFIRMATION_REQUIRED');
  assert.equal(result.human.reason, 'PATIENT_REQUESTED_HUMAN');
  assert.equal(result.medication.reason, 'MEDICATION_GUIDANCE_REQUIRED');
  assert.ok(Object.values(result).every((item) => !item.response));
  assert.equal(result.human.modelCalls, 0);
  assert.equal(result.medication.modelCalls, 0);
});

test('@spec:AC-550 a complete supported sentence survives an unsupported independent sentence', () => {
  const result = python(String.raw`
import json
from ai_agent_runtime.crm_dispatch import CrmDispatchProcessor, handle_crm_dispatch
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.organization_config import InMemoryOrganizationConfigRepository, OrganizationRuntimeConfig
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator, ZApiRuntimeRetrieval
ORG = '38002ccb-9edb-4dcb-aacf-76c0b6ca1692'
OTHER = '11111111-1111-4111-8111-111111111111'
def uid(n): return f'00000000-0000-4000-8000-{n:012d}'
class Retrieval(ZApiRuntimeRetrieval):
    def __init__(self): self.calls = []
    def _get_json(self, table, params, *, endpoint):
        self.calls.append((table, params.get('organization_id')))
        if table == 'document_versions':
            return [{'id': uid(1), 'organization_id': ORG, 'document_id': uid(2),
                     'version_number': 1, 'status': 'PUBLISHED', 'processing_valid': True},
                    {'id': uid(3), 'organization_id': OTHER, 'document_id': uid(4),
                     'version_number': 1, 'status': 'PUBLISHED', 'processing_valid': True}]
        if table == 'chunks':
            return [{'id': uid(5), 'organization_id': ORG, 'document_id': uid(2),
                     'document_version_id': uid(1), 'content': 'O agendamento de avaliação funciona pelo WhatsApp.'}]
        return []
    def closed_world_procedure_decision(self, organization_id, query): return None
class Transport:
    def __init__(self, text): self.text, self.calls = text, 0
    def post_json(self, url, *, headers, payload):
        self.calls += 1
        return {'id': 'mock', 'status': 'completed', 'output_text': self.text}
def dispatch(answer):
    retrieval, transport, logs = Retrieval(), Transport(answer), []
    graph = AgentRuntimeGraph(response_generator=OpenAIWhatsAppResponseGenerator(
        OpenAIResponsesProvider(IntegrationConfig(openai_api_key='mock'), transport), retrieval=retrieval))
    worker = CrmDispatchProcessor(config_repository=InMemoryOrganizationConfigRepository(
        [OrganizationRuntimeConfig(organization_id=ORG)]),
        graph_factory=lambda _: graph, logger=lambda name, fields: logs.append((name, fields)))
    event = {'version':'1','correlationId':uid(20),'organizationId':ORG,'conversationId':uid(21),
             'providerConnectionId':uid(22),'contactId':None,'inboundMessageId':uid(23),
             'mode':'AI','modeVersion':1,'message':{'type':'text','text':'Como funciona o agendamento?',
             'timestamp':'2026-10-10T12:00:00Z'},'history':[]}
    status, body = handle_crm_dispatch(json.dumps(event).encode(), 'Bearer local-mock-service-token-000000000000',
                                       token='local-mock-service-token-000000000000', processor=worker)
    terminal = [fields for name, fields in logs if name == 'crm_dispatch_decision'][-1]
    return {'status':status,'action':body.get('action'),'message':body.get('message'),
            'reason':terminal['reasonCode'],'origin':terminal['decisionOrigin'],
            'grounding':terminal['groundingStatus'],'calls':transport.calls,
            'scoped':all(org == 'eq.' + ORG for _,org in retrieval.calls),
            'logs':json.dumps(logs)}
partial = dispatch('O agendamento de avaliação funciona pelo WhatsApp. Amanhã às 10h está disponível. Quer conversar sobre o agendamento?')
unsafe = dispatch('Amanhã às 10h está disponível.')
print(json.dumps({'partial':partial,'unsafe':unsafe}))
`);
  assert.equal(result.partial.status, 200);
  assert.equal(result.partial.action, 'SEND_MESSAGE');
  assert.equal(result.partial.message, 'O agendamento de avaliação funciona pelo WhatsApp. Quer conversar sobre o agendamento?');
  assert.equal(result.partial.reason, 'SUPPORTED_PARTIAL_RESPONSE');
  assert.equal(result.partial.origin, 'FALLBACK');
  assert.equal(result.partial.grounding, 'PASSED');
  assert.equal(result.partial.calls, 1);
  assert.equal(result.partial.scoped, true);
  assert.equal(result.unsafe.action, 'HANDOFF');
  assert.ok(!/10h|local-mock-service-token|WhatsApp/.test(result.partial.logs));
});
