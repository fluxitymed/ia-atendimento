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

test('@spec:AC-183 Z-API legitimate webhook without native secret is not rejected', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post, validate_zapi_webhook

payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "txt-1", "phone": "5571999990000", "text": {"message": "Oi"}}
adapter = WhatsAppChannelAdapter(provider=FakeWhatsAppProvider(), store=InMemoryWhatsAppStore(), organization_resolver=OrganizationResolver({"clinic-a": "org-a"}))
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
print(json.dumps({
  "status": response.status_code,
  "body": response.body,
  "records": [record.decision.value for record in records],
  "runtimeCalls": adapter.runtime_calls,
  "validator": validate_zapi_webhook({}, ZApiWhatsAppConfig()),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.equal(parsed.body, 'EVENT_RECEIVED');
  assert.deepEqual(parsed.records, ['PROCESSED']);
  assert.equal(parsed.runtimeCalls, 1);
  assert.equal(parsed.validator, true);
});

test('@spec:AC-415 @spec:AC-416 @spec:AC-417 AI inbound kill switch accepts webhook without runtime or outbound', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph, StaticResponseGenerator
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class ForbiddenGenerator:
    def generate(self, state, *, emit):
        raise AssertionError("runtime must not run while AI_INBOUND_ENABLED=false")

logs = []
provider = FakeWhatsAppProvider()
store = InMemoryWhatsAppStore()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=store,
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(response_generator=ForbiddenGenerator()),
    allow_placeholder_ack=False,
    reject_out_of_order=True,
    inbound_enabled=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "off-1", "phone": "5571999990000", "text": {"message": "Oi"}}
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter, stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}))
duplicate_response, duplicate_records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
unknown_payload = {"type": "ReceivedCallback", "instanceId": "unknown", "messageId": "off-2", "phone": "5571999990000", "text": {"message": "Oi"}}
unknown_response, unknown_records = handle_zapi_webhook_post(raw_body=json.dumps(unknown_payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)

enabled_provider = FakeWhatsAppProvider()
enabled_adapter = WhatsAppChannelAdapter(
    provider=enabled_provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(response_generator=StaticResponseGenerator("Ligado")),
    allow_placeholder_ack=False,
    inbound_enabled=True,
)
enabled_payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "on-1", "phone": "5571999990000", "text": {"message": "Oi"}}
enabled_response, enabled_records = handle_zapi_webhook_post(raw_body=json.dumps(enabled_payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=enabled_adapter)

print(json.dumps({
  "disabledStatus": response.status_code,
  "disabledDecision": records[0].decision.value,
  "runtimeCalls": adapter.runtime_calls,
  "sentTexts": provider.sent_texts,
  "readMessages": provider.read_messages,
  "disabledLog": any(entry["stage"] == "ai_inbound_disabled" for entry in logs),
  "duplicateDecision": duplicate_records[0].decision.value,
  "unknownStatus": unknown_response.status_code,
  "unknownRecords": len(unknown_records),
  "enabledStatus": enabled_response.status_code,
  "enabledDecision": enabled_records[0].decision.value,
  "enabledRuntimeCalls": enabled_adapter.runtime_calls,
  "enabledSentTexts": enabled_provider.sent_texts,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.disabledStatus, 200);
  assert.equal(parsed.disabledDecision, 'INBOUND_DISABLED');
  assert.equal(parsed.runtimeCalls, 0);
  assert.deepEqual(parsed.sentTexts, []);
  assert.deepEqual(parsed.readMessages, []);
  assert.equal(parsed.disabledLog, true);
  assert.equal(parsed.duplicateDecision, 'DUPLICATE_SUPPRESSED');
  assert.equal(parsed.unknownStatus, 403);
  assert.equal(parsed.unknownRecords, 0);
  assert.equal(parsed.enabledStatus, 200);
  assert.equal(parsed.enabledDecision, 'PROCESSED');
  assert.equal(parsed.enabledRuntimeCalls, 1);
  assert.equal(parsed.enabledSentTexts.length, 1);
});

test('@spec:AC-184 Z-API parser normalizes official text, audio, image, and document callbacks', () => {
  const output = runPython(`
import base64, json
from ai_agent_runtime.whatsapp.zapi_webhook import parse_zapi_webhook_payload

payload = [
  {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "txt-1", "phone": "5571999990000", "text": {"message": "Oi"}, "momment": 1},
  {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "aud-1", "phone": "5571999990000", "senderLid": "81896604192873@lid", "audio": {"ptt": True, "seconds": 10, "audioUrl": "https://zapi.example/aud.ogg", "mimeType": "audio/ogg; codecs=opus", "base64": base64.b64encode(b"audio").decode()}, "momment": 2},
  {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "img-1", "phone": "5571999990000", "image": {"imageUrl": "https://zapi.example/img.jpg", "mimeType": "image/jpeg", "caption": "foto"}, "momment": 3},
  {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "doc-1", "phone": "5571999990000", "document": {"documentUrl": "https://zapi.example/doc.pdf", "mimeType": "application/pdf", "fileName": "guia.pdf"}, "momment": 4},
]
events = parse_zapi_webhook_payload(json.dumps(payload).encode())
print(json.dumps(events))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed.map((event) => event.type), ['TEXT', 'AUDIO', 'IMAGE', 'DOCUMENT']);
  assert.equal(parsed[0].providerAccountId, 'clinic-a');
  assert.equal(parsed[0].contactExternalId, '5571999990000');
  assert.equal(parsed[0].text, 'Oi');
  assert.equal(parsed[1].mimeType, 'audio/ogg');
  assert.equal(parsed[1].media.storageReference, 'zapi:aud-1');
  assert.equal(parsed[1].media.metadata.temporaryUrl, true);
  assert.equal(parsed[1].media.metadata.durationSeconds, 10);
  assert.equal(parsed[1].media.metadata.ptt, true);
  assert.ok(parsed[1].metadata.contactAliases.includes('81896604192873@lid'));
  assert.equal(parsed[2].media.url, 'https://zapi.example/img.jpg');
  assert.equal(parsed[2].text, 'foto');
  assert.equal(parsed[3].fileName, 'guia.pdf');
});

test('@spec:AC-405 @spec:AC-406 @spec:AC-407 Z-API webhook ingress logs text, image, and audio safely before normalization', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

logs = []
adapter = WhatsAppChannelAdapter(
    provider=FakeWhatsAppProvider(),
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
payloads = [
    {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "txt-ingress", "phone": "5571999990000", "text": {"message": "segredo do paciente"}},
    {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "img-ingress", "phone": "5571999990000", "image": {"imageUrl": "https://zapi.example/private-image.jpg", "mimeType": "image/jpeg"}},
    {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "aud-ingress", "phone": "5571999990000", "audio": {"ptt": True, "seconds": 7, "audioUrl": "https://zapi.example/private-audio.ogg", "mimeType": "audio/ogg", "viewOnce": False}},
]
for payload in payloads:
    handle_zapi_webhook_post(
        raw_body=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        config=ZApiWhatsAppConfig(),
        adapter=adapter,
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    )
ingress = [entry["details"] for entry in logs if entry["stage"] == "zapi_webhook_ingress_received"]
audio_detected = [entry["details"] for entry in logs if entry["stage"] == "audio_inbound_detected"]
serialized = json.dumps(logs)
print(json.dumps({
  "ingress": ingress,
  "audioDetected": audio_detected,
  "leakedText": "segredo do paciente" in serialized,
  "leakedImageUrl": "private-image" in serialized,
  "leakedAudioUrl": "private-audio" in serialized,
}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.ingress.length, 3);
  assert.equal(parsed.ingress[0].hasText, true);
  assert.equal(parsed.ingress[0].contentType, 'application/json');
  assert.equal(parsed.ingress[1].hasImage, true);
  assert.equal(parsed.ingress[2].hasAudio, true);
  assert.equal(parsed.audioDetected.length, 1);
  assert.equal(parsed.audioDetected[0].durationSeconds, 7);
  assert.equal(parsed.audioDetected[0].ptt, true);
  assert.equal(parsed.audioDetected[0].viewOnce, false);
  assert.equal(parsed.leakedText, false);
  assert.equal(parsed.leakedImageUrl, false);
  assert.equal(parsed.leakedAudioUrl, false);
});

test('@spec:AC-374 Z-API parser preserves phone and LID aliases from provider payload', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp.zapi_webhook import parse_zapi_webhook_payload

payload = {
  "type": "ReceivedCallback",
  "instanceId": "clinic-a",
  "messageId": "lid-1",
  "phone": "557191986031",
  "chatId": "139496326742018@lid",
  "remoteJid": "557191986031@s.whatsapp.net",
  "text": {"message": "Oi"}
}
event = parse_zapi_webhook_payload(json.dumps(payload).encode())[0]
print(json.dumps({
  "contactExternalId": event["contactExternalId"],
  "canonical": event["metadata"]["canonicalContactExternalId"],
  "aliases": event["metadata"]["contactAliases"],
  "sourceFields": event["metadata"]["contactAliasSourceFields"],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.contactExternalId, '557191986031');
  assert.equal(parsed.canonical, '557191986031');
  assert.ok(parsed.aliases.includes('557191986031'));
  assert.ok(parsed.aliases.includes('139496326742018@lid'));
  assert.equal(parsed.sourceFields.phone, '557191986031');
  assert.equal(parsed.sourceFields.chatId, '139496326742018@lid');
});

test('@spec:AC-379 unknown Z-API instance with aliases remains blocked and persists no alias', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

payload = {
  "type": "ReceivedCallback",
  "instanceId": "unknown-instance",
  "messageId": "lid-unknown",
  "phone": "557191986031",
  "chatId": "139496326742018@lid",
  "text": {"message": "Oi"}
}
store = InMemoryWhatsAppStore()
adapter = WhatsAppChannelAdapter(provider=FakeWhatsAppProvider(), store=store, organization_resolver=OrganizationResolver({"clinic-a": "org-a"}))
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
print(json.dumps({"status": response.status_code, "body": response.body, "records": len(records), "aliasCount": len(store.contact_aliases), "conversationCount": len(store.conversation_ids)}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 403);
  assert.equal(parsed.body, 'UNKNOWN_INSTANCE');
  assert.equal(parsed.records, 0);
  assert.equal(parsed.aliasCount, 0);
  assert.equal(parsed.conversationCount, 0);
});

test('@spec:AC-185 Z-API webhook blocks unknown instance and ignores payload organizationId', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

payload = {"type": "ReceivedCallback", "instanceId": "unknown-instance", "messageId": "txt-1", "phone": "5571999990000", "text": {"message": "Oi"}, "organizationId": "attacker-org"}
adapter = WhatsAppChannelAdapter(provider=FakeWhatsAppProvider(), store=InMemoryWhatsAppStore(), organization_resolver=OrganizationResolver({"clinic-a": "org-a"}))
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
print(json.dumps({"status": response.status_code, "body": response.body, "records": len(records), "runtimeCalls": adapter.runtime_calls}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 403);
  assert.equal(parsed.body, 'UNKNOWN_INSTANCE');
  assert.equal(parsed.records, 0);
  assert.equal(parsed.runtimeCalls, 0);
});

test('@spec:AC-186 Z-API webhook preserves idempotency, ordering, and self-message protection', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

payload = [
  {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "self-1", "phone": "5571999990000", "fromMe": True, "text": {"message": "Resposta da IA"}, "momment": 0},
  {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "txt-2", "phone": "5571999990000", "text": {"message": "segunda"}, "momment": 2},
  {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "txt-1", "phone": "5571999990000", "text": {"message": "Quero marcar"}, "momment": 1},
]
provider = FakeWhatsAppProvider()
store = InMemoryWhatsAppStore()
adapter = WhatsAppChannelAdapter(provider=provider, store=store, organization_resolver=OrganizationResolver({"clinic-a": "org-a"}), reject_out_of_order=True)
first_response, first_records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
second_response, second_records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
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
  assert.deepEqual(parsed.firstRecords, ['SELF_MESSAGE_IGNORED', 'PROCESSED', 'ORDERING_REJECTED']);
  assert.equal(parsed.second, 200);
  assert.deepEqual(parsed.secondRecords, ['DUPLICATE_SUPPRESSED', 'DUPLICATE_SUPPRESSED', 'DUPLICATE_SUPPRESSED']);
  assert.deepEqual(parsed.history, ['segunda']);
  assert.equal(parsed.runtimeCalls, 1);
  assert.equal(parsed.sentTexts, 1);
});

test('@spec:AC-187 @spec:AC-188 @spec:AC-189 @spec:AC-190 @spec:AC-408 @spec:AC-409 @spec:AC-410 Z-API media flows use safe download, ingress observability, and explicit invalid-media rejection', () => {
  const output = runPython(`
import base64, json
from ai_agent_runtime.whatsapp import FakeSpeechToTextProvider, InMemoryWhatsAppStore, MediaProcessor, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig, ZApiWhatsAppProvider
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class FakeTransport:
    def request_json(self, method, path, *, base_url, client_token, payload=None, query=None):
        return {"messageId": f"out-{len(path)}"}
    def get_bytes(self, url, *, client_token):
        if "doc-1" in url:
            return b"Quero marcar uma consulta sexta a tarde."
        return b"downloaded"

logs = []
payload = [
  {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "aud-1", "phone": "5571999990000", "audio": {"mimeType": "audio/ogg; codecs=opus", "audioUrl": "https://zapi.example/aud-1.ogg", "base64": base64.b64encode(b"audio").decode()}},
  {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "aud-bad", "phone": "5571999990000", "audio": {"mimeType": "audio/ogg", "audioUrl": "https://zapi.example/aud-bad.ogg", "base64": base64.b64encode(b"audio").decode()}},
  {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "doc-1", "phone": "5571999990000", "document": {"mimeType": "text/plain", "fileName": "agenda.txt", "documentUrl": "https://zapi.example/doc-1.txt", "extractedText": "Quero marcar uma consulta sexta a tarde.", "base64": base64.b64encode(b"Quero marcar uma consulta sexta a tarde.").decode()}},
  {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "img-1", "phone": "5571999990000", "image": {"mimeType": "image/jpeg", "imageUrl": "https://zapi.example/img-1.jpg", "base64": base64.b64encode(b"image").decode()}, "clinical": True},
]
provider = ZApiWhatsAppProvider(config=ZApiWhatsAppConfig(base_url="https://api.z-api.io", instance_id="clinic-a", instance_token="tok", client_token="client"), transport=FakeTransport())
adapter = WhatsAppChannelAdapter(
  provider=provider,
  store=InMemoryWhatsAppStore(),
  organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
  media_processor=MediaProcessor(provider=provider, speech_to_text=FakeSpeechToTextProvider("Quero marcar uma consulta sexta a tarde."), stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}})),
  stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter, stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}))
retry_adapter = WhatsAppChannelAdapter(
  provider=provider,
  store=InMemoryWhatsAppStore(),
  organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
  media_processor=MediaProcessor(provider=provider, speech_to_text=FakeSpeechToTextProvider("", fail=True), stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}})),
  stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
retry_payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "retry-1", "phone": "5571999990000", "audio": {"mimeType": "audio/ogg", "audioUrl": "https://zapi.example/retry-1.ogg", "base64": base64.b64encode(b"audio").decode()}}
retry_response, retry_records = handle_zapi_webhook_post(raw_body=json.dumps(retry_payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=retry_adapter, stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}))
invalid_adapter = WhatsAppChannelAdapter(
  provider=provider,
  store=InMemoryWhatsAppStore(),
  organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
  media_processor=MediaProcessor(provider=provider, speech_to_text=FakeSpeechToTextProvider("ignored"), stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}})),
  stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
invalid_payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "invalid-audio", "phone": "5571999990000", "audio": {"mimeType": "audio/ogg", "ptt": True, "seconds": 3, "viewOnce": False}}
invalid_response, invalid_records = handle_zapi_webhook_post(raw_body=json.dumps(invalid_payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=invalid_adapter, stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}))
print(json.dumps({
  "status": response.status_code,
  "records": [record.decision.value for record in records],
  "retryStatus": retry_response.status_code,
  "retryDecision": retry_records[0].decision.value,
  "invalidStatus": invalid_response.status_code,
  "invalidDecision": invalid_records[0].decision.value,
  "transcript": records[0].transcript,
  "imageReason": records[3].handoff_context["reason"],
  "imageHasOutbound": records[3].outbound is not None,
  "docFileName": records[2].inbound.file_name,
  "docMime": records[2].inbound.mime_type,
  "docExtracted": records[2].extracted_text,
  "docStorage": records[2].inbound.media_reference.storage_reference,
  "docUrl": records[2].inbound.media_reference.url,
  "stages": [entry["stage"] for entry in logs],
  "invalidHasOutbound": invalid_records[0].outbound is not None,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.deepEqual(parsed.records, ['PROCESSED', 'PROCESSED', 'PROCESSED', 'HUMAN_HANDOFF_REQUIRED']);
  assert.equal(parsed.retryStatus, 200);
  assert.equal(parsed.retryDecision, 'MEDIA_RETRY_REQUIRED');
  assert.equal(parsed.invalidStatus, 200);
  assert.equal(parsed.invalidDecision, 'MEDIA_RETRY_REQUIRED');
  assert.equal(parsed.invalidHasOutbound, true);
  assert.equal(parsed.transcript, 'Quero marcar uma consulta sexta a tarde.');
  assert.equal(parsed.imageReason, 'IMAGE_REQUIRES_HUMAN_REVIEW');
  assert.equal(parsed.imageHasOutbound, false);
  assert.equal(parsed.docFileName, 'agenda.txt');
  assert.equal(parsed.docMime, 'text/plain');
  assert.equal(parsed.docExtracted, 'Quero marcar uma consulta sexta a tarde.');
  assert.equal(parsed.docStorage, 'zapi:doc-1');
  assert.equal(parsed.docUrl, 'https://zapi.example/doc-1.txt');
  for (const stage of ['zapi_webhook_ingress_received', 'audio_inbound_detected', 'media_download_started', 'transcription_completed', 'audio_payload_missing_url']) {
    assert.ok(parsed.stages.includes(stage), `${stage} should be logged`);
  }
});
