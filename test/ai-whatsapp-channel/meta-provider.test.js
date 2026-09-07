'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { spawnSync } = require('node:child_process');

function runPython(source) {
  const result = spawnSync('python3', ['-c', source], {
    cwd: process.cwd(),
    env: { ...process.env, PYTHONPATH: 'src' },
    encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout.trim();
}

test('@spec:AC-145 Meta WhatsApp config is env-driven and env example contains no real secrets', () => {
  const output = runPython(`
import json
import os
from ai_agent_runtime.whatsapp import MetaWhatsAppConfig

os.environ["WHATSAPP_PROVIDER"] = "meta_cloud"
os.environ["META_WHATSAPP_ACCESS_TOKEN"] = "test-token"
os.environ["META_WHATSAPP_PHONE_NUMBER_ID"] = "12345"
os.environ["META_WHATSAPP_BUSINESS_ACCOUNT_ID"] = "67890"
os.environ["META_WHATSAPP_VERIFY_TOKEN"] = "verify"
os.environ["META_WHATSAPP_APP_SECRET"] = "secret"
os.environ["META_WHATSAPP_API_VERSION"] = "v23.0"
cfg = MetaWhatsAppConfig.from_env()
print(json.dumps({
  "provider": cfg.provider,
  "phoneNumberId": cfg.phone_number_id,
  "waba": cfg.business_account_id,
  "apiVersion": cfg.api_version,
  "missingWithoutPublicUrl": cfg.missing_for_live(),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.provider, 'meta_cloud');
  assert.equal(parsed.phoneNumberId, '12345');
  assert.equal(parsed.waba, '67890');
  assert.equal(parsed.apiVersion, 'v23.0');
  assert.deepEqual(parsed.missingWithoutPublicUrl, ['META_WHATSAPP_PUBLIC_WEBHOOK_URL']);

  const envExample = readFileSync('.env.example', 'utf8');
  for (const key of [
    'WHATSAPP_PROVIDER=meta_cloud',
    'META_WHATSAPP_ACCESS_TOKEN=',
    'META_WHATSAPP_PHONE_NUMBER_ID=',
    'META_WHATSAPP_BUSINESS_ACCOUNT_ID=',
    'META_WHATSAPP_VERIFY_TOKEN=',
    'META_WHATSAPP_APP_SECRET=',
    'META_WHATSAPP_API_VERSION=v23.0',
    'META_WHATSAPP_PUBLIC_WEBHOOK_URL=',
  ]) {
    assert.match(envExample, new RegExp(key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
  assert.doesNotMatch(envExample, /EAAG|Bearer\s+[A-Za-z0-9]|app_secret_[A-Za-z0-9]/);
});

test('@spec:AC-146 @spec:AC-147 Meta provider implements WhatsAppProvider and sends outbound text through messages endpoint', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import MetaWhatsAppCloudProvider, MetaWhatsAppConfig, WhatsAppProvider

class FakeTransport:
    def __init__(self):
        self.json_calls = []
    def request_json(self, method, path, *, access_token, payload=None, query=None):
        self.json_calls.append({"method": method, "path": path, "accessToken": access_token, "payload": payload, "query": query})
        return {"messaging_product": "whatsapp", "messages": [{"id": "wamid.test-out"}]}
    def get_bytes(self, url, *, access_token):
        raise AssertionError("not used")

transport = FakeTransport()
provider = MetaWhatsAppCloudProvider(
    config=MetaWhatsAppConfig(access_token="token-secret", phone_number_id="phone-123", api_version="v23.0"),
    transport=transport,
)
result = provider.send_text(organization_id="org-a", contact_external_id="5571999990000", text="Ola", conversation_id="conv-1")
read = provider.mark_as_read(organization_id="org-a", provider_message_id="wamid.in")
print(json.dumps({
  "isProvider": isinstance(provider, WhatsAppProvider),
  "result": result,
  "read": read,
  "calls": transport.json_calls,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.isProvider, true);
  assert.equal(parsed.result.providerMessageId, 'wamid.test-out');
  assert.equal(parsed.calls[0].method, 'POST');
  assert.equal(parsed.calls[0].path, '/v23.0/phone-123/messages');
  assert.equal(parsed.calls[0].payload.messaging_product, 'whatsapp');
  assert.equal(parsed.calls[0].payload.type, 'text');
  assert.equal(parsed.calls[0].payload.to, '5571999990000');
  assert.equal(parsed.calls[0].payload.text.body, 'Ola');
  assert.equal(parsed.calls[1].payload.status, 'read');
  assert.equal(parsed.calls[1].payload.message_id, 'wamid.in');
});

test('@spec:AC-148 Meta provider resolves media URL with auth and downloads bytes without persisting temporary URL', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import MediaReference, MetaWhatsAppCloudProvider, MetaWhatsAppConfig

class FakeTransport:
    def __init__(self):
        self.json_calls = []
        self.bytes_calls = []
    def request_json(self, method, path, *, access_token, payload=None, query=None):
        self.json_calls.append({"method": method, "path": path, "accessToken": access_token, "payload": payload, "query": query})
        return {"url": "https://lookaside.fbsbx.com/temp-media-url", "mime_type": "audio/ogg", "file_size": 12, "id": "media-1"}
    def get_bytes(self, url, *, access_token):
        self.bytes_calls.append({"url": url, "accessToken": access_token})
        return b"media-bytes"

transport = FakeTransport()
provider = MetaWhatsAppCloudProvider(
    config=MetaWhatsAppConfig(access_token="token-secret", phone_number_id="phone-123", api_version="v23.0"),
    transport=transport,
)
body = provider.download_media(organization_id="org-a", media=MediaReference(provider_media_id="media-1", storage_reference="meta:media-1"))
print(json.dumps({
  "bytes": body.decode("utf-8"),
  "jsonCalls": transport.json_calls,
  "bytesCalls": transport.bytes_calls,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.bytes, 'media-bytes');
  assert.equal(parsed.jsonCalls[0].method, 'GET');
  assert.equal(parsed.jsonCalls[0].path, '/v23.0/media-1');
  assert.deepEqual(parsed.jsonCalls[0].query, { phone_number_id: 'phone-123' });
  assert.equal(parsed.bytesCalls[0].url, 'https://lookaside.fbsbx.com/temp-media-url');
});
