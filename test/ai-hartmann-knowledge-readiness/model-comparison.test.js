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

test('@spec:AC-551 model override is tenant-scoped and removing it rolls back', () => {
  const result = python(String.raw`
import json, os
from ai_agent_runtime.crm_dispatch import _default_graph, _model_settings_for_organization
from ai_agent_runtime.organization_config import OrganizationRuntimeConfig
hartmann = '38002ccb-9edb-4dcb-aacf-76c0b6ca1692'
other = '11111111-1111-4111-8111-111111111111'
os.environ['OPENAI_RESPONSES_MODEL'] = 'gpt-5.6-luna'
os.environ['OPENAI_REASONING_EFFORT'] = 'low'
os.environ.pop('OPENAI_MAX_OUTPUT_TOKENS', None)
os.environ['OPENAI_MODEL_OVERRIDES_JSON'] = json.dumps({hartmann:{
    'model':'gpt-6-luna','reasoningEffort':'medium','maxOutputTokens':4096}})
selected = _model_settings_for_organization(hartmann)
untouched = _model_settings_for_organization(other)
graph = _default_graph(OrganizationRuntimeConfig(organization_id=hartmann, source='env'), logger=lambda *_: None)
graph_config = graph.response_generator.provider.config
os.environ.pop('OPENAI_MODEL_OVERRIDES_JSON')
rollback = _model_settings_for_organization(hartmann)
os.environ['OPENAI_MODEL_OVERRIDES_JSON'] = json.dumps({hartmann:{
    'model':'gpt-6-luna','reasoningEffort':'minimal'}})
try:
    _model_settings_for_organization(hartmann)
except RuntimeError as exc:
    invalid = str(exc)
print(json.dumps({'selected':selected,'untouched':untouched,'rollback':rollback,'invalid':invalid,
                  'graph':[graph_config.openai_responses_model,graph_config.openai_reasoning_effort,
                           graph_config.openai_max_output_tokens]}))
`);
  assert.deepEqual(result.selected, ['gpt-6-luna', 'medium', 4096]);
  assert.deepEqual(result.graph, result.selected);
  assert.deepEqual(result.untouched, ['gpt-5.6-luna', 'low', null]);
  assert.deepEqual(result.rollback, result.untouched);
  assert.equal(result.invalid, 'OPENAI_MODEL_OVERRIDES_INVALID');
});

test('@spec:AC-552 GPT-6 Luna Responses payload and errors fail closed', () => {
  const result = python(String.raw`
import json
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider, OpenAIProviderError
from ai_agent_runtime.whatsapp.zapi_server import _extract_response_text
class Transport:
    def __init__(self, response): self.response, self.calls = response, []
    def post_json(self, url, *, headers, payload):
        self.calls.append({'url':url,'payload':payload,'auth':bool(headers.get('Authorization'))})
        return self.response
config = IntegrationConfig(openai_api_key='mock', openai_responses_model='gpt-6-luna',
                           openai_reasoning_effort='medium', openai_max_output_tokens=4096)
transport = Transport({'status':'completed','model':'gpt-6-luna',
                       'output':[{'type':'message','content':[{'type':'output_text','text':'Resposta segura.'}]}],
                       'usage':{'input_tokens':100,'output_tokens':50}})
provider = OpenAIResponsesProvider(config, transport)
response = provider.create_response(input_messages=[{'role':'user','content':'Oi'}])
for name, bad_config in [('effort', IntegrationConfig(openai_api_key='mock',openai_responses_model='gpt-6-luna',openai_reasoning_effort='minimal')),
                         ('limit', IntegrationConfig(openai_api_key='mock',openai_responses_model='gpt-6-luna',openai_max_output_tokens=128001))]:
    try: OpenAIResponsesProvider(bad_config, transport).create_response(input_messages=[])
    except OpenAIProviderError as exc: globals()[name] = str(exc)
transport.response = {'status':'incomplete','incomplete_details':{'reason':'max_output_tokens'}}
try: provider.create_response(input_messages=[])
except OpenAIProviderError as exc: incomplete = str(exc)
transport.response = {'status':'failed','error':{'message':'secret response body'}}
try: provider.create_response(input_messages=[])
except OpenAIProviderError as exc: failed = str(exc)
print(json.dumps({'call':transport.calls[0],'text':_extract_response_text(response),
                  'usage':response['usage'],'effort':effort,'limit':limit,
                  'incomplete':incomplete,'failed':failed,'calls':len(transport.calls)}))
`);
  assert.equal(result.call.url, 'https://api.openai.com/v1/responses');
  assert.equal(result.call.payload.model, 'gpt-6-luna');
  assert.equal(result.call.payload.reasoning.effort, 'medium');
  assert.equal(result.call.payload.max_output_tokens, 4096);
  assert.equal(result.call.payload.store, false);
  assert.equal(result.text, 'Resposta segura.');
  assert.deepEqual(result.usage, { input_tokens: 100, output_tokens: 50 });
  assert.equal(result.effort, 'OPENAI_REASONING_EFFORT_INVALID');
  assert.equal(result.limit, 'OPENAI_MAX_OUTPUT_TOKENS_INVALID');
  assert.equal(result.incomplete, 'OPENAI_RESPONSE_INCOMPLETE');
  assert.equal(result.failed, 'OPENAI_RESPONSE_FAILED');
  assert.equal(result.calls, 3);
});

test('@spec:AC-553 ten paired mock scenarios report quality, handoff, invention, booking, latency, tokens and cost', () => {
  const result = python(String.raw`
import json
from decimal import Decimal
from ai_agent_runtime.evaluation.model_comparison import compare_model_observations
scenarios = [
 'Quanto custa Botox?', 'Como faço para agendar?',
 'Quanto custa Botox e como faço para agendar?', 'Posso parcelar?',
 'Vocês fazem preenchimento de glúteo?', 'Qual horário vocês têm amanhã?',
 'Quero falar com uma pessoa.', 'Preciso de uma orientação sobre medicamento.',
 'Pergunta comercial com apenas parte da informação disponível.',
 'Pergunta sobre tratamento ausente da base.',
]
rows = []
for model in ('gpt-5.1','gpt-6-luna'):
    for index, scenario in enumerate(scenarios):
        rows.append({'model':model,'scenario':scenario,'conversationQuality':1.0,
                     'commercialAccuracy':1.0,'handoff':index in (4,5,6,7,9),
                     'inventedFact':False,'bookingProgress':index in (1,2,8),
                     'latencyMs':100,'inputTokens':1000,'outputTokens':200})
report = compare_model_observations(rows, usd_per_million_tokens={
    'gpt-5.1':(Decimal('1.25'),Decimal('10.00')),
    'gpt-6-luna':(Decimal('0.10'),Decimal('0.50'))})
try: compare_model_observations(rows[:-1], usd_per_million_tokens={
    'gpt-5.1':(Decimal('1.25'),Decimal('10.00')),
    'gpt-6-luna':(Decimal('0.10'),Decimal('0.50'))})
except ValueError as exc: unpaired = str(exc)
print(json.dumps({'report':report,'unpaired':unpaired}))
`);
  for (const model of ['gpt-5.1', 'gpt-6-luna']) {
    assert.equal(result.report[model].scenarios, 10);
    assert.equal(result.report[model].conversationQuality, 1);
    assert.equal(result.report[model].commercialAccuracy, 1);
    assert.equal(result.report[model].handoffRate, 0.5);
    assert.equal(result.report[model].inventedFactRate, 0);
    assert.equal(result.report[model].bookingProgressRate, 0.3);
    assert.equal(result.report[model].meanLatencyMs, 100);
    assert.equal(result.report[model].inputTokens, 10000);
    assert.equal(result.report[model].outputTokens, 2000);
  }
  assert.ok(Number(result.report['gpt-6-luna'].estimatedCostUsd)
    < Number(result.report['gpt-5.1'].estimatedCostUsd));
  assert.equal(result.unpaired, 'MODEL_COMPARISON_UNPAIRED_SCENARIOS');
});
