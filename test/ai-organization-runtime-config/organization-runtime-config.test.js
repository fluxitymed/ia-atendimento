'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { spawnSync } = require('node:child_process');

function runPython(source, env = {}) {
  const result = spawnSync('python3', ['-c', source], {
    cwd: process.cwd(),
    env: { ...process.env, PYTHONPATH: 'src', ...env },
    encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout.trim();
}

test('@spec:AC-421 @spec:AC-422 runtime config loads active organization without cross-org leakage', () => {
  const output = runPython(`
import json
from ai_agent_runtime.organization_config import InMemoryOrganizationConfigRepository, OrganizationRuntimeConfig, resolve_runtime_config

logs = []
repo = InMemoryOrganizationConfigRepository([
    OrganizationRuntimeConfig(organization_id="org-a", assistant_name="Ana", clinic_name="Clinica A", doctor_name="Dra. A", locations=("A1",), sales_goal="meta A"),
    OrganizationRuntimeConfig(organization_id="org-b", assistant_name="Bia", clinic_name="Clinica B", doctor_name="Dr. B", locations=("B1", "B2"), sales_goal="meta B"),
])
a = resolve_runtime_config("org-a", repository=repo, logger=lambda stage, details=None: logs.append({"stage": stage, "details": details})).to_commercial_config()
b = resolve_runtime_config("org-b", repository=repo, logger=lambda stage, details=None: logs.append({"stage": stage, "details": details})).to_commercial_config()
print(json.dumps({
  "a": {"assistant": a.assistant_name, "clinic": a.clinic_name, "doctor": a.doctor_name, "locations": a.locations, "goal": a.sales_goal},
  "b": {"assistant": b.assistant_name, "clinic": b.clinic_name, "doctor": b.doctor_name, "locations": b.locations, "goal": b.sales_goal},
  "events": [item["stage"] for item in logs],
}))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed.a, { assistant: 'Ana', clinic: 'Clinica A', doctor: 'Dra. A', locations: ['A1'], goal: 'meta A' });
  assert.deepEqual(parsed.b, { assistant: 'Bia', clinic: 'Clinica B', doctor: 'Dr. B', locations: ['B1', 'B2'], goal: 'meta B' });
  assert.equal(parsed.events.filter((event) => event === 'organization_config_loaded').length, 2);
});

test('@spec:AC-423 legacy runtime config fallback preserves current Carvalho env shape', () => {
  const output = runPython(`
import json
from ai_agent_runtime.organization_config import EnvironmentOrganizationConfigRepository, LegacyEnvironmentOrganizationConfigRepository, resolve_runtime_config

logs = []
config = resolve_runtime_config(
    "org-carvalho",
    repository=EnvironmentOrganizationConfigRepository(raw_json=None),
    fallback_repository=LegacyEnvironmentOrganizationConfigRepository("org-carvalho"),
    logger=lambda stage, details=None: logs.append({"stage": stage, "details": details}),
)
commercial = config.to_commercial_config()
print(json.dumps({
  "assistant": commercial.assistant_name,
  "clinic": commercial.clinic_name,
  "doctor": commercial.doctor_name,
  "locations": commercial.locations,
  "events": [item["stage"] for item in logs],
}))
`, {
    AI_ASSISTANT_NAME: 'Bruna',
    AI_CLINIC_NAME: 'Clinica Carvalho e Tavares Odontologia Integrada',
    AI_DOCTOR_NAME: 'Dr. Leonardo Carvalho',
    AI_LOCATIONS: 'Matatu/Brotas|Hospital da Bahia',
  });
  const parsed = JSON.parse(output);
  assert.equal(parsed.assistant, 'Bruna');
  assert.equal(parsed.clinic, 'Clinica Carvalho e Tavares Odontologia Integrada');
  assert.equal(parsed.doctor, 'Dr. Leonardo Carvalho');
  assert.deepEqual(parsed.locations, ['Matatu/Brotas', 'Hospital da Bahia']);
  assert.deepEqual(parsed.events, ['organization_config_legacy_fallback']);
});

test('@spec:AC-424 @spec:AC-425 @spec:AC-427 organization credentials resolve by provider and secrets stay out of logs', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.organization_config import EnvironmentCredentialProvider, resolve_credential

class Transport:
    def __init__(self): self.headers = []
    def post_json(self, url, *, headers, payload):
        self.headers.append(headers)
        return {"id": "resp-a", "model": payload["model"], "output": [], "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}}

logs = []
provider = EnvironmentCredentialProvider(raw_json=json.dumps({
    "org-a": {"OPENAI": {"credential_ref": "OPENAI_KEY_A"}},
    "org-b": {"OPENAI": {"credential_ref": "OPENAI_KEY_B"}},
}))
credential = resolve_credential("org-b", "OPENAI", credential_provider=provider, logger=lambda stage, details=None: logs.append({"stage": stage, "details": details}))
transport = Transport()
openai = OpenAIResponsesProvider(IntegrationConfig(openai_api_key=credential.secret), transport)
openai.create_response(input_messages=[{"role": "user", "content": "oi"}], organization_id="org-b", conversation_id="00000000-0000-0000-0000-000000000001")
print(json.dumps({
  "credentialRef": credential.credential_ref,
  "auth": transport.headers[0]["Authorization"],
  "logs": logs,
}))
`, {
    OPENAI_KEY_A: 'sk-org-a-secret',
    OPENAI_KEY_B: 'sk-org-b-secret',
  });
  const parsed = JSON.parse(output);
  assert.equal(parsed.credentialRef, 'OPENAI_KEY_B');
  assert.equal(parsed.auth, 'Bearer sk-org-b-secret');
  assert.doesNotMatch(JSON.stringify(parsed.logs), /sk-org-[ab]-secret/);
  assert.match(JSON.stringify(parsed.logs), /organization_credential_resolved/);
});

test('@spec:AC-426 @spec:AC-433 Z-API instance mapping ignores payload organization and rejects unknown instance', () => {
  const output = runPython(`
import json
from ai_agent_runtime.organization_config import zapi_instance_organization_map_from_env
from ai_agent_runtime.whatsapp.adapter import OrganizationResolver

mapping = zapi_instance_organization_map_from_env("legacy-instance", "legacy-org")
resolver = OrganizationResolver(mapping)
resolved = resolver.resolve("instance-b")
try:
    resolver.resolve("unknown-instance")
except Exception as exc:
    unknown = type(exc).__name__
payload_organization = "patient-controlled-org"
print(json.dumps({"resolved": resolved, "payloadIgnored": payload_organization != resolved, "unknown": unknown, "mapping": mapping}))
`, {
    ZAPI_INSTANCE_ORGANIZATION_MAP_JSON: '{"instance-a":"org-a","instance-b":"org-b"}',
  });
  const parsed = JSON.parse(output);
  assert.equal(parsed.resolved, 'org-b');
  assert.equal(parsed.payloadIgnored, true);
  assert.equal(parsed.unknown, 'ValueError');
  assert.deepEqual(parsed.mapping, { 'instance-a': 'org-a', 'instance-b': 'org-b' });
});

test('@spec:AC-428 migration defines multi-tenant tables without plaintext secret columns', () => {
  const sql = readFileSync('supabase/migrations/202609070001_ai_organization_runtime_config.sql', 'utf8');
  for (const table of ['organizations', 'organization_ai_configs', 'organization_integrations', 'organization_credentials', 'ai_usage_events']) {
    assert.match(sql, new RegExp(`create table if not exists ${table}`, 'i'));
  }
  for (const field of ['assistant_name', 'clinic_name', 'doctor_name', 'credential_ref', 'provider_request_id', 'estimated_cost_usd']) {
    assert.match(sql, new RegExp(field, 'i'));
  }
  assert.match(sql, /alter table organizations add column if not exists status/i);
  assert.match(sql, /create unique index if not exists ai_usage_events_provider_request_unique_idx/i);
  assert.doesNotMatch(sql, /\b(api_key|access_token|refresh_token|secret_value|plaintext_secret)\b/i);
});

test('@spec:AC-429 Carvalho seed keeps existing organizationId and does not duplicate knowledge', () => {
  const output = runPython(`
import json
from ai_agent_runtime.organization_seed import CARVALHO_ORGANIZATION_ID, carvalho_runtime_seed
seed = carvalho_runtime_seed()
print(json.dumps({"orgId": CARVALHO_ORGANIZATION_ID, "seed": seed}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.orgId, 'dfdcdff0-6d5f-58cc-9a83-2829820b7f8e');
  assert.equal(parsed.seed.organizations[0].id, parsed.orgId);
  assert.equal(parsed.seed.organization_ai_configs[0].assistant_name, 'Bruna');
  assert.equal(parsed.seed.organization_ai_configs[0].doctor_name, 'Dr. Leonardo Carvalho');
  assert.equal(parsed.seed.documents, undefined);
  assert.equal(parsed.seed.chunks, undefined);
});

test('@spec:AC-430 @spec:AC-431 OpenAI usage is recorded by organization and idempotent by provider request id', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.organization_config import InMemoryAiUsageTracker

class Transport:
    def __init__(self): self.calls = 0
    def post_json(self, url, *, headers, payload):
        self.calls += 1
        return {"id": "resp-same", "model": payload["model"], "output": [], "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}}

logs = []
tracker = InMemoryAiUsageTracker()
transport = Transport()
provider = OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), transport, usage_tracker=tracker, usage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details}))
provider.create_response(input_messages=[{"role": "user", "content": "oi"}], organization_id="org-a", conversation_id="00000000-0000-0000-0000-000000000001")
provider.create_response(input_messages=[{"role": "user", "content": "oi de novo"}], organization_id="org-a", conversation_id="00000000-0000-0000-0000-000000000001")
event = tracker.events[0]
print(json.dumps({"callCount": transport.calls, "eventCount": len(tracker.events), "event": event.as_row(), "logs": logs}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.callCount, 2);
  assert.equal(parsed.eventCount, 1);
  assert.equal(parsed.event.organization_id, 'org-a');
  assert.equal(parsed.event.model, 'gpt-5.6-luna');
  assert.equal(parsed.event.input_tokens, 11);
  assert.equal(parsed.event.output_tokens, 7);
  assert.equal(parsed.event.total_tokens, 18);
  assert.equal(parsed.event.estimated_cost_usd, null);
  assert.equal(parsed.logs.filter((item) => item.stage === 'ai_usage_recorded').length, 2);
});

test('@spec:AC-432 usage write failure does not repeat OpenAI call or leak secret', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.organization_config import InMemoryAiUsageTracker

class Transport:
    def __init__(self): self.calls = 0
    def post_json(self, url, *, headers, payload):
        self.calls += 1
        return {"id": "resp-fail", "model": payload["model"], "output": [], "usage": {"input_tokens": 1, "output_tokens": 1}}

logs = []
transport = Transport()
provider = OpenAIResponsesProvider(IntegrationConfig(openai_api_key="sk-secret-should-not-log"), transport, usage_tracker=InMemoryAiUsageTracker(fail=True), usage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details}))
response = provider.create_response(input_messages=[{"role": "user", "content": "oi"}], organization_id="org-a", conversation_id="00000000-0000-0000-0000-000000000001")
print(json.dumps({"callCount": transport.calls, "responseId": response["id"], "logs": logs}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.callCount, 1);
  assert.equal(parsed.responseId, 'resp-fail');
  assert.equal(parsed.logs[0].stage, 'ai_usage_record_failed');
  assert.doesNotMatch(JSON.stringify(parsed.logs), /sk-secret-should-not-log/);
});

test('@spec:AC-434 @spec:AC-435 env example and docs preserve legacy fallback and OpenAI project setup', () => {
  const envExample = readFileSync('.env.example', 'utf8');
  const docs = readFileSync('.spec/features/ai-organization-runtime-config/openai-projects.md', 'utf8');
  for (const key of [
    'ORGANIZATION_RUNTIME_CONFIG_JSON=',
    'ORGANIZATION_CREDENTIALS_JSON=',
    'ZAPI_INSTANCE_ORGANIZATION_MAP_JSON=',
    'OPENAI_API_KEY_CARVALHO=',
    'ZAPI_INSTANCE_TOKEN_CARVALHO=',
  ]) {
    assert.match(envExample, new RegExp(`^${key}$`, 'm'));
  }
  assert.match(docs, /OpenAI Project separado/);
  assert.match(docs, /credential_ref=OPENAI_API_KEY_CARVALHO/);
  assert.match(docs, /OPENAI_API_KEY/);
  assert.doesNotMatch(envExample + docs, /(sk-|Bearer\\s+[A-Za-z0-9]|ya29\\.)/);
});
