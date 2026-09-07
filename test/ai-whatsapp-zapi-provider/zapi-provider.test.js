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

test('@spec:AC-177 @spec:AC-179 @spec:AC-196 Z-API implements WhatsAppProvider and factory preserves Meta and Evolution', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import (
    EvolutionWhatsAppConfig,
    EvolutionWhatsAppProvider,
    MetaWhatsAppCloudProvider,
    MetaWhatsAppConfig,
    WhatsAppProvider,
    ZApiWhatsAppConfig,
    ZApiWhatsAppProvider,
    build_whatsapp_provider,
)

zapi = build_whatsapp_provider("zapi", zapi_config=ZApiWhatsAppConfig(base_url="https://api.z-api.io", instance_id="inst", instance_token="tok", client_token="client"))
evolution = build_whatsapp_provider("evolution", evolution_config=EvolutionWhatsAppConfig(base_url="http://evo", api_key="k", instance_name="inst"))
meta = build_whatsapp_provider("meta_cloud", meta_config=MetaWhatsAppConfig(access_token="m", phone_number_id="phone"))
print(json.dumps({
  "zapiIsProvider": isinstance(zapi, WhatsAppProvider),
  "zapiClass": zapi.__class__.__name__,
  "evolutionClass": evolution.__class__.__name__,
  "metaClass": meta.__class__.__name__,
  "zapiStillExists": ZApiWhatsAppProvider.__name__,
  "evolutionStillExists": EvolutionWhatsAppProvider.__name__,
  "metaStillExists": MetaWhatsAppCloudProvider.__name__,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.zapiIsProvider, true);
  assert.equal(parsed.zapiClass, 'ZApiWhatsAppProvider');
  assert.equal(parsed.evolutionClass, 'EvolutionWhatsAppProvider');
  assert.equal(parsed.metaClass, 'MetaWhatsAppCloudProvider');
  assert.equal(parsed.zapiStillExists, 'ZApiWhatsAppProvider');
  assert.equal(parsed.evolutionStillExists, 'EvolutionWhatsAppProvider');
  assert.equal(parsed.metaStillExists, 'MetaWhatsAppCloudProvider');
});

test('@spec:AC-178 Z-API config is env-driven and .env.example lists names without real secrets', () => {
  const output = runPython(`
import json, os
from ai_agent_runtime.whatsapp import ZApiWhatsAppConfig

os.environ.update({
  "WHATSAPP_PROVIDER": "zapi",
  "ZAPI_BASE_URL": "https://api.z-api.io",
  "ZAPI_INSTANCE_ID": "sandbox-instance",
  "ZAPI_INSTANCE_TOKEN": "instance-secret-value",
  "ZAPI_CLIENT_TOKEN": "client-secret-value",
  "ZAPI_PUBLIC_WEBHOOK_URL": "https://public.example",
  "ZAPI_ORGANIZATION_ID": "org-sandbox",
})
cfg = ZApiWhatsAppConfig.from_env()
print(json.dumps({"cfg": cfg.__dict__, "missing": cfg.missing_for_live()}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.cfg.provider, 'zapi');
  assert.equal(parsed.cfg.base_url, 'https://api.z-api.io');
  assert.equal(parsed.cfg.instance_id, 'sandbox-instance');
  assert.equal(parsed.cfg.organization_id, 'org-sandbox');
  assert.deepEqual(parsed.missing, []);
  const envExample = readFileSync('.env.example', 'utf8');
  for (const key of [
    'WHATSAPP_PROVIDER=zapi',
    'ZAPI_BASE_URL=',
    'ZAPI_INSTANCE_ID=',
    'ZAPI_INSTANCE_TOKEN=',
    'ZAPI_CLIENT_TOKEN=',
    'ZAPI_PUBLIC_WEBHOOK_URL=',
    'ZAPI_ORGANIZATION_ID=sandbox-org-dr-leonardo-carvalho',
  ]) {
  assert.match(envExample, new RegExp(key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
  assert.doesNotMatch(envExample, /instance-secret-value|client-secret-value|webhook-secret-value/);
});

test('@spec:AC-180 @spec:AC-181 @spec:AC-191 @spec:AC-192 @spec:AC-193 Z-API provider calls official endpoints', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import MediaReference, ZApiWhatsAppConfig, ZApiWhatsAppProvider

class FakeTransport:
    def __init__(self):
        self.calls = []
    def request_json(self, method, path, *, base_url, client_token, payload=None, query=None):
        self.calls.append({"method": method, "path": path, "baseUrl": base_url, "clientToken": client_token, "payload": payload})
        return {"messageId": f"id-{len(self.calls)}", "connected": True, "value": "data:image/png;base64,abc"}

transport = FakeTransport()
provider = ZApiWhatsAppProvider(
    config=ZApiWhatsAppConfig(
        base_url="https://api.z-api.io",
        instance_id="clinic-a",
        instance_token="instance-token",
        client_token="client-token",
        public_webhook_url="https://public.example/webhooks/zapi/whatsapp",
    ),
    transport=transport,
)
text = provider.send_text(organization_id="org-a", contact_external_id="5571999990000", text="Oi", conversation_id="conv-a")
image = provider.send_media(organization_id="org-a", contact_external_id="5571999990000", media=MediaReference(provider_media_id="img", url="https://cdn/img.jpg", metadata={"type": "image"}), caption="foto")
audio = provider.send_media(organization_id="org-a", contact_external_id="5571999990000", media=MediaReference(provider_media_id="aud", url="https://cdn/aud.ogg", metadata={"type": "audio"}))
doc = provider.send_media(organization_id="org-a", contact_external_id="5571999990000", media=MediaReference(provider_media_id="doc", url="https://cdn/doc.pdf", metadata={"type": "document", "fileName": "guia.pdf", "mimeType": "application/pdf"}), caption="guia")
status = provider.instance_status()
qr = provider.qr_code()
webhook = provider.set_received_webhook()
print(json.dumps({"text": text, "image": image, "audio": audio, "doc": doc, "status": status, "qr": qr, "webhook": webhook, "calls": transport.calls}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.text.providerMessageId, 'id-1');
  assert.deepEqual(parsed.calls.map((call) => `${call.method} ${call.path}`), [
    'POST /instances/clinic-a/token/instance-token/send-text',
    'POST /instances/clinic-a/token/instance-token/send-image',
    'POST /instances/clinic-a/token/instance-token/send-audio',
    'POST /instances/clinic-a/token/instance-token/send-document/pdf',
    'GET /instances/clinic-a/token/instance-token/status',
    'GET /instances/clinic-a/token/instance-token/qr-code',
    'PUT /instances/clinic-a/token/instance-token/update-webhook-received',
  ]);
  assert.deepEqual(parsed.calls[0].payload, { phone: '5571999990000', message: 'Oi' });
  assert.deepEqual(parsed.calls[1].payload, { phone: '5571999990000', image: 'https://cdn/img.jpg', caption: 'foto' });
  assert.deepEqual(parsed.calls[2].payload, { phone: '5571999990000', audio: 'https://cdn/aud.ogg' });
  assert.deepEqual(parsed.calls[3].payload, { phone: '5571999990000', document: 'https://cdn/doc.pdf', fileName: 'guia.pdf', caption: 'guia' });
  assert.equal(parsed.calls[6].payload.value, 'https://public.example/webhooks/zapi/whatsapp');
  assert.equal(parsed.calls.every((call) => call.clientToken === 'client-token'), true);
});

test('@spec:AC-182 Z-API errors redact instance token, client token and accidental secret text', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp.zapi import ZApiError, ZApiWhatsAppConfig, ZApiWhatsAppProvider, redact_zapi_secret, safe_zapi_result

class BadTransport:
    def request_json(self, method, path, *, base_url, client_token, payload=None, query=None):
        raise ZApiError(f"Client-Token client-secret failed at {path}")

provider = ZApiWhatsAppProvider(config=ZApiWhatsAppConfig(base_url="https://api.z-api.io", instance_id="inst", instance_token="instance-secret", client_token="client-secret"), transport=BadTransport())
try:
    provider.send_text(organization_id="org-a", contact_external_id="1", text="Oi", conversation_id="c")
except Exception as exc:
    error = str(exc)
print(json.dumps({
  "error": error,
  "redacted": redact_zapi_secret("https://api.z-api.io/instances/inst/token/instance-secret/send-text hook-secret client-secret", "instance-secret", "client-secret", "hook-secret"),
  "safeQr": safe_zapi_result({"value": "data:image/png;base64,very-sensitive-qr", "clientToken": "client-secret"}),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.error.includes('instance-secret'), false);
  assert.equal(parsed.error.includes('client-secret'), false);
  assert.equal(parsed.redacted.includes('hook-secret'), false);
  assert.equal(parsed.redacted.includes('client-secret'), false);
  assert.equal(parsed.redacted.includes('instance-secret'), false);
  assert.equal(parsed.safeQr.value, '[REDACTED_QR_CODE]');
  assert.equal(parsed.safeQr.clientToken, '[REDACTED_SECRET]');
});
