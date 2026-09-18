'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');

function runPython(source) {
  const result = spawnSync('python3', ['-c', source], {
    cwd: process.cwd(), env: { ...process.env, PYTHONPATH: 'src' }, encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return JSON.parse(result.stdout);
}

const fixture = `
import json
from ai_agent_runtime.crm_dispatch import CrmDispatchProcessor, handle_crm_dispatch, StrictCrmOrganizationConfigRepository
from ai_agent_runtime.graph import AgentRuntimeGraph, StaticResponseGenerator
from ai_agent_runtime.organization_config import InMemoryOrganizationConfigRepository, OrganizationRuntimeConfig
from ai_agent_runtime.state import AgentDecision

A = '11111111-1111-4111-8111-111111111111'
B = '22222222-2222-4222-8222-222222222222'
C = '33333333-3333-4333-8333-333333333333'
P = '44444444-4444-4444-8444-444444444444'
M = '55555555-5555-4555-8555-555555555555'
R = '66666666-6666-4666-8666-666666666666'
TOKEN = 'local-test-service-token-000000000000'
event = {'version':'1','correlationId':R,'organizationId':A,'conversationId':C,
         'providerConnectionId':P,'contactId':None,'inboundMessageId':M,'mode':'AI',
         'modeVersion':4,'message':{'type':'text','text':'Quero agendar','timestamp':'2026-09-18T12:00:00Z'},
         'history':[{'role':'contact','text':'Ola','timestamp':'2026-09-18T11:00:00Z'},
                    {'role':'human','text':'Bom dia','timestamp':'2026-09-18T11:05:00Z'}]}
config_repo = InMemoryOrganizationConfigRepository([OrganizationRuntimeConfig(organization_id=A)])
processor = CrmDispatchProcessor(config_repository=config_repo,
    graph_factory=lambda _config: AgentRuntimeGraph(response_generator=StaticResponseGenerator(prefix='Teste')))
def invoke(payload=event, auth='Bearer ' + TOKEN, worker=processor):
    return handle_crm_dispatch(json.dumps(payload).encode(), auth, token=TOKEN, processor=worker)
`;

test('authenticated CRM event runs existing commercial graph and returns strict SEND_MESSAGE', () => {
  const out = runPython(`${fixture}
status, body = invoke()
print(json.dumps({'status':status,'body':body}))`);
  assert.equal(out.status, 200);
  assert.deepEqual(Object.keys(out.body).sort(), [
    'version', 'correlationId', 'organizationId', 'conversationId', 'inboundMessageId',
    'modeVersion', 'action', 'message', 'metadata',
  ].sort());
  assert.equal(out.body.action, 'SEND_MESSAGE');
  assert.equal(out.body.version, '1');
  assert.equal(out.body.modeVersion, 4);
  assert.equal(out.body.message.includes('Quero agendar'), true);
  assert.equal(out.body.metadata && Object.keys(out.body.metadata).length, 0);
});

test('service authentication, schema and unknown/inactive tenant fail closed', () => {
  const out = runPython(`${fixture}
cases = [
    invoke(auth=None), invoke(auth='Bearer wrong'),
    invoke({**event,'token':'forged'}),
    invoke({**event,'organizationId':B}),
    invoke({**event,'modeVersion':'4'}),
    invoke({**event,'history':[{'role':'contact','text':'x','timestamp':'2026-09-18T11:00:00Z','token':'x'}]}),
]
inactive = CrmDispatchProcessor(config_repository=InMemoryOrganizationConfigRepository([
    OrganizationRuntimeConfig(organization_id=A,status='inactive')]), graph_factory=lambda _: None)
cases.append(invoke(worker=inactive))
print(json.dumps(cases))`);
  assert.deepEqual(out.map((item) => item[0]), [401, 401, 400, 503, 400, 400, 503]);
  assert.equal(JSON.stringify(out).includes('Quero agendar'), false);
  assert.equal(JSON.stringify(out).includes('local-test-service-token'), false);
});

test('existing handoff rule returns HANDOFF without sending, explicit no-action stays silent', () => {
  const out = runPython(`${fixture}
handoff = invoke({**event,'message':{**event['message'],'text':'Quero falar com atendente'}})
class NoActionGraph:
    def run(self, state):
        state.context['noAction'] = True
        return state
no_action = CrmDispatchProcessor(config_repository=config_repo,graph_factory=lambda _: NoActionGraph())
silent = invoke(worker=no_action)
print(json.dumps({'handoff':handoff,'silent':silent}))`);
  assert.equal(out.handoff[0], 200);
  assert.equal(out.handoff[1].action, 'HANDOFF');
  assert.equal(Object.hasOwn(out.handoff[1], 'message'), false);
  assert.equal(out.silent[1].action, 'NO_ACTION');
  assert.equal(Object.hasOwn(out.silent[1], 'message'), false);
});

test('strict Supabase config requires active organization plus its own AI config', () => {
  const out = runPython(`${fixture}
class Transport:
    def __init__(self): self.calls=[]
    def get(self,table,query):
        self.calls.append([table,query])
        if query.get('id') == 'eq.' + A and table == 'organizations':
            return [{'id':A,'status':'active','name':'Tenant A'}]
        if query.get('organization_id') == 'eq.' + A and table == 'organization_ai_configs':
            return [{'organization_id':A,'assistant_name':'Test'}]
        return []
transport=Transport()
repo=StrictCrmOrganizationConfigRepository(transport=transport)
configured=repo.get_by_organization_id(A)
missing=repo.get_by_organization_id(B)
print(json.dumps({'configured':configured.organization_id,'missing':missing,'calls':transport.calls}))`);
  assert.equal(out.configured, '11111111-1111-4111-8111-111111111111');
  assert.equal(out.missing, null);
  assert.equal(out.calls.every(([_, query]) => Object.values(query).some((value) =>
    String(value).includes('11111111') || String(value).includes('22222222'))), true);
});

test('commercial playbook receives the selected organization configuration', () => {
  const out = runPython(`${fixture}
class CaptureGraph:
    def run(self, state):
        state.response_text = state.context['organizationConfig']['assistant_name']
        return state
scoped = CrmDispatchProcessor(config_repository=InMemoryOrganizationConfigRepository([
    OrganizationRuntimeConfig(organization_id=A, assistant_name='Tenant A assistant')]),
    graph_factory=lambda _: CaptureGraph())
status, body = invoke(worker=scoped)
print(json.dumps({'status':status,'body':body}))`);
  assert.equal(out.status, 200);
  assert.equal(out.body.action, 'SEND_MESSAGE');
  assert.equal(out.body.message, 'Tenant A assistant');
});

test('new dispatch boundary has no WhatsApp provider, CRM writes or plaintext token plumbing', () => {
  const source = readFileSync(join(process.cwd(), 'src/ai_agent_runtime/crm_dispatch.py'), 'utf8');
  assert.doesNotMatch(source, /build_whatsapp_provider\(|send_text\(|send_message\(|ai_messages|whatsapp_messages|create_outbound_message\(/);
  assert.match(source, /hmac\.compare_digest/);
  assert.match(source, /OpenAIWhatsAppResponseGenerator/);
  assert.match(source, /AgentRuntimeGraph/);
});
