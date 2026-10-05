'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { readFileSync } = require('node:fs');

function python(source, env = {}) {
  const result = spawnSync('python3', ['-c', source], {
    cwd: process.cwd(), env: { ...process.env, PYTHONPATH: 'src', ...env }, encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return JSON.parse(result.stdout);
}

const fixture = `
import json
from ai_agent_runtime.crm_dispatch import StrictCrmOrganizationConfigRepository
A='11111111-1111-4111-8111-111111111111'
B='22222222-2222-4222-8222-222222222222'
C='33333333-3333-4333-8333-333333333333'
P='44444444-4444-4444-8444-444444444444'
M='55555555-5555-4555-8555-555555555555'
R='66666666-6666-4666-8666-666666666666'
T='77777777-7777-4777-8777-777777777777'
class Transport:
    def __init__(self):
        self.orgs={A:{'id':A,'name':'Clinic A','status':'active'}}
        self.configs={A:{'organization_id':A,'status':'active','assistant_name':'Assistant A','assistant_role':'Reception A','clinic_name':'Clinic A','doctor_name':'Doctor A'}}
        self.calls=[]
        self.error=False
    def get(self,table,query):
        self.calls.append((table,dict(query)))
        if self.error: raise RuntimeError('unavailable')
        ident=query.get('id',query.get('organization_id','')).removeprefix('eq.')
        row=(self.orgs if table=='organizations' else self.configs).get(ident)
        return [row] if row else []
transport=Transport()
env_json=json.dumps({B:{'assistant_name':'Env B'},A:{'assistant_name':'Forged A'}})
`;

test('@spec:AC-485 @spec:AC-486 @spec:AC-491 explicit source controls precedence and never masks inactive/config/network errors', () => {
  const out = python(`${fixture}
sup=StrictCrmOrganizationConfigRepository(transport=transport,environment_json=env_json,source='supabase')
hybrid=StrictCrmOrganizationConfigRepository(transport=transport,environment_json=env_json,source='hybrid')
env=StrictCrmOrganizationConfigRepository(transport=transport,environment_json=env_json,source='env')
results={'sup_a':sup.get_by_organization_id(A).assistant_name,
 'sup_b':sup.get_by_organization_id(B),
 'hybrid_a':hybrid.get_by_organization_id(A).assistant_name,
 'hybrid_b':hybrid.get_by_organization_id(B).assistant_name,
 'env_a':env.get_by_organization_id(A).assistant_name}
transport.orgs[A]['status']='inactive'
results['inactive']=hybrid.get_by_organization_id(A)
transport.orgs[A]['status']='active'
transport.configs.pop(A)
results['no_config']=hybrid.get_by_organization_id(A)
transport.configs[A]={'organization_id':A,'status':'inactive','assistant_name':'Assistant A'}
results['config_inactive']=hybrid.get_by_organization_id(A)
transport.error=True
try: hybrid.get_by_organization_id(B)
except RuntimeError: results['network']='rejected'
try: StrictCrmOrganizationConfigRepository(source='typo')
except ValueError: results['source']='rejected'
print(json.dumps(results))`);
  assert.deepEqual(out, { sup_a: 'Assistant A', sup_b: null, hybrid_a: 'Assistant A',
    hybrid_b: 'Env B', env_a: 'Forged A', inactive: null, no_config: null,
    config_inactive: null, network: 'rejected', source: 'rejected' });
});

test('@spec:AC-485 @spec:AC-491 default CRM source fails closed without Supabase, while env rollback is explicit', () => {
  const out = python(`${fixture}
import os
for key in ('SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','ORGANIZATION_CONFIG_SOURCE'):
    os.environ.pop(key,None)
os.environ['ORGANIZATION_RUNTIME_CONFIG_JSON']=env_json
default=StrictCrmOrganizationConfigRepository.from_environment()
try: default.get_by_organization_id(A)
except RuntimeError: default_result='rejected'
os.environ['ORGANIZATION_CONFIG_SOURCE']='env'
rollback=StrictCrmOrganizationConfigRepository.from_environment()
print(json.dumps({'default_source':default.source,'default_result':default_result,
                  'rollback_source':rollback.source,'rollback_name':rollback.get_by_organization_id(A).assistant_name}))`);
  assert.deepEqual(out, { default_source: 'supabase', default_result: 'rejected',
    rollback_source: 'env', rollback_name: 'Forged A' });
});

test('@spec:AC-487 @spec:AC-490 @spec:AC-492 Vault provider scopes refs to each organization and rejects ambiguity or missing secrets', () => {
  const out = python(`${fixture}
from ai_agent_runtime.organization_config import SupabaseVaultCredentialProvider, OrganizationCredentialError
refs={A:'vault:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',B:'vault:bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',C:'vault:cccccccc-cccc-4ccc-8ccc-cccccccccccc'}
secrets={A:'fake-secret-a',B:'fake-secret-b',C:'fake-secret-c'}
class VaultTransport:
    def __init__(self): self.calls=[]; self.fail=False; self.ambiguous=False; self.cross=False
    def request_json(self,method,path,*,payload):
        self.calls.append((method,path,payload))
        if self.fail: raise RuntimeError('vault-down')
        org=payload['p_organization_id']
        rows=[{'organization_id':org,'credential_ref':refs[org],'secret':secrets[org]}] if org in refs else []
        if self.cross and rows: rows[0]['organization_id']=B
        return rows*2 if self.ambiguous else rows
vault=VaultTransport(); provider=SupabaseVaultCredentialProvider(transport=vault)
before=provider.get_credential(A,'OPENAI').safe_dict()
# B is onboarded in the backing store without changing process env or code.
selected={org:provider.get_credential(org,'OPENAI').secret for org in (A,B,C)}
missing=provider.get_credential(P,'OPENAI')
vault.ambiguous=True
try: provider.get_credential(A,'OPENAI')
except OrganizationCredentialError: ambiguous='rejected'
vault.ambiguous=False; vault.fail=True
try: provider.get_credential(A,'OPENAI')
except RuntimeError: unavailable='rejected'
vault.fail=False; vault.cross=True
try: provider.get_credential(A,'OPENAI')
except OrganizationCredentialError: cross='rejected'
print(json.dumps({'before':before,'selected':selected,'missing':missing,
 'ambiguous':ambiguous,'unavailable':unavailable,'cross':cross,'calls':vault.calls}))`);
  assert.deepEqual(Object.values(out.selected), ['fake-secret-a', 'fake-secret-b', 'fake-secret-c']);
  assert.equal(out.missing, null);
  assert.equal(out.ambiguous, 'rejected');
  assert.equal(out.unavailable, 'rejected');
  assert.equal(out.cross, 'rejected');
  assert.ok(out.calls.every(([method, path, payload]) => method === 'POST' &&
    path === 'rpc/resolve_organization_openai_credential' && Object.keys(payload).join() === 'p_organization_id'));
  assert.doesNotMatch(JSON.stringify(out.before), /fake-secret/);
});

test('@spec:AC-487 @spec:AC-488 Supabase graph chooses Vault over global OpenAI and ZAPI envs', () => {
  const out = python(`${fixture}
import os
import ai_agent_runtime.crm_dispatch as dispatch
from ai_agent_runtime.organization_config import OrganizationRuntimeConfig
class VaultTransport:
    def __init__(self,*,supabase_url,service_role_key): pass
    def request_json(self,method,path,*,payload):
        return [{'organization_id':payload['p_organization_id'],
                 'credential_ref':'vault:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
                 'secret':'vault-only-key'}]
dispatch.SupabaseOrganizationTransport=VaultTransport
os.environ['SUPABASE_URL']='https://fake.supabase.co'
os.environ['SUPABASE_SERVICE_ROLE_KEY']='local-fake-role'
os.environ['OPENAI_API_KEY']='wrong-global-key'
os.environ['ZAPI_INSTANCE_ID']='wrong-tenant'
os.environ['ZAPI_INSTANCE_ORGANIZATION_MAP_JSON']=json.dumps({'wrong-tenant':B})
os.environ['ORGANIZATION_CREDENTIALS_JSON']=json.dumps({A:{'OPENAI':{'credential_ref':'OPENAI_API_KEY'}}})
logs=[]
graph=dispatch._default_graph(OrganizationRuntimeConfig(organization_id=A,source='supabase'),
 logger=lambda event,fields: logs.append((event,fields)))
credential=graph.response_generator.credential_provider.get_credential(A,'OPENAI')
print(json.dumps({'secret':credential.secret,'ref':credential.credential_ref,'logs':logs}))`);
  assert.equal(out.secret, 'vault-only-key');
  assert.equal(out.ref, 'vault:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa');
  assert.doesNotMatch(JSON.stringify(out.logs), /vault-only-key|wrong-global-key|wrong-tenant/);
  assert.deepEqual(out.logs.map(([event]) => event), ['organization_credential_resolved']);
});

test('@spec:AC-487 @spec:AC-488 canonical dispatch rejects a missing Vault credential before any graph response', () => {
  const out = python(`${fixture}
import os
import ai_agent_runtime.crm_dispatch as dispatch
from ai_agent_runtime.crm_dispatch import CrmDispatchProcessor, handle_crm_dispatch
class EmptyVault:
    def __init__(self,*,supabase_url,service_role_key): pass
    def request_json(self,method,path,*,payload): return []
dispatch.SupabaseOrganizationTransport=EmptyVault
os.environ['SUPABASE_URL']='https://fake.supabase.co'
os.environ['SUPABASE_SERVICE_ROLE_KEY']='local-fake-role'
repo=StrictCrmOrganizationConfigRepository(transport=transport,source='supabase')
events=[]
processor=CrmDispatchProcessor(config_repository=repo,logger=lambda event,fields: events.append((event,fields)))
payload={'version':'1','correlationId':R,'organizationId':A,'conversationId':P,
 'providerConnectionId':P,'contactId':None,'inboundMessageId':M,'mode':'AI','modeVersion':1,
 'message':{'type':'text','text':'Ola','timestamp':'2026-09-29T12:00:00Z'}}
status,body=handle_crm_dispatch(json.dumps(payload).encode(),'Bearer '+'x'*32,
 token='x'*32,processor=processor)
print(json.dumps({'status':status,'body':body,'events':events}))`);
  assert.deepEqual([out.status, out.body], [503, { error: 'RUNTIME_UNAVAILABLE' }]);
  assert.ok(out.events.some(([event, fields]) => event === 'organization_runtime_rejected' &&
    fields.reason === 'EXECUTION_FAILED'));
});

test('@spec:AC-488 @spec:AC-489 @spec:AC-490 three concurrent CRM dispatches keep config and graph memory isolated without env changes', () => {
  const out = python(`${fixture}
from concurrent.futures import ThreadPoolExecutor
from ai_agent_runtime.crm_dispatch import CrmDispatchProcessor, handle_crm_dispatch
from ai_agent_runtime.state import AgentDecision
from ai_agent_runtime.organization_config import SupabaseVaultCredentialProvider
from ai_agent_runtime.whatsapp.zapi_server import ZApiRuntimeRetrieval
# No A/B/C config exists in the process environment for this scale test.
repo=StrictCrmOrganizationConfigRepository(transport=transport,environment_json='{}',source='supabase')
logs=[]
refs={A:'vault:'+A}
published={A}
class VaultTransport:
    def request_json(self,method,path,*,payload):
        org=payload['p_organization_id']
        return [{'organization_id':org,'credential_ref':refs[org],'secret':'fake-'+org}]
credentials=SupabaseVaultCredentialProvider(transport=VaultTransport())
class Retrieval(ZApiRuntimeRetrieval):
    def __init__(self): pass
    def _get_json(self,table,params,*,endpoint):
        org=params['organization_id'].removeprefix('eq.')
        if org not in published: return []
        if table=='document_versions':
            return [{'id':'version-'+org,'organization_id':org,'document_id':'doc-'+org,'version_number':1,'status':'PUBLISHED','processing_valid':True}]
        return [{'id':'chunk-'+org,'organization_id':org,'document_id':'doc-'+org,'document_version_id':'version-'+org,'content':'KB '+org}]
retrieval=Retrieval()
class CaptureGraph:
    def run(self,state):
        state.context['privateMemory']=state.organization_id
        credential=credentials.get_credential(state.organization_id,'OPENAI')
        evidence=retrieval.search(state.organization_id,'unique')
        state.response_text='|'.join((state.context['organizationConfig']['assistant_name'],
          state.context['privateMemory'],credential.credential_ref,evidence[0]['content'],
          state.messages[0]['text']))
        state.decision=AgentDecision.CONTINUE
        return state
processor=CrmDispatchProcessor(config_repository=repo,graph_factory=lambda _: CaptureGraph(),
 logger=lambda event,fields: logs.append((event,fields)))
def dispatch(org):
    payload={'version':'2','correlationId':R,'organizationId':org,'conversationId':P,
      'providerConnectionId':P,'contactId':None,'inboundMessageId':M,'logicalTurnId':T,
      'constituentMessageIds':[M],'latestInboundCreatedAt':'2026-09-29T12:00:00Z',
      'mode':'AI','modeVersion':2,'message':{'type':'text','text':'same phone 5511999999999','timestamp':'2026-09-29T12:00:00Z'},
      'history':[{'role':'contact','text':'memory '+org,'timestamp':'2026-09-29T11:00:00Z'}]}
    return handle_crm_dispatch(json.dumps(payload).encode(),'Bearer '+'x'*32,token='x'*32,processor=processor)
before=dispatch(A)
# Register B/C in the backing store after the processor already served A.
for org,name in ((B,'Assistant B'),(C,'Assistant C')):
    transport.orgs[org]={'id':org,'name':name,'status':'active'}
    transport.configs[org]={'organization_id':org,'status':'active','assistant_name':name,'assistant_role':'Reception'}
    refs[org]='vault:'+org
    published.add(org)
with ThreadPoolExecutor(max_workers=3) as pool: result=list(pool.map(dispatch,(A,B,C)))
print(json.dumps({'before':before,'result':result,'logs':logs}))`);
  assert.equal(out.before[0], 200);
  assert.deepEqual(out.result.map(([status]) => status), [200, 200, 200]);
  for (const [index, org] of ['11111111-1111-4111-8111-111111111111',
    '22222222-2222-4222-8222-222222222222', '33333333-3333-4333-8333-333333333333'].entries()) {
    assert.deepEqual(out.result[index][1].message.split('|'),
      [`Assistant ${'ABC'[index]}`, org, `vault:${org}`, `KB ${org}`, `memory ${org}`]);
  }
  assert.ok(out.logs.filter(([event]) => event === 'organization_config_source_resolved').every(([, fields]) => fields.source === 'supabase'));
  assert.doesNotMatch(JSON.stringify(out.logs), /same phone|fake-secret/);
});

test('@spec:AC-489 RAG filters three organizations and excludes draft, invalid and foreign chunks', () => {
  const out = python(`${fixture}
from ai_agent_runtime.whatsapp.zapi_server import ZApiRuntimeRetrieval
class Retrieval(ZApiRuntimeRetrieval):
    def __init__(self): self.calls=[]
    def _get_json(self,table,params,*,endpoint):
        self.calls.append((table,dict(params)))
        org=params['organization_id'].removeprefix('eq.')
        if table=='document_versions':
            return [{'id':'published-'+org,'organization_id':org,'document_id':'doc-'+org,'version_number':1,'status':'PUBLISHED','processing_valid':True},
                    {'id':'draft-'+org,'organization_id':org,'document_id':'draft-doc-'+org,'version_number':1,'status':'DRAFT','processing_valid':True},
                    {'id':'expired-'+org,'organization_id':org,'document_id':'expired-doc-'+org,'version_number':1,'status':'PUBLISHED','processing_valid':True,'effective_until':'2000-01-01T00:00:00Z'},
                    {'id':'future-'+org,'organization_id':org,'document_id':'future-doc-'+org,'version_number':1,'status':'PUBLISHED','processing_valid':True,'effective_from':'2999-01-01T00:00:00Z'},
                    {'id':'invalid-'+org,'organization_id':org,'document_id':'invalid-doc-'+org,'version_number':1,'status':'PUBLISHED','processing_valid':False},
                    {'id':'foreign','organization_id':A if org!=A else B,'document_id':'foreign-doc','version_number':1,'status':'PUBLISHED','processing_valid':True}]
        return [{'id':'chunk-'+org,'organization_id':org,'document_id':'doc-'+org,'document_version_id':'published-'+org,'content':'unique '+org},
                {'id':'draft','organization_id':org,'document_id':'draft-doc-'+org,'document_version_id':'draft-'+org,'content':'draft'},
                {'id':'expired','organization_id':org,'document_id':'expired-doc-'+org,'document_version_id':'expired-'+org,'content':'old'},
                {'id':'future','organization_id':org,'document_id':'future-doc-'+org,'document_version_id':'future-'+org,'content':'not yet'},
                {'id':'invalid','organization_id':org,'document_id':'invalid-doc-'+org,'document_version_id':'invalid-'+org,'content':'invalid'},
                {'id':'foreign','organization_id':A if org!=A else B,'document_id':'foreign-doc','document_version_id':'foreign','content':'foreign'}]
retrieval=Retrieval()
hits={org:retrieval.search(org,'unique') for org in (A,B,C)}
print(json.dumps({'hits':hits,'calls':retrieval.calls}))`);
  for (const [org, rows] of Object.entries(out.hits)) {
    assert.equal(rows.length, 1);
    assert.equal(rows[0].organization_id, org);
    assert.equal(rows[0].content, `unique ${org}`);
  }
  assert.ok(out.calls.every(([, params]) => /^eq\.[0-9a-f-]{36}$/.test(params.organization_id)));
});

test('@spec:AC-487 @spec:AC-492 @spec:AC-493 migration restricts Vault RPC to service_role and keeps old adapter source untouched', () => {
  const sql = readFileSync('supabase/migrations/202609290001_ai_organization_openai_vault.sql', 'utf8');
  assert.match(sql, /security definer\s+set search_path = ''/i);
  assert.match(sql, /c\.organization_id = p_organization_id/);
  assert.match(sql, /select c\.organization_id, c\.credential_ref, v\.decrypted_secret/);
  assert.match(sql, /c\.provider = 'OPENAI'/);
  assert.match(sql, /c\.status = 'active'/);
  assert.match(sql, /v\.name = 'openai:' \|\| p_organization_id::text/);
  assert.match(sql, /vault\.decrypted_secrets/);
  assert.match(sql, /revoke all on function[\s\S]+from public, anon, authenticated/);
  assert.match(sql, /grant execute on function[\s\S]+to service_role/);
  assert.doesNotMatch(sql, /alter table public\.organization_credentials add column.*secret/i);
});
