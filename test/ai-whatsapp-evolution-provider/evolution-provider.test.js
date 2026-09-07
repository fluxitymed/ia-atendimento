'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { readFileSync } = require('node:fs');

function runPython(source, env = {}) {
  const result = spawnSync('python3', ['-c', source], {
    cwd: process.cwd(),
    env: { ...process.env, ...env, PYTHONPATH: 'src' },
    encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout.trim();
}

test('@spec:AC-156 @spec:AC-158 @spec:AC-175 Evolution provider implements WhatsAppProvider and factory preserves Meta', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import (
    EvolutionWhatsAppConfig,
    EvolutionWhatsAppProvider,
    MetaWhatsAppCloudProvider,
    MetaWhatsAppConfig,
    WhatsAppProvider,
    build_whatsapp_provider,
)

evolution = build_whatsapp_provider("evolution", evolution_config=EvolutionWhatsAppConfig(base_url="http://evo", api_key="k", instance_name="inst"))
meta = build_whatsapp_provider("meta", meta_config=MetaWhatsAppConfig(access_token="m", phone_number_id="phone"))
print(json.dumps({
  "evolutionIsProvider": isinstance(evolution, WhatsAppProvider),
  "evolutionClass": evolution.__class__.__name__,
  "metaIsProvider": isinstance(meta, WhatsAppProvider),
  "metaClass": meta.__class__.__name__,
  "metaStillExists": MetaWhatsAppCloudProvider.__name__,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.evolutionIsProvider, true);
  assert.equal(parsed.evolutionClass, 'EvolutionWhatsAppProvider');
  assert.equal(parsed.metaIsProvider, true);
  assert.equal(parsed.metaClass, 'MetaWhatsAppCloudProvider');
  assert.equal(parsed.metaStillExists, 'MetaWhatsAppCloudProvider');
});

test('@spec:AC-157 Evolution config is env-driven and .env.example does not contain real secrets', () => {
  const output = runPython(`
import json, os
from ai_agent_runtime.whatsapp import EvolutionWhatsAppConfig

os.environ.update({
  "WHATSAPP_PROVIDER": "evolution",
  "EVOLUTION_API_BASE_URL": "https://evolution.local",
  "EVOLUTION_API_KEY": "test-secret-value",
  "EVOLUTION_INSTANCE_NAME": "sandbox-instance",
  "EVOLUTION_WEBHOOK_SECRET": "webhook-secret-value",
  "EVOLUTION_PUBLIC_WEBHOOK_URL": "https://public.example",
  "EVOLUTION_ORGANIZATION_ID": "org-sandbox",
})
cfg = EvolutionWhatsAppConfig.from_env()
print(json.dumps({"cfg": cfg.__dict__, "missing": cfg.missing_for_live()}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.cfg.provider, 'evolution');
  assert.equal(parsed.cfg.base_url, 'https://evolution.local');
  assert.equal(parsed.cfg.instance_name, 'sandbox-instance');
  assert.equal(parsed.cfg.organization_id, 'org-sandbox');
  assert.deepEqual(parsed.missing, []);
  const envExample = readFileSync('.env.example', 'utf8');
  for (const key of ['EVOLUTION_API_BASE_URL=', 'EVOLUTION_API_KEY=', 'EVOLUTION_INSTANCE_NAME=', 'EVOLUTION_WEBHOOK_SECRET=', 'WHATSAPP_PROVIDER=evolution']) {
    assert.match(envExample, new RegExp(key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
  assert.doesNotMatch(envExample, /test-secret-value|webhook-secret-value/);
});

test('@spec:AC-159 @spec:AC-169 @spec:AC-170 @spec:AC-171 Evolution provider calls documented endpoints', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import EvolutionWhatsAppConfig, EvolutionWhatsAppProvider

class FakeTransport:
    def __init__(self):
        self.calls = []
    def request_json(self, method, path, *, base_url, api_key, payload=None, query=None):
        self.calls.append({"method": method, "path": path, "baseUrl": base_url, "apiKey": api_key, "payload": payload})
        return {"key": {"id": f"id-{len(self.calls)}"}, "state": "open"}

transport = FakeTransport()
provider = EvolutionWhatsAppProvider(
    config=EvolutionWhatsAppConfig(
        base_url="https://evolution.example",
        api_key="secret-key",
        instance_name="clinic-a",
        webhook_secret="hook-secret",
        public_webhook_url="https://public.example/webhooks/evolution/whatsapp",
    ),
    transport=transport,
)
sent = provider.send_text(organization_id="org-a", contact_external_id="5571999990000", text="Oi", conversation_id="conv-a")
state = provider.connection_state()
created = provider.create_instance()
connected = provider.connect_instance()
webhook = provider.set_webhook()
print(json.dumps({"sent": sent, "state": state, "created": created, "connected": connected, "webhook": webhook, "calls": transport.calls}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.sent.providerMessageId, 'id-1');
  assert.deepEqual(parsed.calls.map((call) => `${call.method} ${call.path}`), [
    'POST /message/sendText/clinic-a',
    'GET /instance/connectionState/clinic-a',
    'POST /instance/create',
    'GET /instance/connect/clinic-a',
    'POST /webhook/set/clinic-a',
  ]);
  assert.deepEqual(parsed.calls[0].payload, { number: '5571999990000', text: 'Oi' });
  assert.equal(parsed.calls[4].payload.webhook.headers['x-evolution-webhook-secret'], 'hook-secret');
  assert.equal(parsed.calls.every((call) => call.apiKey === 'secret-key'), true);
});

test('@spec:AC-160 @spec:AC-174 Evolution errors redact API key and webhook secret', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp.evolution import EvolutionApiError, EvolutionWhatsAppConfig, EvolutionWhatsAppProvider, redact_evolution_secret

class BadTransport:
    def request_json(self, method, path, *, base_url, api_key, payload=None, query=None):
        raise EvolutionApiError(f"apikey bad-secret failed")

provider = EvolutionWhatsAppProvider(config=EvolutionWhatsAppConfig(base_url="https://evolution.example", api_key="bad-secret", instance_name="inst"), transport=BadTransport())
try:
    provider.send_text(organization_id="org-a", contact_external_id="1", text="Oi", conversation_id="c")
except Exception as exc:
    error = str(exc)
print(json.dumps({
  "error": error,
  "redacted": redact_evolution_secret("token hook-secret bad-secret", "hook-secret", "bad-secret")
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.error.includes('bad-secret'), false);
  assert.equal(parsed.redacted.includes('hook-secret'), false);
  assert.equal(parsed.redacted.includes('bad-secret'), false);
});
