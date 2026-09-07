'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
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

test('@spec:AC-149 Meta webhook GET verification returns challenge only for matching verify token', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import MetaWhatsAppConfig
from ai_agent_runtime.whatsapp.meta_webhook import verify_webhook_get

cfg = MetaWhatsAppConfig(verify_token="expected-token")
ok = verify_webhook_get({"hub.mode": "subscribe", "hub.verify_token": "expected-token", "hub.challenge": "123"}, cfg)
bad = verify_webhook_get({"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "123"}, cfg)
print(json.dumps({"ok": ok.__dict__, "bad": bad.__dict__}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.ok.status_code, 200);
  assert.equal(parsed.ok.body, '123');
  assert.equal(parsed.bad.status_code, 403);
});

test('@spec:AC-150 Meta webhook validates X-Hub-Signature-256 when app secret is configured', () => {
  const output = runPython(`
import hashlib, hmac, json
from ai_agent_runtime.whatsapp.meta_webhook import validate_meta_signature

body = b'{"object":"whatsapp_business_account"}'
secret = "app-secret"
signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
print(json.dumps({
  "valid": validate_meta_signature(body, signature, secret),
  "invalid": validate_meta_signature(body, "sha256=bad", secret),
  "missing": validate_meta_signature(body, None, secret),
  "optional": validate_meta_signature(body, None, None),
}))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed, { valid: true, invalid: false, missing: false, optional: true });
});

test('@spec:AC-151 Meta webhook parser normalizes text, audio, image, and document payloads safely', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp.meta_webhook import parse_meta_webhook_payload

payload = {
  "object": "whatsapp_business_account",
  "entry": [{"changes": [{"field": "messages", "value": {
    "metadata": {"phone_number_id": "phone-123"},
    "messages": [
      {"id": "wamid.text", "from": "5571999990000", "timestamp": "1", "type": "text", "text": {"body": "Oi"}},
      {"id": "wamid.audio", "from": "5571999990000", "timestamp": "2", "type": "audio", "audio": {"id": "media-a", "mime_type": "audio/ogg", "sha256": "sha-a", "voice": True}},
      {"id": "wamid.image", "from": "5571999990000", "timestamp": "3", "type": "image", "image": {"id": "media-i", "mime_type": "image/jpeg", "sha256": "sha-i"}},
      {"id": "wamid.doc", "from": "5571999990000", "timestamp": "4", "type": "document", "document": {"id": "media-d", "mime_type": "application/pdf", "sha256": "sha-d", "filename": "arquivo.pdf"}},
    ],
  }}]}],
}
events = parse_meta_webhook_payload(json.dumps(payload).encode())
print(json.dumps(events))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed.map((event) => event.type), ['TEXT', 'AUDIO', 'IMAGE', 'DOCUMENT']);
  assert.equal(parsed[0].text, 'Oi');
  assert.equal(parsed[1].media.providerMediaId, 'media-a');
  assert.equal(parsed[1].mimeType, 'audio/ogg');
  assert.equal(parsed[2].media.storageReference, 'meta:media-i');
  assert.equal(parsed[3].fileName, 'arquivo.pdf');
});

test('@spec:AC-152 @spec:AC-153 Meta webhook controller delegates to adapter, suppresses duplicate, and ignores status self-events', () => {
  const output = runPython(`
import hashlib, hmac, json
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, MetaWhatsAppConfig
from ai_agent_runtime.whatsapp.meta_webhook import handle_meta_webhook_post

payload = {
  "object": "whatsapp_business_account",
  "entry": [{"changes": [{"field": "messages", "value": {
    "metadata": {"phone_number_id": "phone-123"},
    "messages": [{"id": "wamid.text", "from": "5571999990000", "timestamp": "1", "type": "text", "text": {"body": "Oi"}}],
    "statuses": [{"id": "wamid.sent", "recipient_id": "5571999990000", "status": "sent", "timestamp": "2"}],
  }}]}],
}
body = json.dumps(payload, separators=(",", ":")).encode()
secret = "app-secret"
signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
provider = FakeWhatsAppProvider()
store = InMemoryWhatsAppStore()
adapter = WhatsAppChannelAdapter(provider=provider, store=store, organization_resolver=OrganizationResolver({"phone-123": "org-a"}))
config = MetaWhatsAppConfig(app_secret=secret)
first_response, first_records = handle_meta_webhook_post(raw_body=body, headers={"X-Hub-Signature-256": signature}, config=config, adapter=adapter)
second_response, second_records = handle_meta_webhook_post(raw_body=body, headers={"X-Hub-Signature-256": signature}, config=config, adapter=adapter)
bad_response, bad_records = handle_meta_webhook_post(raw_body=body, headers={"X-Hub-Signature-256": "sha256=bad"}, config=config, adapter=adapter)
print(json.dumps({
  "first": {"status": first_response.status_code, "records": [record.decision.value for record in first_records]},
  "second": {"status": second_response.status_code, "records": [record.decision.value for record in second_records]},
  "bad": {"status": bad_response.status_code, "records": len(bad_records)},
  "runtimeCalls": adapter.runtime_calls,
  "sentTexts": len(provider.sent_texts),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.first.status, 200);
  assert.deepEqual(parsed.first.records, ['SELF_MESSAGE_IGNORED', 'PROCESSED']);
  assert.deepEqual(parsed.second.records, ['DUPLICATE_SUPPRESSED', 'DUPLICATE_SUPPRESSED']);
  assert.equal(parsed.bad.status, 403);
  assert.equal(parsed.bad.records, 0);
  assert.equal(parsed.runtimeCalls, 1);
  assert.equal(parsed.sentTexts, 1);
});
