'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { readFileSync } = require('node:fs');

function runPython(source) {
  const result = spawnSync('python3', ['-c', source], {
    cwd: process.cwd(),
    env: { ...process.env, PYTHONPATH: 'src' },
    encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout.trim();
}

test('@spec:AC-198 inbound Z-API text reaches runtime and outbound uses generated response', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph, StaticResponseGenerator
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.adapter import DEFAULT_ACK_MESSAGE
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

logs = []
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(response_generator=StaticResponseGenerator("Gerado"), stage_logger=lambda stage, details=None: logs.append(stage)),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append(stage),
)
payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "txt-1", "phone": "5571999990000", "text": {"message": "Oi, gostaria de saber mais sobre transplante capilar"}}
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
print(json.dumps({
  "status": response.status_code,
  "runtimeCalls": adapter.runtime_calls,
  "decision": records[0].decision.value,
  "outbound": provider.sent_texts[0]["text"],
  "isAck": provider.sent_texts[0]["text"] == DEFAULT_ACK_MESSAGE,
  "logs": logs,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.equal(parsed.runtimeCalls, 1);
  assert.equal(parsed.decision, 'PROCESSED');
  assert.match(parsed.outbound, /^Gerado 1:/);
  assert.equal(parsed.isAck, false);
  assert.ok(parsed.logs.includes('runtime_started'));
  assert.ok(parsed.logs.includes('response_generated'));
  assert.ok(parsed.logs.includes('outbound_sent'));
  assert.equal(parsed.logs.filter((stage) => stage === 'runtime_started').length, 1);
  assert.equal(parsed.logs.filter((stage) => stage === 'response_generated').length, 1);
  assert.equal(parsed.logs.filter((stage) => stage === 'outbound_sent').length, 1);
});

test('@spec:AC-199 sequential Z-API turns reuse conversation state and previous history', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class HistoryAwareGenerator:
    def __init__(self):
        self.calls = []
    def generate(self, state, *, emit):
        inbound_history = [item["text"] for item in state.messages if item.get("direction") == "inbound"]
        self.calls.append({"conversationId": state.conversation_id, "history": inbound_history})
        emit("retrieval_completed", {"hitCount": len(inbound_history)})
        emit("model_called", {"call": len(self.calls)})
        emit("grounding_result", {"passed": True})
        return f"Resposta contextual {len(self.calls)} com {len(inbound_history)} turno(s)"

generator = HistoryAwareGenerator()
provider = FakeWhatsAppProvider()
store = InMemoryWhatsAppStore()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=store,
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(response_generator=generator),
    allow_placeholder_ack=False,
)
messages = [
  ("txt-1", "Oi, gostaria de saber mais sobre transplante capilar"),
  ("txt-2", "Meu problema são as entradas"),
  ("txt-3", "Isso começou há uns 3 anos"),
]
records = []
for message_id, text in messages:
    payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": message_id, "phone": "5571999990000", "text": {"message": text}}
    response, batch = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
    records.extend(batch)
print(json.dumps({
  "conversationIds": [record.inbound.conversation_id for record in records],
  "generatorCalls": generator.calls,
  "outbounds": [item["text"] for item in provider.sent_texts],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(new Set(parsed.conversationIds).size, 1);
  assert.deepEqual(parsed.generatorCalls.map((call) => call.history.length), [1, 2, 3]);
  assert.deepEqual(parsed.generatorCalls[1].history, [
    'Oi, gostaria de saber mais sobre transplante capilar',
    'Meu problema são as entradas',
  ]);
  assert.equal(new Set(parsed.outbounds).size, 3);
});

test('@spec:AC-200 contacts and organizations do not share Z-API conversation history', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph, StaticResponseGenerator
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

provider = FakeWhatsAppProvider()
store = InMemoryWhatsAppStore()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=store,
    organization_resolver=OrganizationResolver({"clinic-a": "org-a", "clinic-b": "org-b"}),
    runtime_graph=AgentRuntimeGraph(response_generator=StaticResponseGenerator("Gerado")),
    allow_placeholder_ack=False,
)
payloads = [
  {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "a1", "phone": "551", "text": {"message": "Oi"}},
  {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "a2", "phone": "552", "text": {"message": "Oi"}},
  {"type": "ReceivedCallback", "instanceId": "clinic-b", "messageId": "b1", "phone": "551", "text": {"message": "Oi"}, "organizationId": "org-a"},
]
records = []
for payload in payloads:
    response, batch = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
    records.extend(batch)
print(json.dumps({
  "conversationIds": [record.inbound.conversation_id for record in records],
  "organizationIds": [record.inbound.organization_id for record in records],
  "rawOrgIgnored": [record.inbound.metadata.get("rawOrganizationIgnored") for record in records],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(new Set(parsed.conversationIds).size, 3);
  assert.deepEqual(parsed.organizationIds, ['org-a', 'org-a', 'org-b']);
  assert.deepEqual(parsed.rawOrgIgnored, [null, null, 'org-a']);
});

test('@spec:AC-201 runtime failure is not masked by successful placeholder response', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class BrokenGenerator:
    def generate(self, state, *, emit):
        emit("model_called", {"provider": "test"})
        raise RuntimeError("OPENAI_API_KEY leaked-secret failed")

logs = []
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(response_generator=BrokenGenerator()),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "txt-1", "phone": "5571999990000", "text": {"message": "Oi"}}
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
print(json.dumps({
  "status": response.status_code,
  "body": response.body,
  "records": len(records),
  "sentTexts": provider.sent_texts,
  "logs": logs,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 500);
  assert.equal(parsed.records, 0);
  assert.deepEqual(parsed.sentTexts, []);
  assert.equal(parsed.body.includes('leaked-secret'), false);
  assert.ok(parsed.logs.some((entry) => entry.stage === 'runtime_failed'));
});

test('@spec:AC-202 live Z-API path exposes safe observability stages and no fake providers', () => {
  const server = readFileSync('src/ai_agent_runtime/whatsapp/zapi_server.py', 'utf8');
  const graph = readFileSync('src/ai_agent_runtime/graph.py', 'utf8');
  const adapter = readFileSync('src/ai_agent_runtime/whatsapp/adapter.py', 'utf8');
  assert.match(server, /OpenAIWhatsAppResponseGenerator/);
  assert.match(server, /OpenAIResponsesProvider/);
  assert.match(server, /OpenAISpeechToTextProvider/);
  assert.match(server, /MediaProcessor/);
  assert.match(server, /ZApiRuntimeRetrieval/);
  assert.match(server, /rest\/v1\/chunks/);
  assert.match(server, /rest\/v1\/document_versions/);
  assert.match(server, /organization_id/);
  assert.match(server, /allow_placeholder_ack=False/);
  assert.doesNotMatch(server, /FakeWhatsAppProvider|FakeSpeechToTextProvider/);
  for (const stage of [
    'webhook_received',
    'message_normalized',
    'organization_resolved',
    'conversation_resolved',
    'runtime_started',
    'retrieval_completed',
    'model_called',
    'grounding_result',
    'response_generated',
    'outbound_sent',
  ]) {
    assert.match(adapter + graph + server, new RegExp(stage));
  }
});

test('@spec:AC-411 @spec:AC-412 Z-API server is Render-ready and health avoids external providers', () => {
  const output = runPython(`
import json
import os

from ai_agent_runtime.whatsapp.zapi_server import HEALTH_PATH, ZApiWebhookRequestHandler, _server_host, _server_port, request

for name in ("HOST", "PORT", "ZAPI_WEBHOOK_PORT"):
    os.environ.pop(name, None)
fallback = {"host": _server_host(), "port": _server_port()}
os.environ["PORT"] = "10000"
render = {"host": _server_host(), "port": _server_port()}
os.environ.pop("PORT", None)
os.environ["ZAPI_WEBHOOK_PORT"] = "8088"
legacy = {"port": _server_port()}

def forbidden_urlopen(*args, **kwargs):
    raise AssertionError("health must not call external providers")

request.urlopen = forbidden_urlopen
ZApiWebhookRequestHandler.adapter = None
ZApiWebhookRequestHandler.config = None

health_handler = object.__new__(ZApiWebhookRequestHandler)
health_handler.path = HEALTH_PATH
health_writes = []
health_handler._write = lambda response: health_writes.append(response)
health_handler.do_GET()

missing_handler = object.__new__(ZApiWebhookRequestHandler)
missing_handler.path = "/missing"
missing_writes = []
missing_handler._write = lambda response: missing_writes.append(response)
missing_handler.do_GET()

response = health_writes[0]
missing_response = missing_writes[0]

print(json.dumps({
  "fallback": fallback,
  "render": render,
  "legacy": legacy,
  "healthStatus": response.status_code,
  "health": json.loads(response.body),
  "missingStatus": missing_response.status_code,
  "missingBody": missing_response.body,
}))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed.fallback, { host: '0.0.0.0', port: 8082 });
  assert.deepEqual(parsed.render, { host: '0.0.0.0', port: 10000 });
  assert.deepEqual(parsed.legacy, { port: 8088 });
  assert.equal(parsed.healthStatus, 200);
  assert.equal(parsed.health.status, 'ok');
  assert.equal(parsed.health.provider, 'zapi');
  assert.equal(parsed.health.webhookPath, '/webhooks/zapi/whatsapp');
  assert.equal(parsed.missingStatus, 404);
  assert.equal(parsed.missingBody, 'Not Found');
});

test('@spec:AC-413 @spec:AC-414 Z-API store path supports persistent disk and production default', () => {
  const output = runPython(`
import json
import os
import tempfile
from pathlib import Path

from ai_agent_runtime.whatsapp.zapi_server import _build_zapi_store, _zapi_store_path

for name in ("ZAPI_STORE_PATH", "APP_ENV", "RENDER"):
    os.environ.pop(name, None)
local_default = str(_zapi_store_path())
os.environ["APP_ENV"] = "production"
production_default = str(_zapi_store_path())
os.environ.pop("APP_ENV", None)
os.environ["RENDER"] = "true"
render_default = str(_zapi_store_path())
os.environ.pop("RENDER", None)

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "persistent" / "zapi-whatsapp-store.json"
    store = _build_zapi_store(path)
    created = path.exists()
    initial = json.loads(path.read_text(encoding="utf-8") or "{}")
    conversation_id = store.conversation_id_for(organization_id="org-a", channel="whatsapp", contact_external_id="5571999990000")
    reloaded = _build_zapi_store(path)
    reloaded_id = reloaded.conversation_id_for(organization_id="org-a", channel="whatsapp", contact_external_id="5571999990000")

print(json.dumps({
  "localDefault": local_default,
  "productionDefault": production_default,
  "renderDefault": render_default,
  "created": created,
  "initial": initial,
  "sameConversation": conversation_id == reloaded_id,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.localDefault, '.sandbox/zapi-whatsapp-store.json');
  assert.equal(parsed.productionDefault, '/var/data/zapi-whatsapp-store.json');
  assert.equal(parsed.renderDefault, '/var/data/zapi-whatsapp-store.json');
  assert.equal(parsed.created, true);
  assert.deepEqual(parsed.initial, {});
  assert.equal(parsed.sameConversation, true);
});

test('@spec:AC-418 @spec:AC-419 Render guide documents safe start, health, disk, and env names', () => {
  const guide = readFileSync('.spec/features/ai-whatsapp-zapi-provider/render-web-service.md', 'utf8');
  const envExample = readFileSync('.env.example', 'utf8');
  assert.match(guide, /PYTHONPATH=src python3 -m ai_agent_runtime\.whatsapp\.zapi_server/);
  assert.match(guide, /\/health/);
  assert.match(guide, /\/var\/data/);
  assert.match(guide, /ZAPI_STORE_PATH=\/var\/data\/zapi-whatsapp-store\.json/);
  assert.match(guide, /AI_INBOUND_ENABLED/);
  assert.match(envExample, /^AI_INBOUND_ENABLED=true$/m);
  assert.match(envExample, /^ZAPI_STORE_PATH=\/var\/data\/zapi-whatsapp-store\.json$/m);
  assert.doesNotMatch(guide + envExample, /ZAPI_INSTANCE_TOKEN=.+[A-Za-z0-9]{8}/);
  assert.doesNotMatch(guide + envExample, /OPENAI_API_KEY=sk-/);
});

test('@spec:AC-203 @spec:AC-206 Supabase retrieval HTTP 400 logs provider stage and sanitized body', () => {
  const output = runPython(`
import io
import json
from urllib.error import HTTPError
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.state import AgentState
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator, ZApiRuntimeRetrieval, request

def failing_urlopen(req, timeout=20):
    body = b'{"code":"22P02","message":"invalid input syntax for type uuid: \\\\"sandbox-org-aurora\\\\"","apikey":"secret-key"}'
    raise HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(body))

request.urlopen = failing_urlopen
logs = []
graph = AgentRuntimeGraph(
    response_generator=OpenAIWhatsAppResponseGenerator(
        OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key")),
        retrieval=ZApiRuntimeRetrieval(supabase_url="https://example.supabase.co", service_role_key="secret-key"),
    ),
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
failed = False
try:
    graph.run(AgentState(conversation_id="conv-1", organization_id="sandbox-org-aurora", current_message="Quanto custa transplante capilar?"))
except Exception as exc:
    failed = True
    error_text = str(exc)
print(json.dumps({"failed": failed, "error": error_text, "logs": logs}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.failed, true);
  assert.equal(parsed.error.includes('secret-key'), false);
  const started = parsed.logs.find((entry) => entry.stage === 'retrieval_started');
  const failed = parsed.logs.find((entry) => entry.stage === 'retrieval_failed');
  assert.equal(started.details.provider, 'supabase');
  assert.equal(started.details.endpoint, 'rest/v1/chunks');
  assert.equal(failed.details.provider, 'supabase');
  assert.equal(failed.details.status, 400);
  assert.equal(failed.details.endpoint, 'rest/v1/document_versions');
  assert.equal(failed.details.code, '22P02');
  assert.match(failed.details.body.message, /invalid input syntax for type uuid/);
  assert.equal(Object.prototype.hasOwnProperty.call(failed.details.body, 'apikey'), false);
  assert.equal(parsed.logs.some((entry) => entry.stage === 'model_call_started'), false);
});

test('@spec:AC-204 @spec:AC-207 Z-API live server maps sandbox organization slug to Supabase UUID', () => {
  const output = runPython(`
import json
from ai_agent_runtime.sandbox_ids import LEONARDO_ORG_ID, deterministic_sandbox_uuid
from ai_agent_runtime.whatsapp.zapi_server import _runtime_organization_id

expected = deterministic_sandbox_uuid(LEONARDO_ORG_ID)
print(json.dumps({
  "logical": LEONARDO_ORG_ID,
  "runtime": _runtime_organization_id(LEONARDO_ORG_ID),
  "expected": expected,
  "custom": _runtime_organization_id("550e8400-e29b-41d4-a716-446655440000"),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.logical, 'sandbox-org-dr-leonardo-carvalho');
  assert.equal(parsed.runtime, parsed.expected);
  assert.match(parsed.runtime, /^[0-9a-f-]{36}$/);
  assert.equal(parsed.custom, '550e8400-e29b-41d4-a716-446655440000');
});

test('@spec:AC-208 importing zapi_server does not require langsmith or sandbox package bootstrap', () => {
  const output = runPython(`
import builtins
import json
import sys

original_import = builtins.__import__
def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "langsmith" or name.startswith("langsmith."):
        raise ModuleNotFoundError("No module named 'langsmith'")
    return original_import(name, globals, locals, fromlist, level)

builtins.__import__ = guarded_import
import ai_agent_runtime.whatsapp.zapi_server as zapi_server
print(json.dumps({
  "imported": bool(zapi_server.WEBHOOK_PATH),
  "sandboxPackageLoaded": "ai_agent_runtime.sandbox" in sys.modules,
  "langsmithLoaded": any(name == "langsmith" or name.startswith("langsmith.") for name in sys.modules),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.imported, true);
  assert.equal(parsed.sandboxPackageLoaded, false);
  assert.equal(parsed.langsmithLoaded, false);
});

test('@spec:AC-209 sandbox dataset and Z-API runtime share neutral deterministic IDs', () => {
  const output = runPython(`
import json
from ai_agent_runtime.sandbox_ids import BOREAL_ORG_ID, DATASET_VERSION, LEONARDO_ORG_ID, deterministic_sandbox_uuid
from ai_agent_runtime.sandbox.dataset import build_sandbox_dataset
from ai_agent_runtime.whatsapp.zapi_server import _runtime_organization_id

dataset = build_sandbox_dataset()
print(json.dumps({
  "datasetVersion": dataset.version,
  "sharedVersion": DATASET_VERSION,
  "datasetOrgs": [org.id for org in dataset.organizations],
  "sharedOrgs": [LEONARDO_ORG_ID, BOREAL_ORG_ID],
  "leonardoRuntime": _runtime_organization_id(LEONARDO_ORG_ID),
  "leonardoShared": deterministic_sandbox_uuid(LEONARDO_ORG_ID),
  "borealRuntime": _runtime_organization_id(BOREAL_ORG_ID),
  "borealShared": deterministic_sandbox_uuid(BOREAL_ORG_ID),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.datasetVersion, parsed.sharedVersion);
  assert.deepEqual(parsed.datasetOrgs, parsed.sharedOrgs);
  assert.equal(parsed.leonardoRuntime, parsed.leonardoShared);
  assert.equal(parsed.borealRuntime, parsed.borealShared);
});

test('@spec:AC-210 @spec:AC-215 one inbound invokes runtime once and emits one outbound', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph, StaticResponseGenerator
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

logs = []
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(response_generator=StaticResponseGenerator("Gerado"), stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}})),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "once-1", "phone": "5571", "momment": "100", "text": {"message": "Oi"}}
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
print(json.dumps({
  "status": response.status_code,
  "recordCount": len(records),
  "runtimeCalls": adapter.runtime_calls,
  "outboundCount": len(provider.sent_texts),
  "runtimeInvocationLogs": [entry for entry in logs if entry["stage"] == "runtime_invocation_id"],
  "runtimeStartedCount": len([entry for entry in logs if entry["stage"] == "runtime_started"]),
  "responseGeneratedCount": len([entry for entry in logs if entry["stage"] == "response_generated"]),
  "outboundSentCount": len([entry for entry in logs if entry["stage"] == "outbound_sent"]),
  "lifecycleStages": [entry["stage"] for entry in logs],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.equal(parsed.recordCount, 1);
  assert.equal(parsed.runtimeCalls, 1);
  assert.equal(parsed.outboundCount, 1);
  assert.equal(parsed.runtimeInvocationLogs.length, 1);
  assert.equal(parsed.runtimeStartedCount, 1);
  assert.equal(parsed.responseGeneratedCount, 1);
  assert.equal(parsed.outboundSentCount, 1);
  for (const stage of ['inbound_received', 'conversation_history_loaded', 'history_turn_count', 'runtime_invocation_id', 'outbound_sent']) {
    assert.ok(parsed.lifecycleStages.includes(stage), `${stage} missing`);
  }
});

test('@spec:AC-211 distinct messageIds reuse conversation and load previous history', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class CapturingGenerator:
    def __init__(self):
        self.calls = []
    def generate(self, state, *, emit):
        self.calls.append({
            "conversationId": state.conversation_id,
            "history": [item.get("text") for item in state.messages],
            "runtimeInvocationId": state.context.get("runtimeInvocationId"),
        })
        emit("retrieval_completed", {"status": "NOT_CONFIGURED", "hitCount": 0})
        emit("model_called", {"mode": "test"})
        emit("grounding_result", {"passed": True, "evidenceCount": 0})
        return f"Turno {len(self.calls)}"

generator = CapturingGenerator()
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(response_generator=generator),
    allow_placeholder_ack=False,
)
for message_id, text, moment in [("m-1", "Oi, gostaria de saber mais", "100"), ("m-2", "Entradas, faz 1 ano", "101")]:
    payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": message_id, "phone": "5571", "momment": moment, "text": {"message": text}}
    handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
print(json.dumps({
  "runtimeCalls": adapter.runtime_calls,
  "sentTexts": [item["text"] for item in provider.sent_texts],
  "conversationIds": [call["conversationId"] for call in generator.calls],
  "histories": [call["history"] for call in generator.calls],
  "invocationIds": [call["runtimeInvocationId"] for call in generator.calls],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.runtimeCalls, 2);
  assert.deepEqual(parsed.sentTexts, ['Turno 1', 'Turno 2']);
  assert.equal(new Set(parsed.conversationIds).size, 1);
  assert.deepEqual(parsed.histories[0], ['Oi, gostaria de saber mais']);
  assert.deepEqual(parsed.histories[1], ['Oi, gostaria de saber mais', 'Entradas, faz 1 ano']);
  assert.equal(new Set(parsed.invocationIds).size, 2);
});

test('@spec:AC-212 @spec:AC-215 duplicate, fromMe, and out-of-order callbacks do not reinvoke runtime', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph, StaticResponseGenerator
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

logs = []
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(response_generator=StaticResponseGenerator("Gerado")),
    allow_placeholder_ack=False,
    reject_out_of_order=True,
    stage_logger=lambda stage, details=None: logs.append(stage),
)
payloads = [
  {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "m-1", "phone": "5571", "momment": "100", "text": {"message": "Oi"}},
  {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "m-1", "phone": "5571", "momment": "100", "text": {"message": "Oi duplicado"}},
  {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "self-1", "phone": "5571", "momment": "101", "fromMe": True, "text": {"message": "Resposta minha"}},
  {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "old-1", "phone": "5571", "momment": "99", "text": {"message": "Mensagem antiga"}},
]
decisions = []
for payload in payloads:
    response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
    decisions.extend(record.decision.value for record in records)
print(json.dumps({
  "decisions": decisions,
  "runtimeCalls": adapter.runtime_calls,
  "outboundCount": len(provider.sent_texts),
  "logs": logs,
}))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed.decisions, ['PROCESSED', 'DUPLICATE_SUPPRESSED', 'SELF_MESSAGE_IGNORED', 'ORDERING_REJECTED']);
  assert.equal(parsed.runtimeCalls, 1);
  assert.equal(parsed.outboundCount, 1);
  assert.ok(parsed.logs.includes('duplicate_detected'));
  assert.ok(parsed.logs.includes('self_message_ignored'));
  assert.ok(parsed.logs.includes('ordering_rejected'));
});

test('@spec:AC-213 @spec:AC-214 factual zero-evidence response fails grounding while conversational response can pass', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp.zapi_server import validate_live_grounding

factual = validate_live_grounding("O transplante capilar e um procedimento que redistribui fios para regioes com falhas.", evidence_count=0)
conversational = validate_live_grounding("Entendi. Para te orientar melhor, me conta qual regiao te incomoda mais?", evidence_count=0)
grounded = validate_live_grounding("Consulta com Dra. Marina: R$ 500.", evidence_count=1)
print(json.dumps({"factual": factual, "conversational": conversational, "grounded": grounded}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.factual.passed, false);
  assert.equal(parsed.factual.reason, 'UNSUPPORTED_FACTUAL_CLAIM');
  assert.equal(parsed.factual.evidenceCount, 0);
  assert.equal(parsed.conversational.passed, true);
  assert.equal(parsed.conversational.evidenceCount, 0);
  assert.equal(parsed.grounded.passed, true);
  assert.equal(parsed.grounded.evidenceCount, 1);
});

test('@spec:AC-213 factual zero-evidence model output becomes human handoff when user asked factual question', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class FactualTransport:
    def post_json(self, url, *, headers, payload):
        return {"id": "resp-1", "status": "completed", "output_text": "O transplante capilar e um procedimento que redistribui fios para regioes com falhas."}

logs = []
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), FactualTransport())),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "ground-1", "phone": "5571", "momment": "100", "text": {"message": "O que e transplante capilar?"}}
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
grounding = [entry for entry in logs if entry["stage"] == "grounding_result"][-1]["details"]
print(json.dumps({
  "status": response.status_code,
  "decision": records[0].decision.value,
  "agentDecision": records[0].agent_decision,
  "sentCount": len(provider.sent_texts),
  "hasOutbound": records[0].outbound is not None,
  "grounding": grounding,
  "responseGeneratedCount": len([entry for entry in logs if entry["stage"] == "response_generated"]),
  "suppressed": any(entry["stage"] == "outbound_suppressed" for entry in logs),
  "origin": [entry["details"]["origin"] for entry in logs if entry["stage"] == "grounding_failure_origin"][-1],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.equal(parsed.decision, 'HUMAN_HANDOFF_REQUIRED');
  assert.equal(parsed.agentDecision, 'HUMAN_HANDOFF_REQUIRED');
  assert.equal(parsed.grounding.passed, false);
  assert.equal(parsed.grounding.reason, 'UNSUPPORTED_FACTUAL_CLAIM');
  assert.equal(parsed.grounding.evidenceCount, 0);
  assert.equal(parsed.sentCount, 0);
  assert.equal(parsed.hasOutbound, false);
  assert.equal(parsed.suppressed, true);
  assert.equal(parsed.responseGeneratedCount, 0);
  assert.equal(parsed.origin, 'USER_REQUESTED_UNSUPPORTED_FACT');
});

test('@spec:AC-205 @spec:AC-206 OpenAI HTTP 400 logs model call stage and sanitized body', () => {
  const output = runPython(`
import io
import json
from urllib.error import HTTPError
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.state import AgentState
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator

class FailingTransport:
    def post_json(self, url, *, headers, payload):
        body = b'{"error":{"code":"invalid_request_error","message":"Unsupported parameter: reasoning","param":"reasoning"},"authorization":"Bearer secret"}'
        raise HTTPError(url, 400, "Bad Request", {}, io.BytesIO(body))

logs = []
graph = AgentRuntimeGraph(
    response_generator=OpenAIWhatsAppResponseGenerator(
        OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), FailingTransport()),
        retrieval=None,
    ),
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
failed = False
error_text = ""
try:
    graph.run(AgentState(conversation_id="conv-1", organization_id="org-a", current_message="Tenho interesse em melhorar meu sorriso"))
except Exception as exc:
    failed = True
    error_text = str(exc)
print(json.dumps({"failed": failed, "error": error_text, "logs": logs}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.failed, true);
  assert.equal(parsed.error.includes('secret'), false);
  assert.ok(parsed.logs.some((entry) => entry.stage === 'retrieval_completed' && entry.details.status === 'NOT_CONFIGURED'));
  const started = parsed.logs.find((entry) => entry.stage === 'model_call_started');
  const failed = parsed.logs.find((entry) => entry.stage === 'model_call_failed');
  assert.equal(started.details.provider, 'openai');
  assert.equal(started.details.endpoint, 'responses');
  assert.equal(failed.details.provider, 'openai');
  assert.equal(failed.details.status, 400);
  assert.equal(failed.details.endpoint, 'responses');
  assert.equal(failed.details.body.error.code, 'invalid_request_error');
  assert.match(failed.details.body.error.message, /Unsupported parameter/);
  assert.equal(Object.prototype.hasOwnProperty.call(failed.details.body, 'authorization'), false);
});

test('@spec:AC-216 @spec:AC-217 Dr. Leonardo retrieval finds briefing terms without cross-org leakage', () => {
  const output = runPython(`
import json
from urllib import parse
from ai_agent_runtime.whatsapp.zapi_server import ZApiRuntimeRetrieval, _retrieval_terms, request

ORG_A = "dfdcdff0-6d5f-58cc-9a83-2829820b7f8e"
ORG_B = "11111111-1111-4111-8111-111111111111"

class Response:
    def __init__(self, rows):
        self.rows = rows
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def read(self):
        return json.dumps(self.rows).encode("utf-8")

calls = []
def fake_urlopen(req, timeout=20):
    parsed = parse.urlparse(req.full_url)
    qs = parse.parse_qs(parsed.query)
    calls.append({"path": parsed.path, "query": {key: values[0] for key, values in qs.items()}})
    if parsed.path.endswith("/document_versions"):
        return Response([
            {"id": "ver-published", "organization_id": ORG_A, "status": "PUBLISHED", "processing_valid": True},
            {"id": "ver-draft", "organization_id": ORG_A, "status": "DRAFT", "processing_valid": True},
            {"id": "ver-other", "organization_id": ORG_B, "status": "PUBLISHED", "processing_valid": True},
        ])
    content_filter = qs.get("content", [""])[0].lower()
    fixtures = {
        "implante": "Servicos informados: implantes, proteses, periodontia e odontologia digital.",
        "protese": "Servicos informados: implantes, proteses, periodontia e odontologia digital.",
        "scanner": "Diferenciais: Scanner Virtuo, visualizacao 3D e tomografia Cone Beam.",
        "virtuo": "Diferenciais: Scanner Virtuo, visualizacao 3D e tomografia Cone Beam.",
        "hospital": "Clinica Tavares: Av. Prof. Magalhaes Neto, 1541, 4 andar, sala 4022, Bloco A, Pituba.",
        "bahia": "Clinica Tavares: Av. Prof. Magalhaes Neto, 1541, 4 andar, sala 4022, Bloco A, Pituba.",
        "pituba": "Clinica Tavares: Av. Prof. Magalhaes Neto, 1541, 4 andar, sala 4022, Bloco A, Pituba.",
        "clinica": "Clinica Carvalho: Rua Doutor Otaviano Pimenta, 41, Matatu, Salvador/BA. Clinica Tavares: Av. Prof. Magalhaes Neto, 1541, 4 andar, sala 4022, Bloco A, Pituba.",
        "matatu": "Clinica Carvalho: Rua Doutor Otaviano Pimenta, 41, Matatu, Salvador/BA.",
        "pagamento": "Pagamento: PIX, cartao de credito, cartao de debito e boleto. Parcela minima de R$ 500. Nao ha deposito antecipado.",
        "procedimento": "Valores dos procedimentos sao informados apos avaliacao. A avaliacao e gratuita para casos de busca por procedimento.",
        "avaliacao": "Avaliacao gratuita: para casos de busca por procedimento, incluindo implante e lentes, a avaliacao e gratuita. Consulta de avaliacao nesse contexto tambem e gratuita.",
        "gratuita": "Avaliacao gratuita: para casos de busca por procedimento, incluindo implante e lentes, a avaliacao e gratuita. Consulta de avaliacao nesse contexto tambem e gratuita.",
        "consulta": "Avaliacao gratuita: para casos de busca por procedimento, incluindo implante e lentes, a avaliacao e gratuita. Consulta de avaliacao nesse contexto tambem e gratuita.",
        "lente": "Avaliacao gratuita: para casos de busca por procedimento, incluindo implante e lentes, a avaliacao e gratuita. Valores dos procedimentos sao informados apos avaliacao.",
        "carga": "Duvidas sobre carga imediata exigem avaliacao profissional e podem requerer handoff.",
        "imediata": "Duvidas sobre carga imediata exigem avaliacao profissional e podem requerer handoff.",
    }
    for term, content in fixtures.items():
        if term in content_filter:
            return Response([
                {"id": f"chunk-{term}", "organization_id": ORG_A, "document_version_id": "ver-published", "content": content},
                {"id": "chunk-draft", "organization_id": ORG_A, "document_version_id": "ver-draft", "content": f"{term} rascunho"},
                {"id": "chunk-other", "organization_id": ORG_B, "document_version_id": "ver-other", "content": f"{term} outra organizacao"},
            ])
    return Response([])

request.urlopen = fake_urlopen
retrieval = ZApiRuntimeRetrieval(supabase_url="https://example.supabase.co", service_role_key="secret-key")
queries = ["implante", "prótese", "Scanner Virtuo", "onde fica a clínica", "Pituba", "Matatu", "formas de pagamento", "quanto custa o procedimento", "avaliação gratuita", "quanto custa lente", "carga imediata"]
results = {query: retrieval.search(ORG_A, query) for query in queries}
print(json.dumps({
  "terms": {query: _retrieval_terms(query) for query in queries},
  "hitCounts": {query: len(rows) for query, rows in results.items()},
  "implantContent": results["implante"][0]["content"],
  "priceContent": results["quanto custa o procedimento"][0]["content"],
  "evaluationContent": results["avaliação gratuita"][0]["content"],
  "leaked": any(row["organization_id"] != ORG_A or row["document_version_id"] != "ver-published" for rows in results.values() for row in rows),
  "calls": calls,
}))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed.terms.implante, ['implante']);
  assert.deepEqual(parsed.terms['Scanner Virtuo'], ['scanner', 'virtuo']);
  assert.deepEqual(parsed.terms['avaliação gratuita'], ['avaliacao', 'gratuita']);
  for (const count of Object.values(parsed.hitCounts)) assert.ok(count >= 1);
  assert.match(parsed.implantContent, /implantes/);
  assert.match(parsed.priceContent, /apos avaliacao/);
  assert.match(parsed.evaluationContent, /busca por procedimento/);
  assert.doesNotMatch(JSON.stringify(parsed), /sala 4020/);
  assert.doesNotMatch(parsed.evaluationContent, /nao e regra universal|precisa confirmar|pode nao ser cobrada/i);
  assert.equal(parsed.leaked, false);
  assert.ok(parsed.calls.some((call) => call.path.endsWith('/document_versions')));
  assert.ok(parsed.calls.some((call) => call.path.endsWith('/chunks') && call.query.content === 'ilike.*implante*'));
});

test('@spec:AC-344 @spec:AC-346 @spec:AC-347 @spec:AC-348 Dr. Leonardo evaluation and procedure price retrieval use current free-evaluation briefing', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp.zapi_server import validate_live_grounding, _response_requires_authorized_evidence

evidence = [{
    "id": "chunk-v2-evaluation",
    "organization_id": "org-leonardo",
    "document_version_id": "ver-v2",
    "content": "Avaliacao gratuita: para casos de busca por procedimento, incluindo implante e lentes, a avaliacao e gratuita. Valores dos procedimentos sao informados apos avaliacao. Pagamento por PIX, cartao de credito, cartao de debito e boleto. Parcela minima de R$ 500. Nao ha deposito antecipado.",
}]
free_response = "A avaliacao e gratuita para quem esta buscando um procedimento."
implant_price = "O valor do implante e informado apos a avaliacao. A avaliacao e gratuita."
lens_price = "O valor da lente e informado apos a avaliacao. A avaliacao e gratuita."
ambiguous = "A avaliacao pode nao ser cobrada, mas precisa confirmar com a clinica."
print(json.dumps({
  "freeRequiresEvidence": _response_requires_authorized_evidence(free_response),
  "freeGrounding": validate_live_grounding(free_response, evidence_count=1, evidence=evidence),
  "implantGrounding": validate_live_grounding(implant_price, evidence_count=1, evidence=evidence),
  "lensGrounding": validate_live_grounding(lens_price, evidence_count=1, evidence=evidence),
  "ambiguousGrounding": validate_live_grounding(ambiguous, evidence_count=1, evidence=evidence),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.freeRequiresEvidence, true);
  assert.equal(parsed.freeGrounding.passed, true);
  assert.equal(parsed.implantGrounding.passed, true);
  assert.equal(parsed.lensGrounding.passed, true);
  assert.equal(parsed.ambiguousGrounding.passed, false);
  assert.equal(parsed.ambiguousGrounding.reason, 'STALE_FREE_EVALUATION_AMBIGUITY');
});

test('@spec:AC-437 @spec:AC-438 @spec:AC-439 @spec:AC-440 @spec:AC-441 @spec:AC-442 @spec:AC-443 @spec:AC-445 Dr. Leonardo briefing v3 retrieval and runtime decisions match production source', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.state import AgentState
from ai_agent_runtime.whatsapp.zapi_server import (
    OpenAIWhatsAppResponseGenerator,
    ZApiRuntimeRetrieval,
    _classify_turn_context,
    validate_live_grounding,
)

ORG = "dfdcdff0-6d5f-58cc-9a83-2829820b7f8e"

class StaticRetrieval(ZApiRuntimeRetrieval):
    def __init__(self):
        pass
    def search(self, organization_id, query):
        assert organization_id == ORG
        text = query.lower()
        chunks = {
            "avaliacao": "Avaliacao gratuita: para casos de busca por procedimento, incluindo implante, lentes e outros procedimentos, a avaliacao e gratuita.",
            "pituba": "Clinica Tavares: Av. Prof. Magalhaes Neto, 1541, 4 andar, sala 4022, Bloco A, Pituba, Salvador/BA.",
            "sala": "Clinica Tavares: Av. Prof. Magalhaes Neto, 1541, 4 andar, sala 4022, Bloco A, Pituba, Salvador/BA.",
            "implante": "Servicos/procedimentos informados: implantes; proteses; endodontia; ortodontia; periodontia; odontologia digital.",
            "pagamento": "Pagamento: PIX, cartao de credito, cartao de debito e boleto. Parcela minima de R$ 500. Nao ha deposito antecipado.",
            "convenio": "Objecoes frequentes registradas: medo, preco, localizacao, estacionamento, convenio, falta de tempo e comparacao com concorrentes. O briefing nao autoriza afirmar aceite ou recusa de convenio.",
        }
        hits = []
        for term, content in chunks.items():
            if term in text or (term == "pituba" and "unidade" in text) or (term == "pagamento" and "formas" in text):
                hits.append({"id": f"chunk-v3-{term}", "organization_id": organization_id, "document_version_id": "ver-v3", "content": content})
        return hits
    def closed_world_procedure_decision(self, organization_id, query):
        return None

class Transport:
    def __init__(self): self.calls = []
    def post_json(self, url, *, headers, payload):
        self.calls.append(payload)
        return {"status": "completed", "output_text": "Posso te ajudar por aqui e, se precisar confirmar algo especifico, encaminho para o atendimento."}

retrieval = StaticRetrieval()
queries = {
    "avaliacao": "Quanto custa a avaliacao?",
    "pituba": "Onde fica a unidade da Pituba?",
    "sala": "Qual a sala?",
    "implante": "Voces fazem implante?",
    "pagamento": "Quais formas de pagamento?",
    "convenio": "Voces aceitam convenio?",
}
hits = {name: retrieval.search(ORG, query) for name, query in queries.items()}
pituba_text = "\\n".join(item["content"] for item in hits["pituba"] + hits["sala"])
convenio_text = "\\n".join(item["content"] for item in hits["convenio"])
evaluation_grounding = validate_live_grounding("A avaliacao e gratuita para casos de busca por procedimento.", evidence_count=len(hits["avaliacao"]), evidence=hits["avaliacao"])
payment_grounding = validate_live_grounding("As formas de pagamento sao PIX, cartao de credito, cartao de debito e boleto. A parcela minima registrada e R$ 500 e nao ha deposito antecipado.", evidence_count=len(hits["pagamento"]), evidence=hits["pagamento"])
specific_schedule = _classify_turn_context("Quero marcar para amanha as 10h", [])
doctor_talk = _classify_turn_context("Quero falar com Dr. Leonardo", [])
bleeding = _classify_turn_context("Fiz um implante ontem e estou com sangramento", [])
old_policy = "Clinica Tavares: sala 4020. Handoff para dor intensa, inchaco, trauma e pedido direto do dentista."

transport = Transport()
graph = AgentRuntimeGraph(
    response_generator=OpenAIWhatsAppResponseGenerator(OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), transport), retrieval=retrieval),
)
doctor_state = graph.run(AgentState(conversation_id="conv-doctor", organization_id=ORG, current_message="Quero falar com Dr. Leonardo"))

print(json.dumps({
  "hitCounts": {key: len(value) for key, value in hits.items()},
  "pitubaText": pituba_text,
  "convenioText": convenio_text,
  "evaluationGrounding": evaluation_grounding,
  "paymentGrounding": payment_grounding,
  "specificSchedule": specific_schedule,
  "doctorTalk": doctor_talk,
  "doctorDecision": doctor_state.decision.value,
  "doctorHandoff": doctor_state.handoff_context is not None,
  "bleeding": bleeding,
  "oldPolicyCurrent": old_policy in pituba_text or any(old_policy in item["content"] for rows in hits.values() for item in rows),
}))
`);
  const parsed = JSON.parse(output);
  for (const count of Object.values(parsed.hitCounts)) assert.ok(count >= 1);
  assert.match(parsed.pitubaText, /Av\. Prof\. Magalhaes Neto, 1541/);
  assert.match(parsed.pitubaText, /4 andar/);
  assert.match(parsed.pitubaText, /Bloco A/);
  assert.match(parsed.pitubaText, /Pituba/);
  assert.match(parsed.pitubaText, /sala 4022/);
  assert.doesNotMatch(parsed.pitubaText, /sala 4020/);
  assert.equal(parsed.evaluationGrounding.passed, true);
  assert.equal(parsed.paymentGrounding.passed, true);
  assert.equal(parsed.specificSchedule.handoff_decision, 'HUMAN_HANDOFF_REQUIRED');
  assert.equal(parsed.specificSchedule.unsupported_attribute_reason, 'SCHEDULING_TIME_CONFIRMATION_REQUIRED');
  assert.equal(parsed.doctorTalk.handoff_decision, 'NONE');
  assert.equal(parsed.doctorDecision, 'CONTINUE');
  assert.equal(parsed.doctorHandoff, false);
  assert.equal(parsed.bleeding.handoff_decision, 'HUMAN_HANDOFF_REQUIRED');
  assert.equal(parsed.bleeding.unsupported_attribute_reason, 'POST_PROCEDURE_BLEEDING');
  assert.doesNotMatch(parsed.convenioText, /aceitamos convenio|nao aceitamos convenio/i);
  assert.equal(parsed.oldPolicyCurrent, false);
});

test('@spec:AC-218 @spec:AC-219 @spec:AC-220 @spec:AC-221 live sandbox store persists history across restart-like reloads', () => {
  const output = runPython(`
import json
import tempfile
from pathlib import Path
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, JsonFileWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class CapturingGenerator:
    def __init__(self):
        self.calls = []
    def generate(self, state, *, emit):
        inbound_history = [item.get("text") for item in state.messages if item.get("direction") == "inbound"]
        self.calls.append({"conversationId": state.conversation_id, "history": inbound_history})
        emit("retrieval_completed", {"status": "NOT_CONFIGURED", "hitCount": 0})
        emit("model_called", {"mode": "test"})
        emit("grounding_result", {"passed": True, "evidenceCount": 0})
        return f"Resposta {len(self.calls)}"

def adapter_for(path, generator, provider):
    return WhatsAppChannelAdapter(
        provider=provider,
        store=JsonFileWhatsAppStore(path),
        organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
        runtime_graph=AgentRuntimeGraph(response_generator=generator),
        allow_placeholder_ack=False,
        reject_out_of_order=True,
    )

def post(adapter, message_id, text, moment):
    payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": message_id, "phone": "5571", "momment": moment, "text": {"message": text}}
    response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
    return response.status_code, records[0].inbound.conversation_id

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "zapi-store.json"
    provider = FakeWhatsAppProvider()
    generator1 = CapturingGenerator()
    status1, conv1 = post(adapter_for(path, generator1, provider), "m-1", "Oi, gostaria de saber mais sobre botox", "100")

    generator2 = CapturingGenerator()
    status2, conv2 = post(adapter_for(path, generator2, provider), "m-2", "Tenho interesse na testa", "101")

    generator3 = CapturingGenerator()
    status3, conv3 = post(adapter_for(path, generator3, provider), "m-3", "Quanto custa?", "102")

    reloaded = JsonFileWhatsAppStore(path)
    fresh_path = Path(tmp) / "empty-store.json"
    fresh = JsonFileWhatsAppStore(fresh_path)
    print(json.dumps({
      "statuses": [status1, status2, status3],
      "conversationIds": [conv1, conv2, conv3],
      "turnHistories": [generator1.calls[0]["history"], generator2.calls[0]["history"], generator3.calls[0]["history"]],
      "persistedHistory": [message.text for message in reloaded.history_for(conv1)],
      "outboundCount": len(reloaded.outbound_messages),
      "freshHistory": fresh.history_for(conv1),
      "storeExists": path.exists(),
    }))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed.statuses, [200, 200, 200]);
  assert.equal(new Set(parsed.conversationIds).size, 1);
  assert.deepEqual(parsed.turnHistories[0], ['Oi, gostaria de saber mais sobre botox']);
  assert.deepEqual(parsed.turnHistories[1], ['Oi, gostaria de saber mais sobre botox', 'Tenho interesse na testa']);
  assert.deepEqual(parsed.turnHistories[2], ['Oi, gostaria de saber mais sobre botox', 'Tenho interesse na testa', 'Quanto custa?']);
  assert.deepEqual(parsed.persistedHistory, ['Oi, gostaria de saber mais sobre botox', 'Tenho interesse na testa', 'Quanto custa?']);
  assert.equal(parsed.outboundCount, 3);
  assert.deepEqual(parsed.freshHistory, []);
  assert.equal(parsed.storeExists, true);
});

test('@spec:AC-222 factual grounding still requires evidence after retrieval fix', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp.zapi_server import validate_live_grounding

blocked = validate_live_grounding("Botox e oferecido pela clinica e custa R$ 900.", evidence_count=0)
allowed = validate_live_grounding("Botox e oferecido pela clinica.", evidence_count=1)
print(json.dumps({"blocked": blocked, "allowed": allowed}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.blocked.passed, false);
  assert.equal(parsed.blocked.mode, 'HUMAN_HANDOFF_REQUIRED');
  assert.equal(parsed.blocked.reason, 'UNSUPPORTED_FACTUAL_CLAIM');
  assert.equal(parsed.allowed.passed, true);
});

test('@spec:AC-322 @spec:AC-324 @spec:AC-328 @spec:AC-332 live grounding blocks repeated known fields and premature booking language', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp.zapi_server import validate_live_grounding

state = {
    "operational_memory": {
        "patient_phone": "5571999990000",
        "preferred_time": "17:00",
        "preferred_location": "Brotas",
    },
    "scheduling_state": "CHECKING_AVAILABILITY",
    "correction_state": {"treatment_preference": "masculine", "acknowledge_once": False},
}
phone = validate_live_grounding("Qual o seu WhatsApp para cadastrar?", evidence_count=0, commercial_state=state)
time = validate_live_grounding("Voce prefere manha ou tarde?", evidence_count=0, commercial_state=state)
booking = validate_live_grounding("Ficou agendado para amanha as 17.", evidence_count=0, commercial_state=state)
correction = validate_live_grounding("Corrigindo: vou usar ser atendido.", evidence_count=0, commercial_state=state)
booked = validate_live_grounding("Ficou agendado para amanha as 17.", evidence_count=0, commercial_state={**state, "scheduling_state": "BOOKED"})
print(json.dumps({"phone": phone, "time": time, "booking": booking, "correction": correction, "booked": booked}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.phone.reason, 'REDUNDANT_PHONE_REQUEST');
  assert.equal(parsed.time.reason, 'REPEATED_KNOWN_OPERATIONAL_QUESTION');
  assert.equal(parsed.booking.reason, 'PREMATURE_BOOKING_CONFIRMATION');
  assert.equal(parsed.correction.reason, 'CORRECTION_REPETITION');
  assert.notEqual(parsed.booked.reason, 'PREMATURE_BOOKING_CONFIRMATION');
});

test('@spec:AC-330 @spec:AC-331 @spec:AC-332 Z-API live regenerates internal gap wording without inventing technique attributes', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

EVIDENCE = [
    {"id": "chunk-lentes", "organization_id": "org-a", "document_version_id": "ver-1", "content": "A clinica avalia tratamentos esteticos dentais conforme o caso e o resultado buscado pelo paciente."},
]

class LensRetrieval:
    def search(self, organization_id, query, limit=6):
        if organization_id == "org-a" and ("lente" in query.lower() or "resina" in query.lower() or "ceramica" in query.lower()):
            return EVIDENCE
        return []
    def closed_world_procedure_decision(self, organization_id, query):
        return None

class GapThenSafeTransport:
    def __init__(self):
        self.payloads = []
    def post_json(self, url, *, headers, payload):
        self.payloads.append(payload)
        if len(self.payloads) == 1:
            return {"id": "bad", "status": "completed", "output_text": "Não consigo confirmar por aqui se o Dr realiza resina e cerâmica."}
        return {"id": "safe", "status": "completed", "output_text": "A melhor opção é definida na avaliação, de acordo com seu caso e com o resultado que você busca. Posso seguir com a avaliação?"}

logs = []
provider = FakeWhatsAppProvider()
transport = GapThenSafeTransport()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(
            OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), transport),
            retrieval=LensRetrieval(),
        ),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
for message_id, text, moment in [
    ("lens-1", "Vocês fazem lente?", "100"),
    ("lens-2", "Dr faz resina e cerâmica?", "101"),
]:
    payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": message_id, "phone": "5571", "momment": moment, "text": {"message": text}}
    response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
    assert response.status_code == 200, response.body

final = provider.sent_texts[-1]["text"]
print(json.dumps({
  "final": final,
  "sentCount": len(provider.sent_texts),
  "modelCalls": len(transport.payloads),
  "reasons": [entry["details"].get("reason") for entry in logs if entry["stage"] == "grounding_failed"],
  "regenerated": any(entry["stage"] == "response_regeneration_started" for entry in logs),
  "handoff": any(entry["stage"] == "human_handoff_required" for entry in logs),
  "badPhrase": "não consigo confirmar" in final.lower(),
  "inventedBoth": "faz as duas" in final.lower() or "realiza as duas" in final.lower(),
  "clinicalExplanation": "resina" in final.lower() or "cerâmica" in final.lower(),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.sentCount, 2);
  assert.equal(parsed.modelCalls, 3);
  assert.deepEqual(parsed.reasons, ['INTERNAL_KNOWLEDGE_GAP_EXPOSED']);
  assert.equal(parsed.regenerated, true);
  assert.equal(parsed.handoff, false);
  assert.equal(parsed.badPhrase, false);
  assert.equal(parsed.inventedBoth, false);
  assert.equal(parsed.clinicalExplanation, false);
  assert.match(parsed.final, /avaliação|avaliacao/i);
});

test('@spec:AC-294 @spec:AC-295 @spec:AC-296 @spec:AC-297 @spec:AC-298 @spec:AC-299 @spec:AC-300 contextual commercial implant flow preserves state, retrieval, evidence, and grounding', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

EVIDENCE = [
    {"id": "chunk-implante", "organization_id": "org-a", "document_version_id": "ver-1", "content": "A clinica atua com implantes, proteses, periodontia e odontologia digital."},
    {"id": "chunk-digital", "organization_id": "org-a", "document_version_id": "ver-1", "content": "Diferenciais autorizados: Scanner Virtuo, visualizacao 3D e tomografia Cone Beam."},
]

class ContextAwareRetrieval:
    def __init__(self):
        self.queries = []
    def search(self, organization_id, query, limit=6):
        self.queries.append({"organizationId": organization_id, "query": query})
        if organization_id != "org-a":
            return []
        text = query.lower()
        if "implante" in text or "substituir" in text or "medo" in text:
            return EVIDENCE
        return []
    def closed_world_procedure_decision(self, organization_id, query):
        return None

class CommercialTransport:
    def __init__(self):
        self.payloads = []
        self.responses = [
            "Sou a Bruna da Clinica Carvalho e Tavares. Me conta o que voce quer resolver com implante?",
            "Ha quanto tempo esse dente esta faltando?",
            "Seu receio fica mais ligado ao procedimento ou ao pos-operatorio?",
            "Pelo que voce contou, faz sentido uma avaliacao para olhar a substituicao desse dente com cuidado. A clinica trabalha com odontologia digital e Scanner Virtuo. Quer que eu veja um horario?",
        ]
    def post_json(self, url, *, headers, payload):
        self.payloads.append(payload)
        index = min(len(self.payloads) - 1, len(self.responses) - 1)
        return {"id": f"resp-{index}", "status": "completed", "output_text": self.responses[index]}

logs = []
provider = FakeWhatsAppProvider()
retrieval = ContextAwareRetrieval()
transport = CommercialTransport()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(
            OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), transport),
            retrieval=retrieval,
        ),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    reject_out_of_order=True,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
messages = [
    ("impl-1", "Quero saber sobre implante", "100"),
    ("impl-2", "Substituir um dente", "101"),
    ("impl-3", "Tenho medo de fazer", "102"),
    ("impl-4", "Os dois", "103"),
]
for message_id, text, moment in messages:
    payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": message_id, "phone": "5571", "momment": moment, "text": {"message": text}}
    response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
    assert response.status_code == 200, response.body

commercial_states = [entry["details"] for entry in logs if entry["stage"] == "commercial_state_updated"]
final_state = commercial_states[-1]
final_response = provider.sent_texts[-1]["text"]
banned_fragments = ["Entendo", "Compreendo", "E compreensivel", "muitas pessoas", "vou te orientar", "opção A", "opcao A", "A)", "B)", "C)"]
print(json.dumps({
  "outboundCount": len(provider.sent_texts),
  "finalResponse": final_response,
  "finalState": final_state,
  "queries": retrieval.queries,
  "contextualLogs": [entry["details"] for entry in logs if entry["stage"] == "contextual_retrieval_query"],
  "reuseLogs": [entry["details"] for entry in logs if entry["stage"] == "conversation_evidence_reused"],
  "grounding": [entry["details"] for entry in logs if entry["stage"] == "grounding_result"],
  "regenerationFailed": any(entry["stage"] == "response_regeneration_failed" for entry in logs),
  "bannedHits": [fragment for fragment in banned_fragments if fragment in final_response],
  "storedEvidenceCount": len(adapter.store.outbound_messages[-1].metadata.get("conversationEvidence", [])),
  "previousEvidencePassed": bool(transport.payloads[-1]),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.outboundCount, 4);
  assert.equal(parsed.finalState.patient_need_summary.procedure_interest, 'implante');
  assert.equal(parsed.finalState.patient_need_summary.situation, 'substituir dente perdido');
  assert.equal(parsed.finalState.patient_need_summary.main_objection, 'medo');
  assert.equal(parsed.finalState.patient_need_summary.fear_topics, 'procedimento,pos_operatorio');
  assert.ok(parsed.finalState.discovery_depth > 0);
  assert.ok(parsed.finalState.discovery_information_gain >= 4);
  assert.equal(parsed.finalState.contextual_short_answer_resolved, true);
  assert.equal(parsed.finalState.objection_state, 'FEAR_OR_RISK');
  assert.equal(parsed.finalState.sales_stage, 'VALUE_BRIDGE');
  assert.equal(parsed.finalState.naturalness_policy, 'ANTI_ECHO_NO_FORCED_CHOICE');
  assert.match(parsed.queries.at(-1).query, /implante/i);
  assert.match(parsed.queries.at(-1).query, /medo/i);
  assert.match(parsed.queries.at(-1).query, /procedimento/i);
  assert.match(parsed.queries.at(-1).query, /pos/i);
  assert.equal(parsed.contextualLogs.at(-1).contextualShortAnswerResolved, true);
  assert.ok(parsed.reuseLogs.length >= 1);
  assert.ok(parsed.grounding.every((item) => item.passed === true));
  assert.equal(parsed.regenerationFailed, false);
  assert.deepEqual(parsed.bannedHits, []);
  assert.ok(parsed.storedEvidenceCount >= 1);
  assert.match(parsed.finalResponse, /Scanner Virtuo|odontologia digital/);
});

test('@spec:AC-295 @spec:AC-297 contextual short answers resolve without cross-org evidence reuse', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial.playbook import CommercialPlaybook
from ai_agent_runtime.sandbox_ids import DATASET_VERSION
from ai_agent_runtime.whatsapp.zapi_server import _contextual_retrieval_query, _reusable_conversation_evidence

playbook = CommercialPlaybook()
messages = [
    {"direction": "inbound", "text": "Quero saber sobre implante"},
    {"direction": "inbound", "text": "Substituir um dente"},
    {"direction": "inbound", "text": "Tenho medo de fazer"},
]
state = playbook.evaluate(
    messages,
    current_message="Os dois",
    previous_assistant_question="Seu receio fica mais ligado ao procedimento ou ao pos-operatorio?",
)
query = _contextual_retrieval_query(
    "Os dois",
    state.as_dict(),
    history_text=" ".join(item["text"] for item in messages),
    previous_assistant_question="Seu receio fica mais ligado ao procedimento ou ao pos-operatorio?",
)
stored = [
    {"id": "same", "organization_id": "org-a", "document_version_id": "v2", "content": "A clinica atua com implantes e odontologia digital.", "scopeTerms": ["implante"], "datasetVersion": DATASET_VERSION},
    {"id": "stale", "organization_id": "org-a", "document_version_id": "v1", "content": "Evidencia antiga de implante.", "scopeTerms": ["implante"]},
    {"id": "other", "organization_id": "org-b", "document_version_id": "v2", "content": "Outra organizacao fala de implante.", "scopeTerms": ["implante"], "datasetVersion": DATASET_VERSION},
]
print(json.dumps({
  "state": state.as_dict(),
  "query": query,
  "sameOrg": _reusable_conversation_evidence(stored, organization_id="org-a", query=query),
  "otherOrg": _reusable_conversation_evidence(stored, organization_id="org-c", query=query),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.state.contextual_short_answer_resolved, true);
  assert.equal(parsed.state.patient_need_summary.procedure_interest, 'implante');
  assert.equal(parsed.state.patient_need_summary.situation, 'substituir dente perdido');
  assert.equal(parsed.state.patient_need_summary.main_objection, 'medo');
  assert.equal(parsed.state.patient_need_summary.fear_topics, 'procedimento,pos_operatorio');
  assert.match(parsed.query, /implante/i);
  assert.match(parsed.query, /medo/i);
  assert.match(parsed.query, /procedimento/i);
  assert.equal(parsed.sameOrg.length, 1);
  assert.equal(parsed.sameOrg[0].id, 'same');
  assert.deepEqual(parsed.otherOrg, []);
});

test('@spec:AC-280 @spec:AC-281 @spec:AC-282 @spec:AC-283 Dr. Leonardo is active Z-API sandbox org and open catalog does not authorize absence', () => {
  const output = runPython(`
import json
import os
from urllib import parse
from ai_agent_runtime.sandbox.dataset import build_sandbox_dataset
from ai_agent_runtime.sandbox_ids import LEONARDO_ORG_ID, deterministic_sandbox_uuid
from ai_agent_runtime.whatsapp import ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import ZApiRuntimeRetrieval, _organization_commercial_config_from_env, _runtime_organization_id, request

ORG = deterministic_sandbox_uuid(LEONARDO_ORG_ID)

class Response:
    def __init__(self, rows):
        self.rows = rows
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def read(self):
        return json.dumps(self.rows).encode("utf-8")

def fake_urlopen(req, timeout=20):
    parsed = parse.urlparse(req.full_url)
    if parsed.path.endswith("/documents"):
        return Response([{"id": "doc-catalog", "organization_id": ORG, "document_type": "PROCEDURE_CATALOG"}])
    if parsed.path.endswith("/document_versions"):
        return Response([])
    return Response([])

request.urlopen = fake_urlopen
for key in ["AI_ASSISTANT_NAME", "AI_ASSISTANT_ROLE"]:
    os.environ.pop(key, None)
os.environ["AI_CLINIC_NAME"] = "Clinica Carvalho e Tavares Odontologia Integrada"
os.environ["AI_DOCTOR_NAME"] = "Dr. Leonardo Carvalho"
os.environ["AI_BUSINESS_HOURS"] = "segunda a sexta, 8h as 19h; sabado, 8h as 12h"
os.environ["AI_LOCATIONS"] = "Matatu|Pituba"

dataset = build_sandbox_dataset()
catalog = [doc for doc in dataset.documents if doc.document_type == "PROCEDURE_CATALOG"][0]
retrieval = ZApiRuntimeRetrieval(supabase_url="https://example.supabase.co", service_role_key="secret")
config = _organization_commercial_config_from_env()
print(json.dumps({
  "defaultOrg": ZApiWhatsAppConfig().organization_id,
  "runtimeOrg": _runtime_organization_id(LEONARDO_ORG_ID),
  "expectedRuntimeOrg": ORG,
  "datasetOrgs": [org.id for org in dataset.organizations],
  "catalogMode": catalog.knowledge_mode,
  "catalogComplete": catalog.closed_world_completeness_approved,
  "absenceDecision": retrieval.closed_world_procedure_decision(ORG, "Voces fazem transplante capilar?"),
  "clinicName": config.clinic_name,
  "doctorName": config.doctor_name,
  "locations": list(config.locations),
  "businessHours": config.business_hours,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.defaultOrg, 'sandbox-org-dr-leonardo-carvalho');
  assert.equal(parsed.runtimeOrg, parsed.expectedRuntimeOrg);
  assert.deepEqual(parsed.datasetOrgs, ['sandbox-org-dr-leonardo-carvalho', 'sandbox-org-boreal']);
  assert.equal(parsed.catalogMode, 'OPEN_WORLD');
  assert.equal(parsed.catalogComplete, false);
  assert.equal(parsed.absenceDecision, null);
  assert.equal(parsed.clinicName, 'Clinica Carvalho e Tavares Odontologia Integrada');
  assert.equal(parsed.doctorName, 'Dr. Leonardo Carvalho');
  assert.deepEqual(parsed.locations, ['Matatu', 'Pituba']);
  assert.equal(parsed.businessHours, 'segunda a sexta, 8h as 19h; sabado, 8h as 12h');
});

test('@spec:AC-284 @spec:AC-285 clinical urgency for Dr. Leonardo produces silent handoff before model call', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.state import AgentState
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator

class FailingTransport:
    def post_json(self, url, *, headers, payload):
        raise AssertionError("model should not be called for clinical urgency handoff")

logs = []
graph = AgentRuntimeGraph(
    response_generator=OpenAIWhatsAppResponseGenerator(OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), FailingTransport()), retrieval=None),
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
state = graph.run(AgentState(conversation_id="conv-urgency", organization_id="sandbox-org-dr-leonardo-carvalho", current_message="Estou com muita dor e meu implante esta sangrando."))
print(json.dumps({
  "decision": state.decision.value,
  "stage": state.stage.value,
  "response": state.response_text,
  "handoffReason": state.handoff_context["reason"],
  "modelCalled": any(entry["stage"] == "model_call_started" for entry in logs),
  "turn": [entry for entry in logs if entry["stage"] == "turn_classified"][-1]["details"],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.decision, 'HUMAN_HANDOFF_REQUIRED');
  assert.equal(parsed.stage, 'HANDOFF');
  assert.equal(parsed.response, null);
  assert.equal(parsed.handoffReason, 'POST_PROCEDURE_BLEEDING');
  assert.equal(parsed.modelCalled, false);
  assert.equal(parsed.turn.interpreted_intent, 'CLINICAL_URGENCY');
  assert.equal(parsed.turn.handoff_decision, 'HUMAN_HANDOFF_REQUIRED');
});

test('@spec:AC-388 audio transcript with clinical urgency follows text policy before model call', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.state import AgentState
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator

class FailingTransport:
    def post_json(self, url, *, headers, payload):
        raise AssertionError("model should not be called for clinical urgency from audio transcript")

logs = []
graph = AgentRuntimeGraph(
    response_generator=OpenAIWhatsAppResponseGenerator(OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), FailingTransport()), retrieval=None),
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
state = graph.run(AgentState(
    conversation_id="conv-audio-urgency",
    organization_id="sandbox-org-dr-leonardo-carvalho",
    current_message="coloquei um implante e esta sangrando",
    context={"currentMessageMetadata": {"sourceMessageType": "AUDIO", "transcript": "coloquei um implante e esta sangrando"}},
))
print(json.dumps({
  "decision": state.decision.value,
  "stage": state.stage.value,
  "response": state.response_text,
  "handoffReason": state.handoff_context["reason"],
  "modelCalled": any(entry["stage"] == "model_call_started" for entry in logs),
  "turn": [entry for entry in logs if entry["stage"] == "turn_classified"][-1]["details"],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.decision, 'HUMAN_HANDOFF_REQUIRED');
  assert.equal(parsed.stage, 'HANDOFF');
  assert.equal(parsed.response, null);
  assert.equal(parsed.handoffReason, 'POST_PROCEDURE_BLEEDING');
  assert.equal(parsed.modelCalled, false);
  assert.equal(parsed.turn.interpreted_intent, 'CLINICAL_URGENCY');
});

test('@spec:AC-389 audio transcript respects negation and asks clarification for unclear procedure', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.state import AgentState
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator

class Transport:
    def __init__(self): self.calls = 0
    def post_json(self, url, *, headers, payload):
        self.calls += 1
        return {"status": "completed", "output_text": "Entendi. Me conta qual procedimento voce quer avaliar?"}

transport = Transport()
logs = []
graph = AgentRuntimeGraph(
    response_generator=OpenAIWhatsAppResponseGenerator(OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), transport), retrieval=None),
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
negated = graph.run(AgentState(conversation_id="conv-neg", organization_id="sandbox-org-dr-leonardo-carvalho", current_message="nao esta sangrando"))
unclear = graph.run(AgentState(conversation_id="conv-unclear", organization_id="sandbox-org-dr-leonardo-carvalho", current_message="quanto custa [inaudivel]"))
print(json.dumps({
  "negatedDecision": negated.decision.value,
  "negatedHandoff": negated.handoff_context is not None,
  "unclearDecision": unclear.decision.value,
  "unclearResponse": unclear.response_text,
  "modelCalls": transport.calls,
  "clinicalTurns": [entry["details"] for entry in logs if entry["stage"] == "turn_classified"],
}))
`);
  const parsed = JSON.parse(output);
  assert.notEqual(parsed.negatedDecision, 'HUMAN_HANDOFF_REQUIRED');
  assert.equal(parsed.negatedHandoff, false);
  assert.equal(parsed.unclearDecision, 'ANSWER_GROUNDED');
  assert.match(parsed.unclearResponse, /qual procedimento/i);
  assert.equal(parsed.modelCalls, 1);
  assert.notEqual(parsed.clinicalTurns[0].interpreted_intent, 'CLINICAL_URGENCY');
  assert.equal(parsed.clinicalTurns[0].handoff_decision, 'NONE');
});

test('@spec:AC-291 Dr. Leonardo seeded retrieval supports grounded outbound for implant interest', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class SeededLeonardoRetrieval:
    def search(self, organization_id, query):
        return [{
            "id": "chunk-dr-leonardo-implant",
            "organization_id": organization_id,
            "document_version_id": "version-published",
            "content": "Fonte: Briefing_Assistente_Comercial_Dr_Leonardo_Carvalho.pdf. Dr. Leonardo Carvalho atua com implantes, odontologia digital e Scanner Virtuo."
        }]
    def closed_world_procedure_decision(self, organization_id, query):
        return None

class Transport:
    def post_json(self, url, *, headers, payload):
        return {
            "id": "resp",
            "status": "completed",
            "output_text": "O Dr. Leonardo Carvalho atua com implantes e odontologia digital. Para entender seu caso, voce perdeu esse dente ha muito tempo?"
        }

provider = FakeWhatsAppProvider()
logs = []
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "dfdcdff0-6d5f-58cc-9a83-2829820b7f8e"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(
            OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), Transport()),
            retrieval=SeededLeonardoRetrieval(),
        ),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "implant-1", "phone": "5571", "momment": "100", "text": {"message": "Oi, perdi um dente e queria saber mais sobre implante"}}
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
grounding = [entry for entry in logs if entry["stage"] == "grounding_result"][-1]["details"]
retrieval = [entry for entry in logs if entry["stage"] == "retrieval_completed"][-1]["details"]
print(json.dumps({
  "status": response.status_code,
  "decision": records[0].decision.value,
  "hitCount": retrieval["hitCount"],
  "grounding": grounding,
  "sentCount": len(provider.sent_texts),
  "sentText": provider.sent_texts[0]["text"],
  "outboundSent": any(entry["stage"] == "outbound_sent" for entry in logs),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.equal(parsed.decision, 'PROCESSED');
  assert.equal(parsed.hitCount, 1);
  assert.equal(parsed.grounding.passed, true);
  assert.equal(parsed.grounding.evidenceCount, 1);
  assert.equal(parsed.sentCount, 1);
  assert.equal(parsed.outboundSent, true);
  assert.match(parsed.sentText, /Dr\. Leonardo Carvalho/);
});

test('@spec:AC-292 @spec:AC-293 authorized organization config can ground opening but not procedure facts', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import OrganizationCommercialConfig
from ai_agent_runtime.whatsapp.zapi_server import validate_live_grounding

config = OrganizationCommercialConfig(
    assistant_name="Bruna",
    assistant_role="do atendimento",
    clinic_name="Clinica Carvalho e Tavares Odontologia Integrada",
    doctor_name="Dr. Leonardo Carvalho",
    locations=("Clinica Carvalho - Matatu", "Clinica Tavares - Pituba, sala 4022"),
    business_hours="segunda a sexta, 8h as 19h; sabado, 8h as 12h",
)
opening = validate_live_grounding("Oi! Aqui e a Bruna, do atendimento do Dr. Leonardo Carvalho.", evidence_count=0, organization_config=config)
location = validate_live_grounding("A Clinica Tavares fica na Pituba, sala 4022.", evidence_count=0, organization_config=config)
procedure = validate_live_grounding("O Dr. Leonardo Carvalho realiza implantes com odontologia digital.", evidence_count=0, organization_config=config)
print(json.dumps({"opening": opening, "location": location, "procedure": procedure}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.opening.passed, true);
  assert.equal(parsed.opening.configAuthorized, true);
  assert.equal(parsed.opening.mode, 'RESPONSE_CONSTRAINED_BY_AUTHORIZED_CONFIG');
  assert.equal(parsed.location.passed, true);
  assert.equal(parsed.location.configAuthorized, true);
  assert.equal(parsed.procedure.passed, false);
  assert.equal(parsed.procedure.reason, 'UNSUPPORTED_FACTUAL_CLAIM');
});

test('@spec:AC-228 @spec:AC-224 @spec:AC-246 offered Botox interest is treated as commercial progression, not encyclopedia-first handoff', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class BotoxRetrieval:
    def search(self, organization_id, query):
        return [{"id": "chunk-botox", "organization_id": organization_id, "document_version_id": "ver-1", "content": "Botox\\\\nPreenchimento labial\\\\nBlefaroplastia"}]
    def closed_world_procedure_decision(self, organization_id, query):
        return {"decision": "OFFERED", "procedure": "Botox"}

class CapturingTransport:
    def __init__(self):
        self.payloads = []
    def post_json(self, url, *, headers, payload):
        self.payloads.append(payload)
        return {"id": "resp-1", "status": "completed", "output_text": "Claro. O que mais te incomoda hoje: testa, entre as sobrancelhas ou ao redor dos olhos?"}

transport = CapturingTransport()
provider = FakeWhatsAppProvider()
logs = []
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), transport), retrieval=BotoxRetrieval()),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "sales-1", "phone": "5571", "momment": "100", "text": {"message": "Quero saber mais sobre botox"}}
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
system_prompt = transport.payloads[0]["input"][0]["content"]
print(json.dumps({
  "status": response.status_code,
  "decision": records[0].decision.value,
  "sentText": provider.sent_texts[0]["text"],
  "systemPrompt": system_prompt,
  "sentCount": len(provider.sent_texts),
  "groundingPassed": [entry for entry in logs if entry["stage"] == "grounding_result"][-1]["details"]["passed"],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.equal(parsed.decision, 'PROCESSED');
  assert.equal(parsed.sentCount, 1);
  assert.match(parsed.sentText, /\?/);
  assert.doesNotMatch(parsed.sentText, /^O Botox (é|e|consiste|funciona|utilizado)/i);
  assert.equal(parsed.groundingPassed, true);
  assert.match(parsed.systemPrompt, /vendedora consultiva/i);
  assert.match(parsed.systemPrompt, /no maximo uma pergunta principal/i);
  assert.match(parsed.systemPrompt, /descoberta comercial/i);
});

test('@spec:AC-229 @spec:AC-225 closed-world procedure absence returns authorized not-offered answer without handoff', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.state import AgentState

class CatalogRetrieval:
    def search(self, organization_id, query):
        return []
    def closed_world_procedure_decision(self, organization_id, query):
        return {"decision": "NOT_OFFERED", "procedure": "transplante capilar"}

class FailingTransport:
    def post_json(self, url, *, headers, payload):
        raise AssertionError("model should not be called for deterministic closed-world absence")

logs = []
graph = AgentRuntimeGraph(
    response_generator=OpenAIWhatsAppResponseGenerator(OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), FailingTransport()), retrieval=CatalogRetrieval()),
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
state = graph.run(AgentState(conversation_id="conv-1", organization_id="org-a", current_message="Vocês fazem transplante capilar?"))
print(json.dumps({"decision": state.decision.value, "response": state.response_text, "logs": logs}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.decision, 'ANSWER_GROUNDED');
  assert.match(parsed.response, /Nao, nao trabalhamos com transplante capilar/i);
  assert.equal(parsed.logs.some((entry) => entry.stage === 'model_call_started'), false);
  assert.ok(parsed.logs.some((entry) => entry.stage === 'closed_world_procedure_decision' && entry.details.decision === 'NOT_OFFERED'));
});

test('@spec:AC-230 @spec:AC-223 @spec:AC-226 @spec:AC-244 factual attribute missing for Botox produces silent handoff', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class BotoxOnlyRetrieval:
    def search(self, organization_id, query):
        return [{"id": "chunk-botox", "organization_id": organization_id, "document_version_id": "ver-1", "content": "Botox\\\\nPreenchimento labial\\\\nBlefaroplastia"}]
    def closed_world_procedure_decision(self, organization_id, query):
        return {"decision": "OFFERED", "procedure": "Botox"}

class FailingTransport:
    def post_json(self, url, *, headers, payload):
        raise AssertionError("model should not be called for unsupported factual attribute")

logs = []
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), FailingTransport()), retrieval=BotoxOnlyRetrieval()),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "attr-1", "phone": "5571", "momment": "100", "text": {"message": "Qual marca de botox vocês usam?"}}
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
print(json.dumps({
  "status": response.status_code,
  "decision": records[0].decision.value,
  "agentDecision": records[0].agent_decision,
  "hasOutbound": records[0].outbound is not None,
  "sentCount": len(provider.sent_texts),
  "handoffContext": records[0].handoff_context,
  "logs": logs,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.equal(parsed.decision, 'HUMAN_HANDOFF_REQUIRED');
  assert.equal(parsed.agentDecision, 'HUMAN_HANDOFF_REQUIRED');
  assert.equal(parsed.hasOutbound, false);
  assert.equal(parsed.sentCount, 0);
  assert.equal(parsed.handoffContext.reason, 'UNSUPPORTED_ATTRIBUTE');
  assert.equal(parsed.handoffContext.autonomyInterrupted, true);
  assert.ok(parsed.logs.some((entry) => entry.stage === 'unsupported_factual_question'));
  assert.ok(parsed.logs.some((entry) => entry.stage === 'outbound_suppressed'));
  assert.equal(parsed.logs.some((entry) => entry.stage === 'outbound_sent'), false);
});

test('@spec:AC-235 @spec:AC-238 @spec:AC-239 answer about visible skin marks is contextual and does not require handoff', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class ContextRetrieval:
    def __init__(self):
        self.queries = []
    def search(self, organization_id, query):
        self.queries.append(query)
        if "botox" in query.lower():
            return [{"id": "chunk-botox", "organization_id": organization_id, "document_version_id": "ver-1", "content": "Botox\\\\nPreenchimento labial\\\\nBlefaroplastia"}]
        return []
    def closed_world_procedure_decision(self, organization_id, query):
        if "botox" in query.lower():
            return {"decision": "OFFERED", "procedure": "Botox"}
        return None

class ScriptedTransport:
    def __init__(self):
        self.calls = []
        self.responses = [
            "Voce percebe mais quando movimenta ou as marcas ja ficam visiveis em repouso?",
            "Entendi. Ha quanto tempo essas marcas ja ficam visiveis?",
        ]
    def post_json(self, url, *, headers, payload):
        self.calls.append(payload)
        return {"id": f"resp-{len(self.calls)}", "status": "completed", "output_text": self.responses[len(self.calls) - 1]}

logs = []
retrieval = ContextRetrieval()
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), ScriptedTransport()), retrieval=retrieval),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
records_by_turn = []
for message_id, text, moment in [
    ("ctx-1", "Quero saber mais sobre botox", "100"),
    ("ctx-2", "marcas que ja ficam visiveis", "101"),
]:
    payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": message_id, "phone": "5571", "momment": moment, "text": {"message": text}}
    _, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
    records_by_turn.append(records[0])
turns = [entry for entry in logs if entry["stage"] == "turn_classified"]
print(json.dumps({
  "sentTexts": [item["text"] for item in provider.sent_texts],
  "runtimeCalls": adapter.runtime_calls,
  "secondDecision": records_by_turn[1].decision.value,
  "secondTurn": turns[-1]["details"],
  "unsupportedCount": len([entry for entry in logs if entry["stage"] == "unsupported_factual_question"]),
  "retrievalQueries": retrieval.queries,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.runtimeCalls, 2);
  assert.equal(parsed.sentTexts.length, 2);
  assert.equal(parsed.secondDecision, 'PROCESSED');
  assert.equal(parsed.secondTurn.turn_relation, 'ANSWER_TO_PREVIOUS_QUESTION');
  assert.equal(parsed.secondTurn.interpreted_intent, 'NEED_DISCOVERY');
  assert.equal(parsed.secondTurn.requires_evidence, false);
  assert.equal(parsed.secondTurn.handoff_decision, 'NONE');
  assert.equal(parsed.unsupportedCount, 0);
  assert.equal(parsed.retrievalQueries[0], 'Quero saber mais sobre botox');
  assert.match(parsed.retrievalQueries[1], /marcas que ja ficam visiveis/i);
  assert.match(parsed.retrievalQueries[1], /botox/i);
});

test('@spec:AC-236 @spec:AC-239 brand query still requires evidence and produces silent handoff', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class BotoxOnlyRetrieval:
    def search(self, organization_id, query):
        return [{"id": "chunk-botox", "organization_id": organization_id, "document_version_id": "ver-1", "content": "Botox\\\\nPreenchimento labial\\\\nBlefaroplastia"}]
    def closed_world_procedure_decision(self, organization_id, query):
        return {"decision": "OFFERED", "procedure": "Botox"}

class FailingTransport:
    def post_json(self, url, *, headers, payload):
        raise AssertionError("model should not be called for unsupported brand attribute")

logs = []
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), FailingTransport()), retrieval=BotoxOnlyRetrieval()),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "brand-1", "phone": "5571", "momment": "100", "text": {"message": "Qual marca de botox vocês usam?"}}
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
turn = [entry for entry in logs if entry["stage"] == "turn_classified"][-1]["details"]
print(json.dumps({
  "status": response.status_code,
  "decision": records[0].decision.value,
  "sentCount": len(provider.sent_texts),
  "turn": turn,
  "unsupportedReason": [entry["details"]["reason"] for entry in logs if entry["stage"] == "unsupported_attribute_reason"],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.equal(parsed.decision, 'HUMAN_HANDOFF_REQUIRED');
  assert.equal(parsed.sentCount, 0);
  assert.equal(parsed.turn.turn_relation, 'NEW_QUESTION');
  assert.equal(parsed.turn.interpreted_intent, 'ATTRIBUTE_QUERY');
  assert.equal(parsed.turn.requires_evidence, true);
  assert.equal(parsed.turn.handoff_decision, 'HUMAN_HANDOFF_REQUIRED');
  assert.deepEqual(parsed.unsupportedReason, ['ATTRIBUTE_WITHOUT_AUTHORIZED_EVIDENCE']);
});

test('@spec:AC-237 short choices and confirmations are classified as answers to the previous assistant question', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp.zapi_server import _classify_turn_context

examples = [
    ("testa", "E mais a testa ou entre as sobrancelhas?"),
    ("Quero fazer em breve.", "Voce quer fazer em breve ou esta pesquisando?"),
    ("sim", "Isso te incomoda ha algum tempo?"),
    ("nao", "Voce ja fez algum tratamento antes?"),
]
classified = [
    _classify_turn_context(answer, [], previous_assistant_question=question, stage="QUALIFICATION")
    for answer, question in examples
]
print(json.dumps(classified))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed.map((item) => item.turn_relation), [
    'ANSWER_TO_PREVIOUS_QUESTION',
    'ANSWER_TO_PREVIOUS_QUESTION',
    'ANSWER_TO_PREVIOUS_QUESTION',
    'ANSWER_TO_PREVIOUS_QUESTION',
  ]);
  assert.deepEqual(parsed.map((item) => item.interpreted_intent), [
    'NEED_DISCOVERY',
    'NEED_DISCOVERY',
    'NEED_DISCOVERY',
    'NEED_DISCOVERY',
  ]);
  assert.deepEqual(parsed.map((item) => item.requires_evidence), [false, false, false, false]);
  assert.deepEqual(parsed.map((item) => item.handoff_decision), ['NONE', 'NONE', 'NONE', 'NONE']);
});

test('@spec:AC-242 @spec:AC-245 @spec:AC-247 conversational zero-retrieval model factual claim is regenerated without handoff', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class EmptyRetrieval:
    def search(self, organization_id, query):
        return []
    def closed_world_procedure_decision(self, organization_id, query):
        return None

class ScriptedTransport:
    def __init__(self):
        self.payloads = []
        self.responses = [
            "Quando voce percebe mais isso?",
            "Botox suaviza linhas de expressao e costuma ter resultado natural.",
            "Entendi. Isso ja te incomoda ha quanto tempo?",
        ]
    def post_json(self, url, *, headers, payload):
        self.payloads.append(payload)
        return {"id": f"resp-{len(self.payloads)}", "status": "completed", "output_text": self.responses[len(self.payloads) - 1]}

transport = ScriptedTransport()
logs = []
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), transport), retrieval=EmptyRetrieval()),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
for message_id, text, moment in [
    ("safe-1", "Tenho interesse em melhorar meu sorriso", "100"),
    ("safe-2", "Ja fica visivel mesmo sem movimentar.", "101"),
]:
    payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": message_id, "phone": "5571", "momment": moment, "text": {"message": text}}
    response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
second_record = records[0]
retry_prompt = transport.payloads[2]["input"][1]["content"]
print(json.dumps({
  "status": response.status_code,
  "decision": second_record.decision.value,
  "sentTexts": [item["text"] for item in provider.sent_texts],
  "callCount": len(transport.payloads),
  "turnRequires": [entry["details"] for entry in logs if entry["stage"] == "turn_requires_evidence"],
  "responseRequires": [entry["details"] for entry in logs if entry["stage"] == "response_requires_evidence"],
  "origins": [entry["details"]["origin"] for entry in logs if entry["stage"] == "grounding_failure_origin"],
  "regenStarted": [entry["details"] for entry in logs if entry["stage"] == "response_regeneration_started"],
  "regenCompleted": len([entry for entry in logs if entry["stage"] == "response_regeneration_completed"]),
  "handoffCount": len([entry for entry in logs if entry["stage"] == "human_handoff_required"]),
  "retryPrompt": retry_prompt,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.equal(parsed.decision, 'PROCESSED');
  assert.equal(parsed.callCount, 3);
  assert.deepEqual(parsed.sentTexts, [
    'Quando voce percebe mais isso?',
    'Entendi. Isso ja te incomoda ha quanto tempo?',
  ]);
  assert.equal(parsed.turnRequires.at(-1).user_requires_evidence, false);
  assert.deepEqual(parsed.responseRequires.map((entry) => entry.response_contains_factual_claims), [false, true, false]);
  assert.deepEqual(parsed.origins, ['MODEL_INTRODUCED_UNSUPPORTED_FACT']);
  assert.equal(parsed.regenStarted[0].response_regeneration_mode, 'CONVERSATIONAL_NO_FACTS');
  assert.equal(parsed.regenCompleted, 1);
  assert.equal(parsed.handoffCount, 0);
  assert.match(parsed.retryPrompt, /Nao forneca qualquer fato sobre clinica/i);
  assert.match(parsed.retryPrompt, /procedimento, preco, resultado, tecnica/i);
  assert.match(parsed.retryPrompt, /Nao mencione falta de informacao/i);
  assert.match(parsed.retryPrompt, /RAG, retrieval, grounding/i);
});

test('@spec:AC-243 retry that still contains unsupported factual claim fails safely without outbound or false handoff', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import LiveRuntimeGenerationError, OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class EmptyRetrieval:
    def search(self, organization_id, query):
        return []
    def closed_world_procedure_decision(self, organization_id, query):
        return None

class ScriptedTransport:
    def __init__(self):
        self.responses = [
            "Quando voce percebe mais isso?",
            "Botox corrige marcas de repouso.",
            "O procedimento tem tecnica segura e resultado natural.",
        ]
    def post_json(self, url, *, headers, payload):
        return {"id": "resp", "status": "completed", "output_text": self.responses.pop(0)}

logs = []
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), ScriptedTransport()), retrieval=EmptyRetrieval()),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
for message_id, text, moment in [("fail-1", "Tenho interesse em melhorar meu sorriso", "100")]:
    payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": message_id, "phone": "5571", "momment": moment, "text": {"message": text}}
    handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
failed = False
error_type = None
status_code = None
try:
    payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "fail-2", "phone": "5571", "momment": "101", "text": {"message": "Ja fica visivel mesmo sem movimentar."}}
    response, _ = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
    status_code = response.status_code
except Exception as exc:
    failed = True
    error_type = type(exc).__name__
print(json.dumps({
  "failed": failed,
  "statusCode": status_code,
  "errorType": error_type,
  "sentTexts": [item["text"] for item in provider.sent_texts],
  "regenFailed": any(entry["stage"] == "response_regeneration_failed" for entry in logs),
  "runtimeFailed": any(entry["stage"] == "runtime_failed" for entry in logs),
  "handoffCount": len([entry for entry in logs if entry["stage"] == "human_handoff_required"]),
  "origins": [entry["details"]["origin"] for entry in logs if entry["stage"] == "grounding_failure_origin"],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.failed, false);
  assert.equal(parsed.statusCode, 500);
  assert.equal(parsed.errorType, null);
  assert.deepEqual(parsed.sentTexts, ['Quando voce percebe mais isso?']);
  assert.equal(parsed.regenFailed, true);
  assert.equal(parsed.runtimeFailed, true);
  assert.equal(parsed.handoffCount, 0);
  assert.deepEqual(parsed.origins, ['MODEL_INTRODUCED_UNSUPPORTED_FACT']);
});

test('@spec:AC-242 conversational happy path progresses without regeneration or handoff', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class EmptyRetrieval:
    def search(self, organization_id, query):
        return []
    def closed_world_procedure_decision(self, organization_id, query):
        return None

class ScriptedTransport:
    def post_json(self, url, *, headers, payload):
        return {"id": "resp", "status": "completed", "output_text": "Entendi. Isso te incomoda ha dois anos em quais momentos do dia?"}

logs = []
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), ScriptedTransport()), retrieval=EmptyRetrieval()),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "happy-1", "phone": "5571", "momment": "100", "text": {"message": "Isso me incomoda ha dois anos."}}
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
print(json.dumps({
  "status": response.status_code,
  "decision": records[0].decision.value,
  "sentCount": len(provider.sent_texts),
  "turnRequires": [entry["details"] for entry in logs if entry["stage"] == "turn_requires_evidence"][-1],
  "regenCount": len([entry for entry in logs if entry["stage"] == "response_regeneration_started"]),
  "handoffCount": len([entry for entry in logs if entry["stage"] == "human_handoff_required"]),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.equal(parsed.decision, 'PROCESSED');
  assert.equal(parsed.sentCount, 1);
  assert.equal(parsed.turnRequires.user_requires_evidence, false);
  assert.equal(parsed.regenCount, 0);
  assert.equal(parsed.handoffCount, 0);
});

test('@spec:AC-248 supported factual answer passes grounding without safe regeneration', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class PriceRetrieval:
    def search(self, organization_id, query):
        return [{"id": "chunk-price", "organization_id": organization_id, "document_version_id": "ver-1", "content": "Botox custa R$ 900 na Clinica A ficticia."}]
    def closed_world_procedure_decision(self, organization_id, query):
        return {"decision": "OFFERED", "procedure": "Botox"}

class PriceTransport:
    def post_json(self, url, *, headers, payload):
        return {"id": "resp", "status": "completed", "output_text": "Botox custa R$ 900 na Clinica A ficticia."}

logs = []
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), PriceTransport()), retrieval=PriceRetrieval()),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "price-1", "phone": "5571", "momment": "100", "text": {"message": "Quanto custa o botox?"}}
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
grounding = [entry for entry in logs if entry["stage"] == "grounding_result"][-1]["details"]
print(json.dumps({
  "status": response.status_code,
  "decision": records[0].decision.value,
  "sentText": provider.sent_texts[0]["text"],
  "grounding": grounding,
  "regenCount": len([entry for entry in logs if entry["stage"] == "response_regeneration_started"]),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.equal(parsed.decision, 'PROCESSED');
  assert.match(parsed.sentText, /R\$ 900/);
  assert.equal(parsed.grounding.passed, true);
  assert.equal(parsed.grounding.evidenceCount, 1);
  assert.equal(parsed.regenCount, 0);
});

test('@spec:AC-351 factual retrieval retries transient Supabase failure and succeeds grounded', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import LiveRuntimeHttpError, OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class FlakyRetrieval:
    def __init__(self): self.calls = 0
    def search(self, organization_id, query):
        self.calls += 1
        if self.calls == 1:
            raise LiveRuntimeHttpError(stage="retrieval", provider="supabase", status=None, endpoint="rest/v1/chunks", body={"message": "Connection reset by peer"}, code="ConnectionResetError")
        return [{"id": "eval-v2", "organization_id": organization_id, "document_version_id": "v2", "content": "Avaliacao gratuita: para casos de busca por procedimento, incluindo implante, lentes e outros procedimentos, a avaliacao e gratuita."}]
    def closed_world_procedure_decision(self, organization_id, query):
        return None

class Transport:
    def post_json(self, url, *, headers, payload):
        return {"id": "resp", "status": "completed", "output_text": "A avaliacao e gratuita para quem busca um procedimento."}

logs = []
retrieval = FlakyRetrieval()
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), Transport()), retrieval=retrieval),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "retry-1", "phone": "5571", "momment": "100", "text": {"message": "Quanto custa a avaliacao?"}}
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
print(json.dumps({
  "status": response.status_code,
  "decision": records[0].decision.value,
  "retrievalCalls": retrieval.calls,
  "sentCount": len(provider.sent_texts),
  "retryStarted": [entry["details"] for entry in logs if entry["stage"] == "retrieval_retry_started"],
  "retryAttempts": [entry["details"] for entry in logs if entry["stage"] == "retrieval_retry_attempt"],
  "retrySucceeded": [entry["details"] for entry in logs if entry["stage"] == "retrieval_retry_succeeded"],
  "grounding": [entry["details"] for entry in logs if entry["stage"] == "grounding_result"][-1],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.equal(parsed.decision, 'PROCESSED');
  assert.equal(parsed.retrievalCalls, 2);
  assert.equal(parsed.sentCount, 1);
  assert.equal(parsed.retryStarted.length, 1);
  assert.equal(parsed.retryAttempts[0].attempt, 2);
  assert.equal(parsed.retrySucceeded[0].attempt, 2);
  assert.equal(parsed.grounding.passed, true);
});

test('@spec:AC-352 deterministic Supabase error is not retried or masked', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import LiveRuntimeHttpError, OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class InvalidQueryRetrieval:
    def __init__(self): self.calls = 0
    def search(self, organization_id, query):
        self.calls += 1
        raise LiveRuntimeHttpError(stage="retrieval", provider="supabase", status=400, endpoint="rest/v1/chunks", body={"code": "PGRST100", "message": "invalid query"}, code="PGRST100")
    def closed_world_procedure_decision(self, organization_id, query):
        return None

class Transport:
    def post_json(self, url, *, headers, payload):
        raise AssertionError("model should not run after deterministic retrieval error")

logs = []
retrieval = InvalidQueryRetrieval()
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), Transport()), retrieval=retrieval),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "bad-query-1", "phone": "5571", "momment": "100", "text": {"message": "Quanto custa a avaliacao?"}}
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
failed = [entry["details"] for entry in logs if entry["stage"] == "retrieval_failed"][-1]
print(json.dumps({
  "status": response.status_code,
  "recordCount": len(records),
  "retrievalCalls": retrieval.calls,
  "sentCount": len(provider.sent_texts),
  "retryStarted": len([entry for entry in logs if entry["stage"] == "retrieval_retry_started"]),
  "failed": failed,
  "runtimeFailed": any(entry["stage"] == "runtime_failed" for entry in logs),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 500);
  assert.equal(parsed.recordCount, 0);
  assert.equal(parsed.retrievalCalls, 1);
  assert.equal(parsed.sentCount, 0);
  assert.equal(parsed.retryStarted, 0);
  assert.equal(parsed.failed.status, 400);
  assert.equal(parsed.failed.code, 'PGRST100');
  assert.equal(parsed.runtimeFailed, true);
});

test('@spec:AC-353 @spec:AC-354 affirmative appointment CTA skips retrieval and advances scheduling', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import OrganizationCommercialConfig
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class Retrieval:
    def __init__(self): self.calls = []
    def search(self, organization_id, query):
        self.calls.append(query)
        if len(self.calls) > 1:
            raise AssertionError("retrieval should be skipped for affirmative scheduling answer")
        return [{"id": "eval-v2", "organization_id": organization_id, "document_version_id": "v2", "content": "Avaliacao gratuita: para casos de busca por procedimento, incluindo implante, lentes e outros procedimentos, a avaliacao e gratuita. O valor dos procedimentos e informado apos avaliacao."}]
    def closed_world_procedure_decision(self, organization_id, query):
        return None

class Transport:
    def __init__(self): self.calls = 0
    def post_json(self, url, *, headers, payload):
        self.calls += 1
        return {"id": "resp-1", "status": "completed", "output_text": "A avaliacao e gratuita. O valor do procedimento e informado apos a avaliacao. Quer que eu solicite um horario para sua avaliacao?"}

logs = []
retrieval = Retrieval()
transport = Transport()
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(
            OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), transport),
            retrieval=retrieval,
            organization_config=OrganizationCommercialConfig(locations=("Matatu", "Pituba")),
        ),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    reject_out_of_order=True,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
for message_id, text, moment in [("sched-1", "Oi, quero colocar lentes. Quanto custa a avaliacao?", "100"), ("sched-2", "Sim", "101")]:
    payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": message_id, "phone": "5571", "momment": moment, "text": {"message": text}}
    response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
states = [entry["details"] for entry in logs if entry["stage"] == "commercial_state_updated"]
requirements = [entry["details"] for entry in logs if entry["stage"] == "TURN_EVIDENCE_REQUIREMENT"]
print(json.dumps({
  "status": response.status_code,
  "decision": records[0].decision.value,
  "retrievalCalls": retrieval.calls,
  "modelCalls": transport.calls,
  "sentTexts": [item["text"] for item in provider.sent_texts],
  "requirement": requirements[-1],
  "retrievalSkipped": [entry["details"] for entry in logs if entry["stage"] == "retrieval_skipped"][-1],
  "schedulingTransition": [entry["details"] for entry in logs if entry["stage"] == "scheduling_transition_resolved"][-1],
  "finalState": states[-1],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.equal(parsed.decision, 'PROCESSED');
  assert.equal(parsed.retrievalCalls.length, 1);
  assert.equal(parsed.modelCalls, 1);
  assert.equal(parsed.sentTexts.length, 2);
  assert.match(parsed.sentTexts[1], /Qual unidade voce prefere/);
  assert.equal(parsed.requirement.requires_retrieval, false);
  assert.equal(parsed.requirement.reason, 'OPERATIONAL_SCHEDULING_CONFIRMATION');
  assert.equal(parsed.retrievalSkipped.reason, 'OPERATIONAL_SCHEDULING_CONFIRMATION');
  assert.equal(parsed.schedulingTransition.next_best_action, 'SCHEDULE');
  assert.equal(parsed.schedulingTransition.scheduling_state, 'COLLECTING_REQUIRED_DATA');
});

test('@spec:AC-355 factual query with exhausted transient retrieval failure becomes controlled safe handoff', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import LiveRuntimeHttpError, OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class DownRetrieval:
    def __init__(self): self.calls = 0
    def search(self, organization_id, query):
        self.calls += 1
        raise LiveRuntimeHttpError(stage="retrieval", provider="supabase", status=None, endpoint="rest/v1/chunks", body={"message": "timed out"}, code="TimeoutError")
    def closed_world_procedure_decision(self, organization_id, query):
        return None

class Transport:
    def post_json(self, url, *, headers, payload):
        raise AssertionError("model must not invent fact without retrieval")

logs = []
retrieval = DownRetrieval()
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), Transport()), retrieval=retrieval),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "down-1", "phone": "5571", "momment": "100", "text": {"message": "Quanto custa o procedimento?"}}
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
record = records[0]
print(json.dumps({
  "status": response.status_code,
  "decision": record.decision.value,
  "agentDecision": record.agent_decision,
  "handoffReason": record.handoff_context["reason"],
  "retrievalCalls": retrieval.calls,
  "sentCount": len(provider.sent_texts),
  "retryExhausted": [entry["details"] for entry in logs if entry["stage"] == "retrieval_retry_exhausted"],
  "controlled": [entry["details"] for entry in logs if entry["stage"] == "controlled_retrieval_failure"],
  "runtimeFailed": any(entry["stage"] == "runtime_failed" for entry in logs),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.equal(parsed.decision, 'HUMAN_HANDOFF_REQUIRED');
  assert.equal(parsed.agentDecision, 'HUMAN_HANDOFF_REQUIRED');
  assert.equal(parsed.handoffReason, 'RETRIEVAL_UNAVAILABLE_FOR_FACTUAL_QUERY');
  assert.equal(parsed.retrievalCalls, 3);
  assert.equal(parsed.sentCount, 0);
  assert.equal(parsed.retryExhausted[0].attempts, 3);
  assert.equal(parsed.controlled[0].decision, 'HUMAN_HANDOFF_REQUIRED');
  assert.equal(parsed.runtimeFailed, false);
});

test('@spec:AC-356 @spec:AC-357 @spec:AC-358 commercial fear state is patient-only and scoped per conversation', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial.playbook import CommercialPlaybook

playbook = CommercialPlaybook()
assistant_mentions_procedure = playbook.evaluate(
    [{"direction": "inbound", "text": "Quero colocar lentes"}],
    current_message="Sim",
    previous_assistant_question="Quer que eu solicite um horario para avaliacao do procedimento?",
)
assistant_mentions_fear = playbook.evaluate(
    [{"direction": "inbound", "text": "Quero saber sobre implante"}, {"direction": "inbound", "text": "Tenho medo do procedimento"}],
    current_message="Os dois",
    previous_assistant_question="Seu medo fica mais ligado ao procedimento ou ao pos-operatorio?",
)
assistant_only_fear = playbook.evaluate(
    [{"direction": "inbound", "text": "Quero saber sobre implante"}],
    current_message="Sim",
    previous_assistant_question="Se voce tiver medo do procedimento, posso te explicar melhor?",
)
explicit_patient = playbook.evaluate(
    [{"direction": "inbound", "text": "Quero saber sobre implante"}],
    current_message="Tenho medo do procedimento",
)
conversation_a = playbook.evaluate([], current_message="Tenho medo do procedimento")
conversation_b = playbook.evaluate([], current_message="Sim", previous_assistant_question="Quer que eu solicite um horario para avaliacao do procedimento?")
print(json.dumps({
  "assistantProcedure": assistant_mentions_procedure.as_dict(),
  "assistantFearQuestion": assistant_mentions_fear.as_dict(),
  "assistantOnlyFear": assistant_only_fear.as_dict(),
  "explicitPatient": explicit_patient.as_dict(),
  "conversationA": conversation_a.as_dict(),
  "conversationB": conversation_b.as_dict(),
}))
`);
  const parsed = JSON.parse(output);
  assert.notEqual(parsed.assistantProcedure.objection_state, 'FEAR_OR_RISK');
  assert.equal(parsed.assistantProcedure.patient_need_summary.fear_topics, undefined);
  assert.equal(parsed.assistantFearQuestion.objection_state, 'FEAR_OR_RISK');
  assert.equal(parsed.assistantFearQuestion.patient_need_summary.fear_topics, 'procedimento,pos_operatorio');
  assert.notEqual(parsed.assistantOnlyFear.objection_state, 'FEAR_OR_RISK');
  assert.equal(parsed.assistantOnlyFear.patient_need_summary.fear_topics, undefined);
  assert.equal(parsed.explicitPatient.objection_state, 'FEAR_OR_RISK');
  assert.equal(parsed.explicitPatient.patient_need_summary.fear_topics, 'procedimento');
  assert.equal(parsed.conversationA.objection_state, 'FEAR_OR_RISK');
  assert.notEqual(parsed.conversationB.objection_state, 'FEAR_OR_RISK');
  assert.equal(parsed.conversationB.patient_need_summary.fear_topics, undefined);
});

test('@spec:AC-360 @spec:AC-361 @spec:AC-362 @spec:AC-363 introduction and answered facts are persisted after outbound and not repeated in scheduling', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import OrganizationCommercialConfig
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class Retrieval:
    def __init__(self): self.calls = []
    def search(self, organization_id, query):
        self.calls.append(query)
        return [{"id": "eval-v2", "organization_id": organization_id, "document_version_id": "briefing-v2", "content": "Avaliacao gratuita: para casos de busca por procedimento, incluindo implante e lentes, a avaliacao e gratuita. O valor dos procedimentos e informado apos avaliacao."}]
    def closed_world_procedure_decision(self, organization_id, query):
        return None

class Transport:
    def __init__(self): self.calls = 0
    def post_json(self, url, *, headers, payload):
        self.calls += 1
        if self.calls == 1:
            return {"id": "resp-1", "status": "completed", "output_text": "Oi! Aqui e a Bruna, do atendimento do Dr. Leonardo. A avaliacao e gratuita. Quer que eu veja um horario para voce?"}
        raise AssertionError("model should not run for deterministic scheduling acceptance")

logs = []
store = InMemoryWhatsAppStore()
retrieval = Retrieval()
transport = Transport()
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=store,
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(
            OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), transport),
            retrieval=retrieval,
            organization_config=OrganizationCommercialConfig(assistant_name="Bruna", assistant_role="atendimento", doctor_name="Dr. Leonardo", locations=("Matatu", "Pituba")),
        ),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
for message_id, text in [("intro-1", "Oi, quero colocar lentes. Quanto custa a avaliacao?"), ("intro-2", "Quero")]:
    payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": message_id, "phone": "5571", "momment": message_id[-1], "text": {"message": text}}
    response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
last = store.last_outbound_for(records[0].inbound.conversation_id)
states = [entry["details"] for entry in logs if entry["stage"] == "commercial_state_updated"]
print(json.dumps({
  "status": response.status_code,
  "sentTexts": [item["text"] for item in provider.sent_texts],
  "transportCalls": transport.calls,
  "retrievalCalls": len(retrieval.calls),
  "metadata": last.metadata,
  "firstShouldIntroduce": states[0]["should_introduce"],
  "secondShouldIntroduce": states[-1]["should_introduce"],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.equal(parsed.firstShouldIntroduce, true);
  assert.equal(parsed.secondShouldIntroduce, false);
  assert.equal(parsed.metadata.assistantIntroduced, true);
  assert.equal(parsed.metadata.answeredFacts.evaluation_price.value, 'free');
  assert.equal(parsed.transportCalls, 1);
  assert.equal(parsed.retrievalCalls, 1);
  assert.match(parsed.sentTexts[0], /avaliacao e gratuita/i);
  assert.doesNotMatch(parsed.sentTexts[1], /gratuita|gratis/i);
});

test('@spec:AC-360 stale inbound history without assistant presentation metadata still introduces once', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import OrganizationCommercialConfig
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, InboundMessage, OrganizationResolver, WhatsAppChannelAdapter, WhatsAppMessageType, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class Transport:
    def post_json(self, url, *, headers, payload):
        return {"id": "resp-1", "status": "completed", "output_text": "Oi! Aqui e a Bruna. Me conta o que voce busca melhorar?"}

store = InMemoryWhatsAppStore()
conversation_id = store.conversation_id_for(organization_id="org-a", channel="whatsapp", contact_external_id="5571")
store.messages_by_conversation[conversation_id] = [
    InboundMessage(id="old-1", provider_message_id="old-1", organization_id="org-a", conversation_id=conversation_id, contact_external_id="5571", type=WhatsAppMessageType.TEXT, text="historico antigo", timestamp="1"),
    InboundMessage(id="old-2", provider_message_id="old-2", organization_id="org-a", conversation_id=conversation_id, contact_external_id="5571", type=WhatsAppMessageType.TEXT, text="mais historico", timestamp="2"),
]
logs = []
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=store,
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(
            OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), Transport()),
            retrieval=None,
            organization_config=OrganizationCommercialConfig(assistant_name="Bruna"),
        ),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "stale-1", "phone": "5571", "momment": "3", "text": {"message": "Oi, quero saber sobre lentes"}}
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
states = [entry["details"] for entry in logs if entry["stage"] == "commercial_state_updated"]
last = store.last_outbound_for(conversation_id)
print(json.dumps({"status": response.status_code, "shouldIntroduce": states[-1]["should_introduce"], "metadata": last.metadata}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.equal(parsed.shouldIntroduce, true);
  assert.equal(parsed.metadata.assistantIntroduced, true);
});

test('@spec:AC-367 @spec:AC-369 @spec:AC-371 registration turn skips RAG, asks only missing fields, and avoids confirmation loop', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import OrganizationCommercialConfig
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class Retrieval:
    def search(self, organization_id, query):
        raise AssertionError("registration-only turn must skip retrieval")
    def closed_world_procedure_decision(self, organization_id, query):
        raise AssertionError("registration-only turn must skip retrieval")

class Transport:
    def post_json(self, url, *, headers, payload):
        raise AssertionError("registration-only turn should be deterministic")

logs = []
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(
            OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), Transport()),
            retrieval=Retrieval(),
            organization_config=OrganizationCommercialConfig(locations=("Matatu", "Pituba")),
        ),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "reg-1", "phone": "5571", "momment": "10", "text": {"message": "Fernando Augusto, fernando@gmail.com, 07693271502, 15125843-02, 17727390, rua praia"}}
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
states = [entry["details"] for entry in logs if entry["stage"] == "commercial_state_updated"]
requirements = [entry["details"] for entry in logs if entry["stage"] == "TURN_EVIDENCE_REQUIREMENT"]
print(json.dumps({
  "status": response.status_code,
  "sent": provider.sent_texts[-1]["text"],
  "state": states[-1],
  "requirement": requirements[-1],
  "skipped": any(entry["stage"] == "retrieval_skipped" for entry in logs),
  "memoryLog": any(entry["stage"] == "operational_memory_updated" for entry in logs),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.equal(parsed.requirement.reason, 'OPERATIONAL_NO_RAG');
  assert.equal(parsed.skipped, true);
  assert.equal(parsed.memoryLog, true);
  assert.deepEqual(parsed.state.missing_required_fields, ['address_number', 'address_neighborhood', 'address_city', 'address_state']);
  assert.match(parsed.sent, /numero, bairro, cidade e estado/i);
  assert.doesNotMatch(parsed.sent, /RG|CEP|nome|e-mail/i);
  assert.doesNotMatch(parsed.sent, /correto|confirma/i);
  assert.doesNotMatch(parsed.sent, /gratuita|gratis/i);
});

test('@spec:AC-391 @spec:AC-392 @spec:AC-396 @spec:AC-397 @spec:AC-398 stale commercial context does not hijack greeting, identity, or acknowledgement', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator

class Retrieval:
    def __init__(self):
        self.queries = []
    def search(self, organization_id, query, limit=6):
        self.queries.append(query)
        if "lente" in query.lower() or "avaliacao" in query.lower():
            return [{"id": "chunk-lentes", "organization_id": organization_id, "document_version_id": "v2", "content": "O valor da avaliacao e gratuito para casos de busca por procedimento, incluindo lentes."}]
        return []
    def closed_world_procedure_decision(self, organization_id, query):
        return None

class Transport:
    def __init__(self):
        self.payloads = []
    def post_json(self, url, *, headers, payload):
        self.payloads.append(payload)
        if len(self.payloads) > 1:
            raise AssertionError("model should not be called for respond-only neutral turns")
        return {"id": "resp-1", "status": "completed", "output_text": "A avaliacao e gratuita. Quer que eu veja um horario para voce?"}

logs = []
provider = FakeWhatsAppProvider()
retrieval = Retrieval()
transport = Transport()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(
            OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), transport),
            retrieval=retrieval,
        ),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
for event in [
    {"providerAccountId": "clinic-a", "providerMessageId": "m1", "contactExternalId": "5571", "type": "TEXT", "text": "Oi, quero colocar lentes. Quanto custa a avaliacao?", "timestamp": "100"},
    {"providerAccountId": "clinic-a", "providerMessageId": "m2", "contactExternalId": "5571", "type": "TEXT", "text": "Ola", "timestamp": "3700"},
    {"providerAccountId": "clinic-a", "providerMessageId": "m3", "contactExternalId": "5571", "type": "TEXT", "text": "Qual seu nome?", "timestamp": "3705"},
    {"providerAccountId": "clinic-a", "providerMessageId": "m4", "contactExternalId": "5571", "type": "TEXT", "text": "Obrigado", "timestamp": "3710"},
]:
    adapter.process_event(event)

states = [entry["details"] for entry in logs if entry["stage"] == "commercial_state_updated"]
respond_only = [entry["details"] for entry in logs if entry["stage"] == "current_turn_response_only"]
print(json.dumps({
  "outbounds": [item["text"] for item in provider.sent_texts],
  "modelCalls": len(transport.payloads),
  "retrievalQueries": retrieval.queries,
  "states": states[-4:],
  "respondOnly": respond_only,
}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.modelCalls, 1);
  assert.equal(parsed.outbounds.length, 4);
  assert.match(parsed.outbounds[0], /avaliacao e gratuita/i);
  for (const text of parsed.outbounds.slice(1)) {
    assert.doesNotMatch(text, /lentes|avaliacao gratuita|agendar|horario|discovery/i);
  }
  assert.match(parsed.outbounds[1], /como posso te ajudar/i);
  assert.match(parsed.outbounds[2], /Sou/i);
  assert.match(parsed.outbounds[3], /Por nada|precisar/i);
  assert.equal(parsed.retrievalQueries.length, 1);
  assert.equal(parsed.states.at(-3).current_turn_intent, 'GREETING');
  assert.equal(parsed.states.at(-3).context_continuity, 'NEW_NEUTRAL_TURN');
  assert.equal(parsed.states.at(-3).next_best_action, 'RESPOND_ONLY');
  assert.equal(parsed.states.at(-2).current_turn_intent, 'IDENTITY_QUERY');
  assert.equal(parsed.states.at(-2).context_continuity, 'SIDE_QUERY');
  assert.equal(parsed.states.at(-2).persistent_memory.procedure_interest, 'lentes');
  assert.equal(parsed.states.at(-2).active_topic, null);
  assert.equal(parsed.states.at(-1).current_turn_intent, 'ACKNOWLEDGEMENT');
  assert.ok(parsed.respondOnly.length >= 3);
});

test('@spec:AC-393 @spec:AC-394 scheduling continuation remains semantic instead of time-only', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook, OrganizationCommercialConfig
from ai_agent_runtime.whatsapp.zapi_server import _deterministic_scheduling_response

playbook = CommercialPlaybook()
config = OrganizationCommercialConfig()
short = playbook.evaluate(
    [{"direction": "inbound", "text": "Quero colocar lentes"}, {"direction": "inbound", "text": "Quero"}],
    current_message="Quero",
    previous_assistant_question="A avaliacao e gratuita. Quer que eu veja um horario para sua avaliacao?",
    current_message_at="110",
    previous_assistant_message_at="100",
).as_dict()
late = playbook.evaluate(
    [{"direction": "inbound", "text": "Quero colocar lentes"}, {"direction": "inbound", "text": "Pode marcar para amanha"}],
    current_message="Pode marcar para amanha",
    previous_assistant_question="A avaliacao e gratuita. Quer que eu veja um horario para sua avaliacao?",
    current_message_at="7300",
    previous_assistant_message_at="100",
).as_dict()
short_response = _deterministic_scheduling_response("Quero", short, previous_assistant_question="A avaliacao e gratuita. Quer que eu veja um horario para sua avaliacao?", organization_config=config)
late_response = _deterministic_scheduling_response("Pode marcar para amanha", late, previous_assistant_question="A avaliacao e gratuita. Quer que eu veja um horario para sua avaliacao?", organization_config=config)
print(json.dumps({"short": short, "late": late, "shortResponse": short_response, "lateResponse": late_response}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.short.context_continuity, 'STRONG_CONTINUATION');
  assert.equal(parsed.short.next_best_action, 'SCHEDULE');
  assert.match(parsed.shortResponse, /dia e horario|unidade/i);
  assert.equal(parsed.late.context_continuity, 'STRONG_CONTINUATION');
  assert.equal(parsed.late.context_age_seconds, 7200);
  assert.equal(parsed.late.next_best_action, 'SCHEDULE');
  assert.match(parsed.lateResponse, /horario|unidade|verificar/i);
});

test('@spec:AC-395 topic change and factual query use current active topic instead of old procedure', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook
from ai_agent_runtime.whatsapp.zapi_server import _contextual_retrieval_query

messages = [{"direction": "inbound", "text": "Quero colocar lentes"}, {"direction": "inbound", "text": "Voces fazem implante?"}]
state = CommercialPlaybook().evaluate(messages, current_message="Voces fazem implante?").as_dict()
query = _contextual_retrieval_query("Voces fazem implante?", state, history_text=" ".join(item["text"] for item in messages), previous_assistant_question="")
print(json.dumps({"state": state, "query": query}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.state.current_turn_intent, 'TOPIC_CHANGE');
  assert.equal(parsed.state.context_continuity, 'TOPIC_CHANGE');
  assert.equal(parsed.state.active_topic, 'implante');
  assert.match(parsed.query, /implante/i);
  assert.doesNotMatch(parsed.query, /lentes/i);
});

test('@spec:AC-399 audio transcript follows current-turn-first identity behavior', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.state import AgentState
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator

class Transport:
    def post_json(self, url, *, headers, payload):
        raise AssertionError("model should not be called for audio identity side query")

logs = []
state = AgentState(
    conversation_id="conv-audio",
    organization_id="org-a",
    current_message="qual seu nome?",
    messages=[{"direction": "inbound", "text": "Quero falar de implante"}],
    context={
        "previousAssistantQuestion": "Quer que eu veja um horario?",
        "currentMessageMetadata": {"sourceMessageType": "AUDIO", "transcript": "qual seu nome?"},
        "organizationConfig": {"assistant_name": "Bruna", "doctor_name": "Dr. Leonardo"},
    },
)
result = AgentRuntimeGraph(
    response_generator=OpenAIWhatsAppResponseGenerator(OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), Transport())),
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
).run(state)
print(json.dumps({"response": result.response_text, "state": result.context["commercialState"], "logs": logs}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.match(parsed.response, /Bruna|Leonardo/);
  assert.doesNotMatch(parsed.response, /implante|avaliacao|agendar|horario/i);
  assert.equal(parsed.state.current_turn_intent, 'IDENTITY_QUERY');
  assert.equal(parsed.state.context_continuity, 'SIDE_QUERY');
  assert.equal(parsed.state.next_best_action, 'RESPOND_ONLY');
});

test('@spec:AC-401 @spec:AC-402 @spec:AC-403 NEW_NEUTRAL_TURN OTHER short-circuits stale retrieval and answered facts echo', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.state import AgentState
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator, _contextual_retrieval_query

class Retrieval:
    def search(self, organization_id, query, limit=6):
        raise AssertionError("retrieval should be skipped for neutral OTHER stale turn")
    def closed_world_procedure_decision(self, organization_id, query):
        raise AssertionError("catalog should be skipped for neutral OTHER stale turn")

class Transport:
    def post_json(self, url, *, headers, payload):
        raise AssertionError("model should not be called for neutral OTHER stale turn")

logs = []
state = AgentState(
    conversation_id="conv-neutral",
    organization_id="org-a",
    current_message="TESTE123",
    messages=[
        {"direction": "inbound", "text": "Oi, quero colocar lentes."},
        {"direction": "inbound", "text": "Quanto custa a avaliacao?"},
        {"direction": "assistant", "text": "A avaliacao para lentes e gratuita. Quer que eu veja um horario?"},
    ],
    context={
        "previousAssistantQuestion": "A avaliacao para lentes e gratuita. Quer que eu veja um horario?",
        "answeredFacts": {"evaluation_price": {"value": "free", "knowledgeVersion": "v2"}},
        "currentMessageAt": "1786695752889",
        "previousAssistantMessageAt": "1786692152889",
    },
)
result = AgentRuntimeGraph(
    response_generator=OpenAIWhatsAppResponseGenerator(
        OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), Transport()),
        retrieval=Retrieval(),
    ),
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
).run(state)
commercial_state = result.context["commercialState"]
query = _contextual_retrieval_query(
    "TESTE123",
    commercial_state,
    history_text="Oi quero colocar lentes Quanto custa a avaliacao",
    previous_assistant_question="A avaliacao para lentes e gratuita. Quer que eu veja um horario?",
)
print(json.dumps({
  "response": result.response_text,
  "state": commercial_state,
  "query": query,
  "stages": [entry["stage"] for entry in logs],
  "requirement": [entry["details"] for entry in logs if entry["stage"] == "TURN_EVIDENCE_REQUIREMENT"][-1],
}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.state.current_turn_intent, 'OTHER');
  assert.equal(parsed.state.context_continuity, 'NEW_NEUTRAL_TURN');
  assert.equal(parsed.state.next_best_action, 'RESPOND_ONLY');
  assert.equal(parsed.state.active_topic, null);
  assert.equal(parsed.state.context_age_seconds, 3600);
  assert.equal(parsed.query, 'TESTE123');
  assert.equal(parsed.requirement.requires_retrieval, false);
  assert.equal(parsed.requirement.reason, 'CURRENT_TURN_RESPOND_ONLY');
  assert.ok(parsed.stages.includes('retrieval_skipped'));
  assert.ok(parsed.stages.includes('current_turn_response_only'));
  assert.doesNotMatch(parsed.response, /lentes|avaliacao|gratuita|horario|agendar|nome completo/i);
});
