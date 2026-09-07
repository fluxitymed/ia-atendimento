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

test('@spec:AC-161 Evolution webhook validates configured shared secret', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import EvolutionWhatsAppConfig
from ai_agent_runtime.whatsapp.evolution_webhook import validate_evolution_webhook

cfg = EvolutionWhatsAppConfig(webhook_secret="expected")
print(json.dumps({
  "ok": validate_evolution_webhook({"x-evolution-webhook-secret": "expected"}, cfg),
  "bearer": validate_evolution_webhook({"authorization": "Bearer expected"}, cfg),
  "bad": validate_evolution_webhook({"x-evolution-webhook-secret": "wrong"}, cfg),
  "optional": validate_evolution_webhook({}, EvolutionWhatsAppConfig()),
}))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed, { ok: true, bearer: true, bad: false, optional: true });
});

test('@spec:AC-162 Evolution parser normalizes text, audio, image, and document events', () => {
  const output = runPython(`
import base64, json
from ai_agent_runtime.whatsapp.evolution_webhook import parse_evolution_webhook_payload

payload = {
  "event": "MESSAGES_UPSERT",
  "instance": "clinic-a",
  "data": {"messages": [
    {"key": {"id": "txt-1", "remoteJid": "5571999990000@s.whatsapp.net"}, "messageType": "conversation", "message": {"conversation": "Oi"}, "messageTimestamp": 1},
    {"key": {"id": "aud-1", "remoteJid": "5571999990000@s.whatsapp.net"}, "messageType": "audioMessage", "message": {"audioMessage": {"mimetype": "audio/ogg", "fileLength": 20}}, "base64": base64.b64encode(b"audio").decode(), "messageTimestamp": 2},
    {"key": {"id": "img-1", "remoteJid": "5571999990000@s.whatsapp.net"}, "messageType": "imageMessage", "message": {"imageMessage": {"mimetype": "image/jpeg"}}, "mediaUrl": "https://media.example/img", "messageTimestamp": 3},
    {"key": {"id": "doc-1", "remoteJid": "5571999990000@s.whatsapp.net"}, "messageType": "documentMessage", "message": {"documentMessage": {"mimetype": "text/plain", "fileName": "guia.txt"}}, "base64": base64.b64encode(b"Quero marcar uma consulta sexta a tarde.").decode(), "messageTimestamp": 4},
  ]},
}
events = parse_evolution_webhook_payload(json.dumps(payload).encode())
print(json.dumps(events))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed.map((event) => event.type), ['TEXT', 'AUDIO', 'IMAGE', 'DOCUMENT']);
  assert.equal(parsed[0].contactExternalId, '5571999990000');
  assert.equal(parsed[0].text, 'Oi');
  assert.equal(parsed[1].mimeType, 'audio/ogg');
  assert.equal(parsed[1].media.storageReference, 'evolution:aud-1');
  assert.equal(parsed[2].media.url, 'https://media.example/img');
  assert.equal(parsed[3].fileName, 'guia.txt');
});

test('@spec:AC-163 Evolution webhook blocks unknown instance before runtime and ignores payload organizationId', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import EvolutionWhatsAppConfig, FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter
from ai_agent_runtime.whatsapp.evolution_webhook import handle_evolution_webhook_post

payload = {
  "event": "MESSAGES_UPSERT",
  "instance": "unknown-instance",
  "data": {"key": {"id": "txt-1", "remoteJid": "5571999990000@s.whatsapp.net"}, "messageType": "conversation", "message": {"conversation": "Oi"}, "organizationId": "attacker-org"},
}
adapter = WhatsAppChannelAdapter(provider=FakeWhatsAppProvider(), store=InMemoryWhatsAppStore(), organization_resolver=OrganizationResolver({"clinic-a": "org-a"}))
response, records = handle_evolution_webhook_post(raw_body=json.dumps(payload).encode(), headers={"x-evolution-webhook-secret": "ok"}, config=EvolutionWhatsAppConfig(webhook_secret="ok"), adapter=adapter)
print(json.dumps({"status": response.status_code, "body": response.body, "records": len(records), "runtimeCalls": adapter.runtime_calls}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 403);
  assert.equal(parsed.body, 'UNKNOWN_INSTANCE');
  assert.equal(parsed.records, 0);
  assert.equal(parsed.runtimeCalls, 0);
});

test('@spec:AC-164 Evolution webhook preserves idempotency, ordering, and self-message protection', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import EvolutionWhatsAppConfig, FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter
from ai_agent_runtime.whatsapp.evolution_webhook import handle_evolution_webhook_post

payload = {
  "event": "MESSAGES_UPSERT",
  "instance": "clinic-a",
  "data": {"messages": [
    {"key": {"id": "self-1", "remoteJid": "5571999990000@s.whatsapp.net", "fromMe": True}, "messageType": "conversation", "message": {"conversation": "Resposta da IA"}, "messageTimestamp": 0},
    {"key": {"id": "txt-2", "remoteJid": "5571999990000@s.whatsapp.net"}, "messageType": "conversation", "message": {"conversation": "segunda"}, "messageTimestamp": 2},
    {"key": {"id": "txt-1", "remoteJid": "5571999990000@s.whatsapp.net"}, "messageType": "conversation", "message": {"conversation": "Quero marcar"}, "messageTimestamp": 1},
  ]},
}
provider = FakeWhatsAppProvider()
store = InMemoryWhatsAppStore()
adapter = WhatsAppChannelAdapter(provider=provider, store=store, organization_resolver=OrganizationResolver({"clinic-a": "org-a"}))
first_response, first_records = handle_evolution_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=EvolutionWhatsAppConfig(), adapter=adapter)
second_response, second_records = handle_evolution_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=EvolutionWhatsAppConfig(), adapter=adapter)
conversation_id = first_records[1].inbound.conversation_id
print(json.dumps({
  "first": first_response.status_code,
  "firstRecords": [record.decision.value for record in first_records],
  "second": second_response.status_code,
  "secondRecords": [record.decision.value for record in second_records],
  "history": [message.text for message in store.history_for(conversation_id)],
  "runtimeCalls": adapter.runtime_calls,
  "sentTexts": len(provider.sent_texts),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.first, 200);
  assert.deepEqual(parsed.firstRecords, ['SELF_MESSAGE_IGNORED', 'PROCESSED', 'PROCESSED']);
  assert.equal(parsed.second, 200);
  assert.deepEqual(parsed.secondRecords, ['DUPLICATE_SUPPRESSED', 'DUPLICATE_SUPPRESSED', 'DUPLICATE_SUPPRESSED']);
  assert.deepEqual(parsed.history, ['segunda', 'Quero marcar']);
  assert.equal(parsed.runtimeCalls, 2);
  assert.equal(parsed.sentTexts, 2);
});

test('@spec:AC-165 @spec:AC-166 @spec:AC-167 @spec:AC-168 Evolution media flows use safe download and existing policies', () => {
  const output = runPython(`
import base64, json
from ai_agent_runtime.whatsapp import EvolutionWhatsAppConfig, EvolutionWhatsAppProvider, FakeSpeechToTextProvider, InMemoryWhatsAppStore, MediaProcessor, OrganizationResolver, WhatsAppChannelAdapter
from ai_agent_runtime.whatsapp.evolution_webhook import handle_evolution_webhook_post

class FakeTransport:
    def request_json(self, method, path, *, base_url, api_key, payload=None, query=None):
        return {"key": {"id": f"out-{path}"}}
    def get_bytes(self, url, *, api_key):
        return b"downloaded"

payload = {
  "event": "MESSAGES_UPSERT",
  "instance": "clinic-a",
  "data": {"messages": [
    {"key": {"id": "aud-1", "remoteJid": "5571999990000@s.whatsapp.net"}, "messageType": "audioMessage", "message": {"audioMessage": {"mimetype": "audio/ogg"}}, "base64": base64.b64encode(b"audio").decode()},
    {"key": {"id": "img-1", "remoteJid": "5571999990000@s.whatsapp.net"}, "messageType": "imageMessage", "message": {"imageMessage": {"mimetype": "image/jpeg"}}, "base64": base64.b64encode(b"image").decode(), "clinical": True},
    {"key": {"id": "doc-1", "remoteJid": "5571999990001@s.whatsapp.net"}, "messageType": "documentMessage", "message": {"documentMessage": {"mimetype": "text/plain", "fileName": "agenda.txt"}}, "base64": base64.b64encode(b"Quero marcar uma consulta sexta a tarde.").decode()},
  ]},
}
provider = EvolutionWhatsAppProvider(config=EvolutionWhatsAppConfig(base_url="https://evolution.example", api_key="key", instance_name="clinic-a"), transport=FakeTransport())
adapter = WhatsAppChannelAdapter(
  provider=provider,
  store=InMemoryWhatsAppStore(),
  organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
  media_processor=MediaProcessor(provider=provider, speech_to_text=FakeSpeechToTextProvider("Quero marcar uma consulta sexta a tarde.")),
)
response, records = handle_evolution_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=EvolutionWhatsAppConfig(), adapter=adapter)
print(json.dumps({
  "status": response.status_code,
  "records": [record.decision.value for record in records],
  "transcript": records[0].transcript,
  "imageReason": records[1].handoff_context["reason"],
  "docFileName": records[2].inbound.file_name,
  "docMime": records[2].inbound.mime_type,
  "docExtracted": records[2].extracted_text,
  "docStorage": records[2].inbound.media_reference.storage_reference,
  "docUrl": records[2].inbound.media_reference.url,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.deepEqual(parsed.records, ['PROCESSED', 'HUMAN_HANDOFF_REQUIRED', 'PROCESSED']);
  assert.equal(parsed.transcript, 'Quero marcar uma consulta sexta a tarde.');
  assert.equal(parsed.imageReason, 'IMAGE_REQUIRES_HUMAN_REVIEW');
  assert.equal(parsed.docFileName, 'agenda.txt');
  assert.equal(parsed.docMime, 'text/plain');
  assert.equal(parsed.docExtracted, 'Quero marcar uma consulta sexta a tarde.');
  assert.equal(parsed.docStorage, 'evolution:doc-1');
  assert.equal(parsed.docUrl, null);
});
