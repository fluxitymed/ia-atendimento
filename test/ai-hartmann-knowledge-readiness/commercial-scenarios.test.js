'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

test('@spec:AC-499 @spec:AC-535 ten Hartmann questions use published tenant evidence and safe decisions', () => {
  const source = String.raw`
import json
from ai_agent_runtime.crm_dispatch import CrmDispatchProcessor, handle_crm_dispatch
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.organization_config import InMemoryOrganizationConfigRepository, OrganizationRuntimeConfig
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator, ZApiRuntimeRetrieval, validate_live_grounding

ORG = '38002ccb-9edb-4dcb-aacf-76c0b6ca1692'
OTHER = '11111111-1111-4111-8111-111111111111'
TOKEN = 'local-only-service-token-000000000000'
def uid(number): return f'00000000-0000-4000-8000-{number:012d}'
def version(number, org=ORG, status='PUBLISHED'):
    return {'id': uid(number), 'organization_id': org, 'document_id': uid(number+100),
            'version_number': 1, 'status': status, 'processing_valid': True}
VERSIONS = [version(n) for n in range(1, 6)] + [version(90, OTHER), version(91, ORG, 'DRAFT')]
def chunk(number, version_number, content, org=ORG):
    return {'id': uid(number+200), 'organization_id': org, 'document_id': uid(version_number+100),
            'document_version_id': uid(version_number), 'content': content}
CHUNKS = [
    chunk(1, 1, 'Clínica Hartmann — Procedimentos e Valores > Botox\n- Botox, unidade sem reposição — R$ 75\n- Botox com revisão em 15 dias — R$ 750.'),
    chunk(2, 1, 'Clínica Hartmann — Procedimentos e Valores > Regra final\nO orçamento final é definido após a avaliação gratuita.'),
    chunk(3, 2, 'Clínica Hartmann — Avaliação\nA avaliação padrão é gratuita. Avaliação específica pela médica custa R$ 200.'),
    chunk(4, 3, 'Clínica Hartmann — Parcelamento\nAté 10x sem juros no cartão de crédito.'),
    chunk(5, 4, 'Clínica Hartmann — Handoff humano\nPedido de remarcação, pedido de cancelamento ou orientação clínica exigem humano. Não recomendar medicamento.'),
    chunk(6, 5, 'Clínica Hartmann — Agendamento\nA equipe pode agendar avaliação sem prometer horário não confirmado.'),
    chunk(90, 90, 'Botox custa R$ 1.', OTHER),
    chunk(91, 91, 'Botox custa R$ 2.'),
    *[chunk(20+i, 5, f'Vocês fazem atendimento comercial genérico {i}.') for i in range(6)],
]
class Retrieval(ZApiRuntimeRetrieval):
    def __init__(self): self.calls = []
    def _get_json(self, table, params, *, endpoint):
        self.calls.append((table, dict(params)))
        if table == 'document_versions': return VERSIONS
        if table == 'chunks':
            term = params['content'].removeprefix('ilike.*').removesuffix('*').lower()
            allowed = set(params['document_version_id'].removeprefix('in.(').removesuffix(')').split(','))
            return [row for row in CHUNKS if row['organization_id'] == ORG
                    and row['document_version_id'] in allowed and term in row['content'].lower()][:int(params['limit'])]
        return []
    def closed_world_procedure_decision(self, organization_id, query): return None
ANSWERS = {
    'Quanto custa botox?': 'Botox com revisão em 15 dias custa R$ 750. O orçamento final é definido após a avaliação gratuita.',
    'Vocês fazem botox?': 'A clínica oferece Botox.',
    'Esse valor já é o final?': 'O orçamento final é definido após a avaliação gratuita.',
    'A avaliação é gratuita?': 'A avaliação padrão é gratuita.',
    'Posso parcelar?': 'A clínica aceita parcelamento em até 10x sem juros no cartão de crédito.',
    'Vocês fazem um procedimento que não consta no catálogo?': 'Qual procedimento você procura?',
    'Quero agendar uma avaliação.': 'Qual dia você prefere para a avaliação?',
}
class Transport:
    def __init__(self): self.calls = 0
    def post_json(self, url, *, headers, payload):
        self.calls += 1
        question = payload['input'][-1]['content']
        return {'id': 'controlled-response', 'status': 'completed', 'output_text': ANSWERS[question]}
repo = InMemoryOrganizationConfigRepository([OrganizationRuntimeConfig(organization_id=ORG)])
questions = [
    'Quanto custa botox?', 'Vocês fazem botox?', 'Esse valor já é o final?',
    'A avaliação é gratuita?', 'Posso parcelar?', 'Quero remarcar meu horário.',
    'Quero cancelar minha consulta.', 'Qual medicamento devo usar?',
    'Vocês fazem um procedimento que não consta no catálogo?', 'Quero agendar uma avaliação.',
]
results = []
for index, question in enumerate(questions):
    retrieval, transport, logs = Retrieval(), Transport(), []
    provider = OpenAIResponsesProvider(IntegrationConfig(openai_api_key='controlled-only-key'), transport)
    graph = AgentRuntimeGraph(response_generator=OpenAIWhatsAppResponseGenerator(provider, retrieval=retrieval))
    worker = CrmDispatchProcessor(config_repository=repo, graph_factory=lambda _, graph=graph: graph,
                                  logger=lambda name, fields: logs.append((name, fields)))
    history = []
    if index == 2:
        history = [
            {'role': 'contact', 'text': 'Quanto custa botox?', 'timestamp': '2026-10-08T00:45:00Z'},
            {'role': 'ai', 'text': 'Botox com revisão em 15 dias: R$ 750.', 'timestamp': '2026-10-08T00:45:30Z'},
        ]
    event = {
        'version': '1', 'correlationId': uid(index+300), 'organizationId': ORG,
        'conversationId': uid(index+400), 'providerConnectionId': uid(500),
        'contactId': None, 'inboundMessageId': uid(index+600), 'mode': 'AI', 'modeVersion': 1,
        'message': {'type': 'text', 'text': question, 'timestamp': '2026-10-08T00:46:49Z'},
        'history': history,
    }
    status, body = handle_crm_dispatch(json.dumps(event).encode(), 'Bearer '+TOKEN,
                                       token=TOKEN, processor=worker)
    terminal = [fields for name, fields in logs if name == 'crm_dispatch_decision'][-1]
    results.append({'question': question, 'status': status, 'action': body.get('action'),
                    'message': body.get('message'), 'origin': terminal['decisionOrigin'],
                    'reason': terminal['reasonCode'], 'model': terminal['modelInvoked'],
                    'grounding': terminal['groundingStatus'], 'retrieval': terminal['retrievalStatus'],
                    'versions': terminal['documentVersionIds'], 'chunks': terminal['chunkIds'],
                    'transportCalls': transport.calls,
                    'scoped': all(params.get('organization_id') == 'eq.'+ORG for table, params in retrieval.calls),
                    'noForbiddenVersion': uid(90) not in terminal['documentVersionIds'] and uid(91) not in terminal['documentVersionIds']})
wrong_price = validate_live_grounding('Botox com revisão em 15 dias custa R$ 900.',
    evidence_count=1, evidence=[CHUNKS[0]])['passed']
print(json.dumps({'results': results, 'wrongPricePassed': wrong_price}))
`;
  const run = spawnSync('python3', ['-c', source], {
    cwd: process.cwd(), env: { ...process.env, PYTHONPATH: 'src' }, encoding: 'utf8',
  });
  assert.equal(run.status, 0, run.stderr || run.stdout);
  const { results, wrongPricePassed } = JSON.parse(run.stdout);
  assert.equal(wrongPricePassed, false);
  assert.equal(results.length, 10);
  assert.ok(results.every((item) => item.status === 200 && item.scoped && item.noForbiddenVersion));
  assert.deepEqual(results.map((item) => item.action), [
    'SEND_MESSAGE', 'SEND_MESSAGE', 'SEND_MESSAGE', 'SEND_MESSAGE', 'SEND_MESSAGE',
    'HANDOFF', 'HANDOFF', 'HANDOFF', 'SEND_MESSAGE', 'SEND_MESSAGE',
  ]);
  assert.deepEqual(results.slice(5, 8).map((item) => [item.origin, item.reason, item.model]), [
    ['DETERMINISTIC_RULE', 'RESCHEDULING_REQUEST', false],
    ['DETERMINISTIC_RULE', 'CANCELLATION_REQUEST', false],
    ['DETERMINISTIC_RULE', 'MEDICATION_GUIDANCE_REQUIRED', false],
  ]);
  assert.ok(results.slice(0, 5).every((item) => item.origin === 'MODEL' && item.grounding === 'PASSED'));
  assert.ok(results.slice(0, 5).every((item) => item.model === true && item.transportCalls === 1));
  assert.ok(results.slice(5, 8).every((item) => item.grounding === 'NOT_RUN' && item.transportCalls === 0));
  assert.ok(results.slice(0, 3).every((item) => item.versions.includes('00000000-0000-4000-8000-000000000001')));
  assert.ok(results[0].chunks.includes('00000000-0000-4000-8000-000000000201'));
  assert.ok(results[0].chunks.includes('00000000-0000-4000-8000-000000000202'));
  assert.ok(results[1].chunks.includes('00000000-0000-4000-8000-000000000201'));
  assert.ok(results[2].chunks.includes('00000000-0000-4000-8000-000000000202'));
  assert.ok(results[3].chunks.includes('00000000-0000-4000-8000-000000000203'));
  assert.ok(results[4].chunks.includes('00000000-0000-4000-8000-000000000204'));
  assert.ok(results.slice(5, 8).every((item) => item.retrieval === 'SKIPPED_NOT_REQUIRED' && item.chunks.length === 0));
  assert.equal(results[8].message, 'Qual procedimento você procura?');
  assert.match(results[9].message, /qual dia/i);
});
