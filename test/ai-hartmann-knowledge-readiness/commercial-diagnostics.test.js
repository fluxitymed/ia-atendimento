'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

function runPython(source) {
  const run = spawnSync('python3', ['-c', source], {
    cwd: process.cwd(), env: { ...process.env, PYTHONPATH: 'src' }, encoding: 'utf8',
  });
  assert.equal(run.status, 0, run.stderr || run.stdout);
  return JSON.parse(run.stdout);
}

const fixture = String.raw`
import json
from ai_agent_runtime.crm_dispatch import CrmDispatchProcessor, handle_crm_dispatch
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.organization_config import InMemoryOrganizationConfigRepository, OrganizationRuntimeConfig
from ai_agent_runtime.whatsapp.zapi_server import ZApiRuntimeRetrieval, OpenAIWhatsAppResponseGenerator, validate_live_grounding

ORG = '38002ccb-9edb-4dcb-aacf-76c0b6ca1692'
OTHER = '11111111-1111-4111-8111-111111111111'
QUESTION = 'Olá! Gostaria de saber quanto custa o Botox e como funciona o agendamento na Clínica Hartmann.'
TOKEN = 'local-test-service-token-000000000000'
def uid(n): return f'00000000-0000-4000-8000-{n:012d}'
def version(n, org=ORG, status='PUBLISHED'):
    return {'id': uid(n), 'organization_id': org, 'document_id': uid(n+100),
            'version_number': 1, 'status': status, 'processing_valid': True}
VERSIONS = [version(n) for n in range(1, 6)] + [version(90, OTHER), version(91, ORG, 'DRAFT')]
def chunk(n, v, content, org=ORG):
    return {'id': uid(n+200), 'organization_id': org, 'document_id': uid(v+100),
            'document_version_id': uid(v), 'content': content}
CHUNKS = [
    chunk(1, 1, 'Botox com revisão em 15 dias custa R$ 750.'),
    *[chunk(n, 1, f'Botox: informação geral {n}.') for n in range(2, 7)],
    chunk(7, 2, 'O orçamento final é definido após a avaliação gratuita.'),
    chunk(8, 3, 'O agendamento de avaliação funciona pelo WhatsApp.'),
    chunk(9, 4, 'O parcelamento de Botox é em até 10x sem juros.'),
    chunk(10, 5, 'A avaliação padrão é gratuita. A avaliação específica custa R$ 200.'),
    chunk(90, 90, 'O agendamento de Botox é confirmado automaticamente.', OTHER),
    chunk(91, 91, 'Botox custa R$ 1.'),
]
class Retrieval(ZApiRuntimeRetrieval):
    def __init__(self, excluded=()): self.excluded, self.calls = set(excluded), []
    def _get_json(self, table, params, *, endpoint):
        self.calls.append((table, dict(params)))
        if table == 'document_versions': return VERSIONS
        if table != 'chunks': return []
        term = params['content'].removeprefix('ilike.*').removesuffix('*').lower()
        allowed = set(params['document_version_id'].removeprefix('in.(').removesuffix(')').split(','))
        return [row for row in CHUNKS if row['organization_id'] == ORG
                and row['document_version_id'] in allowed and row['id'] not in self.excluded
                and term in row['content'].lower()][:int(params['limit'])]
    def closed_world_procedure_decision(self, organization_id, query): return None
class Transport:
    def __init__(self, answer): self.answers, self.calls = (answer if isinstance(answer, list) else [answer]), 0
    def post_json(self, url, *, headers, payload):
        self.calls += 1
        answer = self.answers[min(self.calls - 1, len(self.answers) - 1)]
        return {'id': 'controlled', 'status': 'completed', 'output_text': answer}
repo = InMemoryOrganizationConfigRepository([OrganizationRuntimeConfig(organization_id=ORG)])
def dispatch(question, answer, *, excluded=(), history=()):
    retrieval, transport, logs = Retrieval(excluded), Transport(answer), []
    graph = AgentRuntimeGraph(response_generator=OpenAIWhatsAppResponseGenerator(
        OpenAIResponsesProvider(IntegrationConfig(openai_api_key='test-only-key'), transport), retrieval=retrieval))
    worker = CrmDispatchProcessor(config_repository=repo, graph_factory=lambda _: graph,
                                  logger=lambda name, fields: logs.append((name, fields)))
    event = {'version': '1', 'correlationId': uid(300), 'organizationId': ORG,
             'conversationId': uid(301), 'providerConnectionId': uid(302),
             'contactId': None, 'inboundMessageId': uid(303), 'mode': 'AI', 'modeVersion': 1,
             'message': {'type': 'text', 'text': question, 'timestamp': '2026-10-08T12:00:00Z'},
             'history': list(history)}
    status, body = handle_crm_dispatch(json.dumps(event).encode(), 'Bearer '+TOKEN,
                                       token=TOKEN, processor=worker)
    terminal = [fields for name, fields in logs if name == 'crm_dispatch_decision'][-1]
    return {'status': status, 'action': body.get('action'), 'message': body.get('message'),
            'intent': terminal['turnIntent'],
            'topics': terminal['turnTopics'], 'coverage': terminal.get('promptTopicCoverage'),
            'candidateTopics': terminal.get('promptCandidateTopics'),
            'missingTopics': terminal.get('missingPromptTopics'),
            'budgetPolicyCandidate': terminal.get('budgetPolicyCandidate'),
            'commercialEvidencePresent': terminal['commercialEvidencePresent'],
            'grounding': terminal['groundingStatus'], 'groundingPassed': terminal['groundingPassed'],
            'groundingFailureOrigin': terminal['groundingFailureOrigin'],
            'initialGroundingFailureOrigin': terminal.get('initialGroundingFailureOrigin'),
            'origin': terminal['decisionOrigin'], 'reason': terminal['reasonCode'],
            'regenerationMode': terminal.get('regenerationMode'),
            'model': terminal['modelInvoked'], 'modelCalls': transport.calls,
            'chunks': terminal['chunkIds'], 'promptChunks': terminal['promptChunkIds'],
            'documents': terminal['documentIds'], 'versions': terminal['documentVersionIds'],
            'scoped': all(params.get('organization_id') == 'eq.'+ORG for _, params in retrieval.calls),
            'logs': json.dumps(logs)}
`;

test('@spec:AC-540 prompt coverage distinguishes complete, partial and absent topic candidates', () => {
  const result = runPython(fixture + String.raw`
answer = 'Botox com revisão em 15 dias custa R$ 750 e o agendamento de avaliação funciona pelo WhatsApp.'
complete = dispatch(QUESTION, answer)
partial = dispatch(QUESTION, 'Botox com revisão em 15 dias custa R$ 750.', excluded=[uid(208)])
absent = dispatch(QUESTION, 'Qual dia prefere para avaliação?', excluded=[uid(201), uid(207), uid(208)])
print(json.dumps({'complete': complete, 'partial': partial, 'absent': absent}))
`);
  assert.deepEqual(result.complete.topics, ['PRICE', 'SCHEDULING']);
  assert.deepEqual(result.complete.candidateTopics, ['PRICE', 'SCHEDULING']);
  assert.equal(result.complete.coverage, 'COMPLETE');
  assert.deepEqual(result.partial.missingTopics, ['SCHEDULING']);
  assert.equal(result.partial.coverage, 'PARTIAL');
  assert.deepEqual(result.absent.missingTopics, ['PRICE', 'SCHEDULING']);
  assert.equal(result.absent.coverage, 'NONE');
  assert.ok([result.complete, result.partial, result.absent].every((item) => item.scoped));
});

test('@spec:AC-541 grounding origin remains undetermined when a factual response fails despite candidates', () => {
  const result = runPython(fixture + String.raw`
candidate = dispatch(QUESTION, 'Botox com revisão em 15 dias custa R$ 900 e o agendamento é confirmado automaticamente.')
missing = dispatch('Quanto custa Botox?', 'Botox custa R$ 900.', excluded=[uid(201)])
print(json.dumps({'candidate': candidate, 'missing': missing}))
`);
  assert.equal(result.candidate.action, 'HANDOFF');
  assert.equal(result.candidate.reason, 'UNSUPPORTED_FACTUAL_CLAIM');
  assert.equal(result.candidate.initialGroundingFailureOrigin, 'UNDETERMINED_UNSUPPORTED_FACT');
  assert.equal(result.candidate.groundingFailureOrigin, 'MODEL_INTRODUCED_UNSUPPORTED_FACT');
  assert.equal(result.candidate.coverage, 'COMPLETE');
  assert.equal(result.candidate.commercialEvidencePresent, true);
  assert.equal(result.missing.action, 'HANDOFF');
  assert.ok(['NONE', 'PARTIAL'].includes(result.missing.coverage));
});

test('@spec:AC-542 exact commercial and safety question matrix reports intent, evidence, model, grounding and action', () => {
  const result = runPython(fixture + String.raw`
cases = [
    (QUESTION, 'Botox com revisão em 15 dias custa R$ 750 e o agendamento de avaliação funciona pelo WhatsApp.'),
    ('Quanto custa Botox?', 'Botox com revisão em 15 dias custa R$ 750.'),
    ('Vocês fazem Botox?', 'A clínica oferece Botox.'),
    ('Quanto custa Botox e como posso agendar?', 'Botox com revisão em 15 dias custa R$ 750 e o agendamento de avaliação funciona pelo WhatsApp.'),
    ('Como funciona o agendamento?', 'O agendamento de avaliação funciona pelo WhatsApp.'),
    ('Posso parcelar?', 'O parcelamento de Botox é em até 10x sem juros.'),
    ('O valor informado é definitivo?', 'O orçamento final é definido após a avaliação gratuita.'),
    ('A avaliação é gratuita?', 'A avaliação padrão é gratuita.'),
    ('Quero remarcar minha consulta.', ''),
    ('Qual medicamento devo tomar?', ''),
    ('Quero falar com um atendente.', ''),
]
print(json.dumps([dispatch(question, answer) for question, answer in cases]))
`);
  assert.equal(result.length, 11);
  assert.ok(result.every((item) => item.status === 200 && item.scoped));
  assert.deepEqual(result.map((item) => item.action), [
    ...Array(8).fill('SEND_MESSAGE'), 'HANDOFF', 'HANDOFF', 'HANDOFF',
  ]);
  assert.ok(result.slice(0, 8).every((item) => item.model === true && item.modelCalls === 1 && item.grounding === 'PASSED'));
  assert.ok(result.slice(0, 8).every((item) => item.reason === 'GROUNDED_MODEL_RESPONSE' && item.origin === 'MODEL'));
  assert.deepEqual(result.map((item) => item.intent), [
    'ATTRIBUTE_QUERY', 'ATTRIBUTE_QUERY', 'FACTUAL_QUERY', 'ATTRIBUTE_QUERY',
    'FACTUAL_QUERY', 'FACTUAL_QUERY', 'FACTUAL_QUERY', 'FACTUAL_QUERY',
    'SCHEDULING_CONFIRMATION', 'CLINICAL_URGENCY', 'UNKNOWN',
  ]);
  assert.ok(result.slice(0, 8).every((item) => item.promptChunks.length > 0 && item.versions.length > 0 && item.documents.length > 0));
  assert.ok(result.slice(0, 8).every((item) => ['COMPLETE', 'PARTIAL', 'NONE', 'NOT_EVALUATED'].includes(item.coverage)));
  assert.ok(result.slice(0, 8).every((item) => item.commercialEvidencePresent !== false));
  assert.ok(result.slice(0, 8).every((item) => !item.versions.includes('00000000-0000-4000-8000-000000000091')));
  assert.ok([0, 3].every((index) => result[index].promptChunks.includes('00000000-0000-4000-8000-000000000201')
    && result[index].promptChunks.includes('00000000-0000-4000-8000-000000000208')));
  assert.ok(result[4].promptChunks.includes('00000000-0000-4000-8000-000000000208'));
  assert.ok(result[5].promptChunks.includes('00000000-0000-4000-8000-000000000209'));
  assert.ok(result[6].promptChunks.includes('00000000-0000-4000-8000-000000000207'));
  assert.ok(result[7].promptChunks.includes('00000000-0000-4000-8000-000000000210'));
  assert.equal(result[6].budgetPolicyCandidate, true);
  assert.deepEqual(result.slice(8).map((item) => [item.model, item.modelCalls, item.origin, item.grounding]), [
    [false, 0, 'DETERMINISTIC_RULE', 'NOT_RUN'],
    [false, 0, 'DETERMINISTIC_RULE', 'NOT_RUN'],
    [false, 0, 'DETERMINISTIC_RULE', 'NOT_RUN'],
  ]);
  assert.deepEqual(result.slice(8).map((item) => item.reason), [
    'RESCHEDULING_REQUEST', 'MEDICATION_GUIDANCE_REQUIRED', 'PATIENT_REQUESTED_HUMAN',
  ]);
  assert.deepEqual(result[0].topics, ['PRICE', 'SCHEDULING']);
  assert.equal(result[0].coverage, 'COMPLETE');
  assert.equal(result[0].message, 'Botox com revisão em 15 dias custa R$ 750 e o agendamento de avaliação funciona pelo WhatsApp.');
  assert.ok(result.every((item) => !/local-test-service-token|test-only-key|Botox com revisão em 15 dias custa/.test(item.logs)));
});

test('@spec:AC-543 partial, absent, contradictory, draft and foreign facts remain fail closed', () => {
  const result = runPython(fixture + String.raw`
partial = dispatch(QUESTION, 'Botox com revisão em 15 dias custa R$ 750. Qual dia prefere para avaliação?', excluded=[uid(208)])
invented_schedule = dispatch(QUESTION, 'Botox com revisão em 15 dias custa R$ 750 e o agendamento é confirmado automaticamente.', excluded=[uid(208)])
invented_price = dispatch('Quanto custa Botox?', 'Botox com revisão em 15 dias custa R$ 900.')
invented_hours = dispatch('Como funciona o agendamento?', 'O agendamento está disponível amanhã às 10h.')
free_without_source = dispatch('A avaliação é gratuita?', 'A avaliação padrão é gratuita.', excluded=[uid(207), uid(210)])
contradictory = validate_live_grounding('Botox com revisão em 15 dias custa R$ 750.', evidence_count=2,
    evidence=[CHUNKS[0], chunk(11, 1, 'Botox com revisão em 15 dias custa R$ 900.')])['passed']
same_amount = validate_live_grounding('Botox com revisão em 15 dias custa R$ 750.', evidence_count=2,
    evidence=[CHUNKS[0], chunk(12, 1, 'Botox com revisão em 15 dias custa R$ 750,00.')])['passed']
different_offer = validate_live_grounding('Botox com revisão em 15 dias custa R$ 750.', evidence_count=2,
    evidence=[CHUNKS[0], chunk(13, 1, 'Botox por unidade sem revisão custa R$ 75.')])['passed']
different_procedure = validate_live_grounding('Botox com revisão em 15 dias custa R$ 750.', evidence_count=2,
    evidence=[CHUNKS[0], chunk(14, 1, 'Botox capilar com revisão em 15 dias custa R$ 90.')])['passed']
thousand_correct = validate_live_grounding('Botox com revisão em 15 dias custa R$ 1.500,00.', evidence_count=1,
    evidence=[chunk(15, 1, 'Botox com revisão em 15 dias custa R$ 1.500,00.')])['passed']
thousand_wrong = validate_live_grounding('Botox com revisão em 15 dias custa R$ 1.600,00.', evidence_count=1,
    evidence=[chunk(15, 1, 'Botox com revisão em 15 dias custa R$ 1.500,00.')])['passed']
print(json.dumps({'partial': partial, 'inventedSchedule': invented_schedule,
                  'inventedPrice': invented_price, 'inventedHours': invented_hours,
                  'freeWithoutSource': free_without_source,
                  'contradictoryPassed': contradictory, 'sameAmountPassed': same_amount,
                  'differentOfferPassed': different_offer, 'differentProcedurePassed': different_procedure,
                  'thousandCorrect': thousand_correct, 'thousandWrong': thousand_wrong}))
`);
  assert.equal(result.partial.action, 'SEND_MESSAGE');
  assert.equal(result.partial.coverage, 'PARTIAL');
  assert.equal(result.inventedSchedule.action, 'HANDOFF');
  assert.equal(result.inventedSchedule.reason, 'UNSUPPORTED_FACTUAL_CLAIM');
  assert.equal(result.inventedPrice.action, 'HANDOFF');
  assert.equal(result.inventedHours.action, 'HANDOFF');
  assert.equal(result.freeWithoutSource.action, 'HANDOFF');
  assert.equal(result.contradictoryPassed, false);
  assert.equal(result.sameAmountPassed, true);
  assert.equal(result.differentOfferPassed, true);
  assert.equal(result.differentProcedurePassed, true);
  assert.equal(result.thousandCorrect, true);
  assert.equal(result.thousandWrong, false);
  assert.ok([result.partial, result.inventedSchedule, result.inventedPrice,
    result.inventedHours, result.freeWithoutSource]
    .every((item) => item.scoped && !item.versions.includes('00000000-0000-4000-8000-000000000091')));
});

test('@spec:AC-544 a factual grounding rejection gets one evidence-bounded retry and accepts only grounded output', () => {
  const result = runPython(fixture + String.raw`
good = 'Botox com revisão em 15 dias custa R$ 750 e o orçamento final é definido após a avaliação gratuita e o agendamento de avaliação funciona pelo WhatsApp.'
recovered = dispatch(QUESTION, ['Botox com revisão em 15 dias custa R$ 900.', good])
partial = dispatch(QUESTION, ['Botox com revisão em 15 dias custa R$ 750 e o agendamento é confirmado automaticamente.',
                               'Botox com revisão em 15 dias custa R$ 750. Qual dia prefere para avaliação?'], excluded=[uid(208)])
print(json.dumps({'recovered': recovered, 'partial': partial}))
`);
  assert.equal(result.recovered.action, 'SEND_MESSAGE');
  assert.equal(result.recovered.reason, 'EVIDENCE_GROUNDED_REGENERATION_ACCEPTED');
  assert.equal(result.recovered.regenerationMode, 'EVIDENCE_GROUNDED');
  assert.equal(result.recovered.origin, 'FALLBACK');
  assert.equal(result.recovered.modelCalls, 2);
  assert.equal(result.recovered.grounding, 'PASSED');
  assert.equal(result.recovered.groundingPassed, true);
  assert.equal(result.partial.action, 'SEND_MESSAGE');
  assert.equal(result.partial.reason, 'EVIDENCE_GROUNDED_REGENERATION_ACCEPTED');
  assert.equal(result.partial.regenerationMode, 'EVIDENCE_GROUNDED');
  assert.equal(result.partial.coverage, 'PARTIAL');
  assert.equal(result.partial.grounding, 'PASSED');
  assert.ok([result.recovered, result.partial].every((item) => item.scoped && !/R\$ 900|automaticamente|test-only-key|local-test-service-token/.test(item.logs)));
});

test('@spec:AC-545 a second unsupported factual generation ends in HANDOFF with stable grounding reason', () => {
  const result = runPython(fixture + String.raw`
result = dispatch(QUESTION, ['Botox com revisão em 15 dias custa R$ 900.',
                             'Botox com revisão em 15 dias custa R$ 750 e o agendamento está disponível amanhã às 10h.'])
print(json.dumps(result))
`);
  assert.equal(result.action, 'HANDOFF');
  assert.equal(result.origin, 'GROUNDING');
  assert.equal(result.reason, 'UNSUPPORTED_FACTUAL_CLAIM');
  assert.equal(result.regenerationMode, 'EVIDENCE_GROUNDED');
  assert.equal(result.groundingFailureOrigin, 'MODEL_INTRODUCED_UNSUPPORTED_FACT');
  assert.equal(result.grounding, 'FAILED');
  assert.equal(result.groundingPassed, false);
  assert.equal(result.modelCalls, 2);
  assert.equal(result.model, true);
  assert.ok(!/R\$ 900|amanhã às 10h|test-only-key|local-test-service-token/.test(result.logs));
});

test('@spec:AC-546 local grounding diagnostics identify claim index and topic without returning claim text', () => {
  const result = runPython(fixture + String.raw`
from ai_agent_runtime.whatsapp.zapi_server import _grounding_claim_diagnostics
answer = 'Botox com revisão em 15 dias custa R$ 900 e o agendamento de avaliação funciona pelo WhatsApp.'
diagnostics = _grounding_claim_diagnostics(answer, [CHUNKS[0], chunk(12, 1, 'Botox com revisão em 15 dias custa R$ 850.'), CHUNKS[7]])
print(json.dumps(diagnostics))
`);
  assert.deepEqual(result, [
    { claimIndex: 1, topic: 'PRICE', status: 'CONTRADICTED' },
    { claimIndex: 2, topic: 'SCHEDULING', status: 'SUPPORTED' },
  ]);
  assert.ok(result.every((claim) => !Object.hasOwn(claim, 'text')));
});

test('@spec:AC-547 absent candidates and deterministic clinical/human rules never use evidence regeneration', () => {
  const result = runPython(fixture + String.raw`
no_evidence = dispatch('Quanto custa Botox?', ['Botox custa R$ 900.', 'Botox custa R$ 900.'], excluded=[uid(201), uid(202), uid(203), uid(204), uid(205), uid(206), uid(207), uid(208), uid(209), uid(210)])
reschedule = dispatch('Quero remarcar minha consulta.', '')
print(json.dumps({'noEvidence': no_evidence, 'reschedule': reschedule}))
`);
  assert.equal(result.noEvidence.action, 'HANDOFF');
  assert.equal(result.noEvidence.modelCalls, 0);
  assert.equal(result.noEvidence.origin, 'DETERMINISTIC_RULE');
  assert.equal(result.reschedule.action, 'HANDOFF');
  assert.equal(result.reschedule.modelCalls, 0);
  assert.equal(result.reschedule.origin, 'DETERMINISTIC_RULE');
});
