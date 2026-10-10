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
import json
from ai_agent_runtime.whatsapp.zapi_server import ZApiRuntimeRetrieval, _classify_turn_context, validate_live_grounding

ORG = '38002ccb-9edb-4dcb-aacf-76c0b6ca1692'
OTHER = '11111111-1111-4111-8111-111111111111'
QUESTION = 'Olá! Gostaria de saber quanto custa o Botox e como funciona o agendamento na Clínica Hartmann.'
PRICE = 'Botox com revisão em 15 dias custa R$ 750.'
BUDGET = 'O orçamento final é definido após a avaliação gratuita.'
SCHEDULE = 'O agendamento de avaliação funciona pelo WhatsApp.'
PAYMENT = 'O parcelamento de Botox é em até 10x sem juros.'
def uid(n): return f'00000000-0000-4000-8000-{n:012d}'
def version(n, org=ORG, status='PUBLISHED'):
    return {'id': uid(n), 'organization_id': org, 'document_id': uid(n+100),
            'version_number': 1, 'status': status, 'processing_valid': True}
VERSIONS = [version(n) for n in (1, 2, 3, 4)] + [version(90, OTHER), version(91, ORG, 'DRAFT')]
def chunk(n, version_number, content, org=ORG):
    return {'id': uid(n+200), 'organization_id': org, 'document_id': uid(version_number+100),
            'document_version_id': uid(version_number), 'content': content}
CHUNKS = [
    chunk(1, 1, PRICE),
    *[chunk(n, 1, f'Botox: informacao comercial complementar {n}.') for n in range(2, 7)],
    chunk(7, 2, BUDGET),
    chunk(8, 3, SCHEDULE),
    chunk(9, 4, PAYMENT),
    chunk(90, 90, 'O agendamento de Botox é instantâneo.', OTHER),
    chunk(91, 91, 'Botox custa R$ 1.'),
]
class Retrieval(ZApiRuntimeRetrieval):
    def __init__(self, include_schedule=True):
        self.include_schedule = include_schedule
        self.calls = []
    def _get_json(self, table, params, *, endpoint):
        self.calls.append((table, dict(params)))
        if table == 'document_versions': return VERSIONS
        if table != 'chunks': return []
        term = params['content'].removeprefix('ilike.*').removesuffix('*').lower()
        allowed = set(params['document_version_id'].removeprefix('in.(').removesuffix(')').split(','))
        return [row for row in CHUNKS if row['organization_id'] == ORG
                and row['document_version_id'] in allowed
                and (self.include_schedule or row['id'] != uid(208))
                and term in row['content'].lower()][:int(params['limit'])]
    def closed_world_procedure_decision(self, organization_id, query): return None
`;

test('@spec:AC-536 multi-intent retrieval presents published price, budget and scheduling evidence within four chunks', () => {
  const result = runPython(fixture + String.raw`
r = Retrieval()
cases = [QUESTION, 'Quanto custa Botox?', 'Como agendar uma avaliação?',
         'Quanto custa Botox e como posso agendar?', 'Posso parcelar Botox?',
         'O preço informado já é definitivo?']
results = []
for question in cases:
    rows = r.search(ORG, question)
    turn = _classify_turn_context(question, rows)
    results.append({'ids': [row['id'] for row in rows[:4]], 'intent': turn['interpreted_intent'],
                    'topics': turn.get('requested_topics'),
                    'scoped': all(row['organization_id'] == ORG and row['document_version_id'] not in (uid(90), uid(91)) for row in rows)})
print(json.dumps(results))
`);
  const id = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
  assert.equal(result.length, 6);
  assert.ok(result.every((item) => item.scoped));
  for (const index of [0, 3]) {
    assert.equal(result[index].intent, 'ATTRIBUTE_QUERY');
    assert.deepEqual(result[index].topics, ['PRICE', 'SCHEDULING']);
    assert.ok(result[index].ids.includes(id(201)));
    assert.ok(result[index].ids.includes(id(207)));
    assert.ok(result[index].ids.includes(id(208)));
  }
  assert.ok(result[1].ids.includes(id(201)) && result[1].ids.includes(id(207)));
  assert.ok(result[2].ids.includes(id(208)));
  assert.ok(result[4].ids.includes(id(209)));
  assert.ok(result[5].ids.includes(id(207)));
});

test('@spec:AC-537 separate supported claims in one sentence pass grounding; wrong prices and invented scheduling fail', () => {
  const result = runPython(fixture + String.raw`
evidence = [{'content': PRICE}, {'content': SCHEDULE}]
answers = [
    'Botox com revisão em 15 dias custa R$ 750 e o agendamento de avaliação funciona pelo WhatsApp.',
    'Botox com revisão em 15 dias custa R$ 900 e o agendamento de avaliação funciona pelo WhatsApp.',
    'Botox com revisão em 15 dias custa R$ 750 e o agendamento é confirmado automaticamente.',
    'Botox com revisão em 15 dias custa R$ 750 e R$ 900.',
]
print(json.dumps([validate_live_grounding(answer, evidence_count=2, evidence=evidence)['passed'] for answer in answers]))
`);
  assert.deepEqual(result, [true, false, false, false]);
});

test('@spec:AC-538 @spec:AC-539 CRM dispatch answers the exact dual-intent question and keeps partial answers safe', () => {
  const result = runPython(fixture + String.raw`
from ai_agent_runtime.crm_dispatch import CrmDispatchProcessor, handle_crm_dispatch
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.organization_config import InMemoryOrganizationConfigRepository, OrganizationRuntimeConfig
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
TOKEN = 'local-test-service-token-000000000000'
repo = InMemoryOrganizationConfigRepository([OrganizationRuntimeConfig(organization_id=ORG)])
class Transport:
    def __init__(self, answer): self.answer, self.calls = answer, 0
    def post_json(self, url, *, headers, payload):
        self.calls += 1
        return {'id': 'controlled', 'status': 'completed', 'output_text': self.answer}
def run(question, answer, include_schedule=True):
    retrieval, transport, logs = Retrieval(include_schedule), Transport(answer), []
    graph = AgentRuntimeGraph(response_generator=OpenAIWhatsAppResponseGenerator(
        OpenAIResponsesProvider(IntegrationConfig(openai_api_key='test-only-key'), transport),
        retrieval=retrieval))
    worker = CrmDispatchProcessor(config_repository=repo, graph_factory=lambda _: graph,
                                  logger=lambda name, fields: logs.append((name, fields)))
    event = {'version': '1', 'correlationId': uid(300), 'organizationId': ORG,
             'conversationId': uid(301), 'providerConnectionId': uid(302),
             'contactId': None, 'inboundMessageId': uid(303), 'mode': 'AI', 'modeVersion': 1,
             'message': {'type': 'text', 'text': question, 'timestamp': '2026-10-08T12:00:00Z'}}
    status, body = handle_crm_dispatch(json.dumps(event).encode(), 'Bearer '+TOKEN,
                                       token=TOKEN, processor=worker)
    terminal_events = [fields for name, fields in logs if name == 'crm_dispatch_decision']
    assert terminal_events, (status, body)
    terminal = terminal_events[-1]
    return {'status': status, 'action': body.get('action'), 'reason': terminal['reasonCode'],
            'origin': terminal['decisionOrigin'], 'commercialEvidencePresent': terminal['commercialEvidencePresent'],
            'groundingPassed': terminal['groundingPassed'], 'promptChunkIds': terminal.get('promptChunkIds'),
            'turnTopics': terminal.get('turnTopics'), 'calls': transport.calls,
            'logs': json.dumps(logs)}
valid = run(QUESTION, 'Botox com revisão em 15 dias custa R$ 750 e o agendamento de avaliação funciona pelo WhatsApp.')
partial = run(QUESTION, 'Botox com revisão em 15 dias custa R$ 750. Qual dia prefere para uma avaliação?', False)
unsupported = run(QUESTION, 'Botox com revisão em 15 dias custa R$ 750 e o agendamento é confirmado automaticamente.', False)
cases = [
    run('Quanto custa Botox?', 'Botox com revisão em 15 dias custa R$ 750. O orçamento final é definido após a avaliação gratuita.'),
    run('Como agendar uma avaliação?', 'O agendamento de avaliação funciona pelo WhatsApp.'),
    run('Quanto custa Botox e como posso agendar?', 'Botox com revisão em 15 dias custa R$ 750 e o agendamento de avaliação funciona pelo WhatsApp.'),
    run('Posso parcelar Botox?', 'O parcelamento de Botox é em até 10x sem juros.'),
    run('O preço informado já é definitivo?', 'O orçamento final é definido após a avaliação gratuita.'),
]
print(json.dumps({'valid': valid, 'partial': partial, 'unsupported': unsupported, 'cases': cases}))
`);
  const id = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
  assert.deepEqual([result.valid.action, result.partial.action, result.unsupported.action],
    ['SEND_MESSAGE', 'SEND_MESSAGE', 'HANDOFF']);
  assert.deepEqual([result.valid.reason, result.partial.reason, result.unsupported.reason],
    ['GROUNDED_MODEL_RESPONSE', 'GROUNDED_MODEL_RESPONSE', 'UNSUPPORTED_FACTUAL_CLAIM']);
  assert.deepEqual(result.valid.turnTopics, ['PRICE', 'SCHEDULING']);
  assert.ok(result.valid.promptChunkIds.includes(id(201)));
  assert.ok(result.valid.promptChunkIds.includes(id(207)));
  assert.ok(result.valid.promptChunkIds.includes(id(208)));
  assert.equal(result.unsupported.commercialEvidencePresent, true);
  assert.equal(result.unsupported.groundingPassed, false);
  assert.ok([result.valid, result.partial].every((item) => item.status === 200 && item.calls === 1));
  assert.equal(result.unsupported.status, 200);
  assert.equal(result.unsupported.calls, 2);
  assert.deepEqual(result.cases.map((item) => item.action), Array(5).fill('SEND_MESSAGE'));
  assert.deepEqual(result.cases.map((item) => item.reason), Array(5).fill('GROUNDED_MODEL_RESPONSE'));
  assert.ok(result.cases.every((item) => item.status === 200 && item.calls === 1 && item.groundingPassed));
  assert.ok(result.cases.every((item) => item.promptChunkIds.length > 0));
  assert.ok([result.valid, result.partial, result.unsupported].every((item) =>
    !/local-test-service-token|test-only-key|Botox com revisão|agendamento é confirmado/.test(item.logs)));
});
