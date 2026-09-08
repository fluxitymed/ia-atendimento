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
  return JSON.parse(result.stdout);
}

const fakeRestTransport = `
class FakeRestTransport:
    def __init__(self, responses=()):
        self.calls = []
        self.responses = list(responses)

    def request(self, method, path, *, headers, params=None, payload=None):
        self.calls.append({
            "method": method,
            "path": path,
            "headers": headers,
            "params": params or {},
            "payload": payload or {},
        })
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        return {}
`;

test('@spec:AC-457 inbound creates or finds conversations scoped by CRM organization, WhatsApp channel, and external conversation id', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.crm_conversations import CrmConversationRepository
${fakeRestTransport}

transport = FakeRestTransport([
    [],
    {"id": "conv-a", "organization_id": "org-a", "channel": "whatsapp", "external_conversation_id": "55119999"},
    [],
    {"id": "conv-b", "organization_id": "org-b", "channel": "whatsapp", "external_conversation_id": "55119999"},
])
repository = CrmConversationRepository(transport=transport)
first = repository.resolve_or_create_conversation(
    organization_id="org-a", channel="whatsapp", external_conversation_id="55119999", phone_number="55119999"
)
second = repository.resolve_or_create_conversation(
    organization_id="org-b", channel="whatsapp", external_conversation_id="55119999", phone_number="55119999"
)
print(json.dumps({"first": first, "second": second, "calls": transport.calls}))
`);

  assert.equal(output.first.id, 'conv-a');
  assert.equal(output.second.id, 'conv-b');
  assert.notEqual(output.first.organization_id, output.second.organization_id);
  const inserts = output.calls.filter((call) => call.method === 'POST');
  assert.equal(output.calls.length, 4);
  assert.equal(inserts.length, 2);
  for (const call of inserts) {
    assert.equal(call.path, '/ai_conversations');
    assert.equal(Object.hasOwn(call.params, 'on_conflict'), false);
    assert.equal(call.headers.Prefer, 'return=representation');
    assert.equal(call.payload.channel, 'whatsapp');
    assert.equal(call.payload.mode, 'ai');
    assert.equal(call.payload.status, 'AI_ACTIVE');
  }
});

test('@spec:AC-457 an existing human CRM conversation is returned without resetting its mode, status, or handoff', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.crm_conversations import CrmConversationRepository
${fakeRestTransport}

transport = FakeRestTransport([[
    {"id": "conv-human", "organization_id": "org-1", "channel": "whatsapp", "external_conversation_id": "chat-1",
     "mode": "human", "status": "HANDOFF_REQUESTED", "handoff_requested": True,
     "handoff_requested_by": "human"}
]])
repository = CrmConversationRepository(transport=transport)
conversation = repository.resolve_or_create_conversation(
    organization_id="org-1", channel="whatsapp", external_conversation_id="chat-1", phone_number="55119999"
)
print(json.dumps({"conversation": conversation, "calls": transport.calls}))
`);

  assert.equal(output.conversation.mode, 'human');
  assert.equal(output.conversation.status, 'HANDOFF_REQUESTED');
  assert.equal(output.conversation.handoff_requested, true);
  assert.equal(output.conversation.handoff_requested_by, 'human');
  assert.equal(output.calls.length, 1);
  assert.equal(output.calls[0].method, 'GET');
  assert.equal(output.calls.some((call) => call.method === 'POST' || call.method === 'PATCH'), false);
});

test('@spec:AC-457 a concurrent conversation conflict is re-read instead of merging initial AI fields', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.crm_conversations import CrmConversationRepository, CrmRestConflictError
${fakeRestTransport}

transport = FakeRestTransport([
    [], CrmRestConflictError(),
    [{"id": "conv-human", "organization_id": "org-1", "channel": "whatsapp", "external_conversation_id": "chat-1",
      "mode": "human", "status": "HUMAN_ACTIVE", "handoff_requested": True, "handoff_requested_by": "human"}],
])
repository = CrmConversationRepository(transport=transport)
conversation = repository.resolve_or_create_conversation(
    organization_id="org-1", channel="whatsapp", external_conversation_id="chat-1", phone_number="55119999"
)
print(json.dumps({"conversation": conversation, "calls": transport.calls}))
`);

  assert.equal(output.conversation.mode, 'human');
  assert.equal(output.conversation.status, 'HUMAN_ACTIVE');
  assert.equal(output.conversation.handoff_requested, true);
  assert.equal(output.calls.length, 3);
  assert.equal(output.calls[1].method, 'POST');
  assert.equal(output.calls[1].headers.Prefer, 'return=representation');
  assert.equal(Object.hasOwn(output.calls[1].params, 'on_conflict'), false);
  assert.equal(output.calls[2].method, 'GET');
  assert.equal(output.calls.some((call) => call.method === 'PATCH'), false);
});

test('@spec:AC-458 inbound customer messages are persisted and advance conversation timestamps', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.crm_conversations import CrmConversationRepository
${fakeRestTransport}

transport = FakeRestTransport([
    {"id": "msg-1"},
    {"id": "conv-1", "last_message_at": "2026-09-07T12:00:00+00:00", "last_customer_message_at": "2026-09-07T12:00:00+00:00"},
])
repository = CrmConversationRepository(transport=transport)
result = repository.record_inbound_message(
    organization_id="org-1", conversation_id="conv-1", external_message_id="inbound-1",
    content="Quero agendar", occurred_at="2026-09-07T12:00:00+00:00"
)
print(json.dumps({"result": result, "calls": transport.calls}))
`);

  assert.equal(output.result.message_id, 'msg-1');
  const messageInsert = output.calls.find((call) => call.path === '/ai_messages');
  const conversationUpdate = output.calls.find((call) => call.path === '/ai_conversations' && call.method === 'PATCH');
  assert.deepEqual(messageInsert.payload, {
    organization_id: 'org-1',
    conversation_id: 'conv-1',
    external_message_id: 'inbound-1',
    direction: 'inbound',
    sender_type: 'customer',
    content: 'Quero agendar',
    message_type: 'text',
    sent_at: '2026-09-07T12:00:00+00:00',
  });
  assert.deepEqual(conversationUpdate.payload, {
    last_message_at: '2026-09-07T12:00:00+00:00',
    last_customer_message_at: '2026-09-07T12:00:00+00:00',
    updated_at: '2026-09-07T12:00:00+00:00',
  });
});

test('@spec:AC-459 duplicate inbound webhooks persist one message and event and start automation once', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.crm_conversations import CrmConversationMonitor, CrmConversationRepository, CrmOrganizationResolver, CrmRestConflictError
${fakeRestTransport}

transport = FakeRestTransport([
    [], {"id": "conv-1", "organization_id": "org-1", "mode": "ai", "status": "AI_ACTIVE"},
    {"id": "msg-1"}, {}, {"id": "event-1"},
    {"id": "conv-1", "organization_id": "org-1", "mode": "ai", "status": "AI_ACTIVE"},
    CrmRestConflictError(), [{"id": "msg-1", "conversation_id": "conv-1"}],
])
started = []
monitor = CrmConversationMonitor(
    repository=CrmConversationRepository(transport=transport),
    organization_resolver=CrmOrganizationResolver({"instance-a": "org-1"}),
)
for _ in range(2):
    monitor.process_inbound(
        instance_id="instance-a", external_conversation_id="chat-1", external_message_id="message-1",
        content="Oi", occurred_at="2026-09-07T12:00:00+00:00", phone_number="55119999",
        start_automation=lambda conversation: started.append(conversation["id"]),
    )
print(json.dumps({"started": started, "messageCalls": [c for c in transport.calls if c["path"] == "/ai_messages"], "events": [c for c in transport.calls if c["path"] == "/ai_events"]}))
`);

  assert.deepEqual(output.started, ['conv-1']);
  const messageInserts = output.messageCalls.filter((call) => call.method === 'POST');
  assert.equal(messageInserts.length, 2);
  assert.ok(messageInserts.every((call) => (
    call.headers.Prefer === 'return=representation' && !Object.hasOwn(call.params, 'on_conflict')
  )));
  assert.equal(output.events.length, 1);
  assert.equal(output.events[0].payload.event_type, 'MESSAGE_RECEIVED');
  assert.deepEqual(output.events[0].payload.metadata_json, {});
  assert.equal(output.events[0].payload.created_at, '2026-09-07T12:00:00+00:00');
});

test('@spec:AC-459 a 409 inbound conflict is re-read by organization and external id, then suppresses duplicate automation', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.crm_conversations import CrmConversationRepository, CrmRestConflictError
${fakeRestTransport}

transport = FakeRestTransport([CrmRestConflictError(), [{"id": "message-1", "conversation_id": "conv-1"}]])
result = CrmConversationRepository(transport=transport).record_inbound_message(
    organization_id="org-1", conversation_id="conv-1", external_message_id="provider-message-1",
    content="Oi", occurred_at="2026-09-07T12:00:00+00:00"
)
print(json.dumps({"result": result, "calls": transport.calls}))
`);

  assert.deepEqual(output.result, { message_id: 'message-1', inserted: false });
  assert.equal(output.calls.length, 2);
  assert.deepEqual(output.calls[1].params, {
    organization_id: 'eq.org-1',
    external_message_id: 'eq.provider-message-1',
    select: 'id,conversation_id',
  });
  assert.equal(output.calls.some((call) => call.method === 'PATCH'), false);
});

test('@spec:AC-459 non-409 inbound failures are not treated as duplicates and cross-conversation id collisions fail closed', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.crm_conversations import CrmConversationRepository, CrmRestConflictError, CrmRestError
${fakeRestTransport}

def attempt(responses, conversation_id):
    transport = FakeRestTransport(responses)
    try:
        CrmConversationRepository(transport=transport).record_inbound_message(
            organization_id="org-1", conversation_id=conversation_id, external_message_id="provider-message-1",
            content="Oi", occurred_at="2026-09-07T12:00:00+00:00"
        )
    except CrmRestError as exc:
        return {"error": exc.__class__.__name__, "status": exc.status_code, "calls": transport.calls}
    raise AssertionError("expected fail closed")

non_conflict = attempt([CrmRestError("CRM REST request failed with status 500", status_code=500)], "conv-1")
cross_conversation = attempt([CrmRestConflictError(), [{"id": "message-1", "conversation_id": "conv-other"}]], "conv-1")
print(json.dumps({"nonConflict": non_conflict, "crossConversation": cross_conversation}))
`);

  assert.deepEqual(output.nonConflict, {
    error: 'CrmRestError',
    status: 500,
    calls: [output.nonConflict.calls[0]],
  });
  assert.equal(output.nonConflict.calls.length, 1);
  assert.equal(output.nonConflict.calls.some((call) => call.method === 'GET'), false);
  assert.equal(output.crossConversation.error, 'CrmRestError');
  assert.equal(output.crossConversation.status, null);
  assert.equal(output.crossConversation.calls.length, 2);
  assert.equal(output.crossConversation.calls.some((call) => call.method === 'PATCH'), false);
});

test('@spec:AC-475 PostgREST transport exposes a typed 409 status without retaining response secrets', () => {
  const output = runPython(`
import io
import json
from urllib import error
import ai_agent_runtime.integrations.crm_conversations as crm

original_urlopen = crm.request.urlopen
crm.request.urlopen = lambda *args, **kwargs: (_ for _ in ()).throw(error.HTTPError(
    "https://crm.example.co/rest/v1/ai_messages", 409, "Conflict", {},
    io.BytesIO(b'{"message":"Authorization: Bearer super-secret-token"}')
))
try:
    crm.UrllibPostgrestTransport("https://crm.example.co").request(
        "POST", "/ai_messages", headers={"Authorization": "Bearer service-role"}, payload={"content": "Oi"}
    )
except crm.CrmRestConflictError as exc:
    print(json.dumps({"type": exc.__class__.__name__, "status": exc.status_code, "message": str(exc)}))
finally:
    crm.request.urlopen = original_urlopen
`);

  assert.deepEqual(output, { type: 'CrmRestConflictError', status: 409, message: 'CRM REST request conflicted' });
  assert.doesNotMatch(JSON.stringify(output), /super-secret-token|service-role|crm\.example\.co/);
});

test('@spec:AC-460 a new inbound message records an auditable MESSAGE_RECEIVED event in its CRM conversation', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.crm_conversations import CrmConversationRepository
${fakeRestTransport}

transport = FakeRestTransport([{"id": "event-1"}])
repository = CrmConversationRepository(transport=transport)
repository.record_event(
    organization_id="org-1", conversation_id="conv-1", event_type="MESSAGE_RECEIVED",
    occurred_at="2026-09-07T12:00:00+00:00"
)
print(json.dumps(transport.calls[0]))
`);

  assert.equal(output.path, '/ai_events');
  assert.equal(output.payload.organization_id, 'org-1');
  assert.equal(output.payload.conversation_id, 'conv-1');
  assert.equal(output.payload.event_type, 'MESSAGE_RECEIVED');
  assert.deepEqual(output.payload.metadata_json, {});
  assert.equal(output.payload.created_at, '2026-09-07T12:00:00+00:00');
  assert.equal('occurred_at' in output.payload, false);
});

test('@spec:AC-467 generated AI output is persisted as pending external delivery before the injectable outbound sender runs', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.crm_conversations import CrmConversationMonitor, CrmConversationRepository
${fakeRestTransport}

transport = FakeRestTransport([{"id": "outbound-1"}])
monitor = CrmConversationMonitor(repository=CrmConversationRepository(transport=transport))
sender_observations = []
def sender(text):
    sender_observations.append({"text": text, "calls_before_send": list(transport.calls)})
    return {"external_message_id": "zapi-1", "sent_at": "2026-09-07T12:00:01+00:00"}

monitor.deliver_ai_response(
    organization_id="org-1", conversation_id="conv-1", content="Posso ajudar?",
    occurred_at="2026-09-07T12:00:00+00:00", send_outbound=sender
)
print(json.dumps(sender_observations[0]))
`);

  assert.equal(output.text, 'Posso ajudar?');
  assert.equal(output.calls_before_send.length, 1);
  assert.equal(output.calls_before_send[0].path, '/ai_messages');
  assert.deepEqual(output.calls_before_send[0].payload, {
    organization_id: 'org-1',
    conversation_id: 'conv-1',
    direction: 'outbound',
    sender_type: 'ai',
    content: 'Posso ajudar?',
    message_type: 'text',
    delivery_status: 'pending_external_delivery',
  });
});

test('@spec:AC-468 accepted outbound delivery marks the message sent, advances the conversation, and records completion', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.crm_conversations import CrmConversationMonitor, CrmConversationRepository
${fakeRestTransport}

transport = FakeRestTransport([{"id": "outbound-1"}, {}, {}, {"id": "event-1"}])
monitor = CrmConversationMonitor(repository=CrmConversationRepository(transport=transport))
monitor.deliver_ai_response(
    organization_id="org-1", conversation_id="conv-1", content="Resposta",
    occurred_at="2026-09-07T12:00:00+00:00",
    send_outbound=lambda text: {"external_message_id": "zapi-1", "sent_at": "2026-09-07T12:00:02+00:00"},
)
print(json.dumps(transport.calls))
`);

  const sentUpdate = output.find((call) => call.path === '/ai_messages' && call.method === 'PATCH');
  const conversationUpdate = output.find((call) => call.path === '/ai_conversations' && call.method === 'PATCH');
  const completedEvent = output.find((call) => call.path === '/ai_events' && call.payload.event_type === 'AI_RESPONSE_COMPLETED');
  assert.deepEqual(sentUpdate.payload, {
    delivery_status: 'sent',
    external_message_id: 'zapi-1',
    sent_at: '2026-09-07T12:00:02+00:00',
  });
  assert.deepEqual(conversationUpdate.payload, {
    last_message_at: '2026-09-07T12:00:02+00:00',
    last_ai_message_at: '2026-09-07T12:00:02+00:00',
    updated_at: '2026-09-07T12:00:02+00:00',
  });
  assert.equal(completedEvent.payload.organization_id, 'org-1');
  assert.equal(completedEvent.payload.conversation_id, 'conv-1');
  assert.equal(completedEvent.payload.created_at, '2026-09-07T12:00:02+00:00');
  assert.deepEqual(completedEvent.payload.metadata_json, {});
});

test('@spec:AC-469 failed outbound delivery stores exactly the contracted sanitized metadata keys', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.crm_conversations import CrmConversationMonitor, CrmConversationRepository
${fakeRestTransport}

transport = FakeRestTransport([{"id": "outbound-1"}, {}, {"id": "event-1"}])
monitor = CrmConversationMonitor(repository=CrmConversationRepository(transport=transport))
result = monitor.deliver_ai_response(
    organization_id="org-1", conversation_id="conv-1", content="Resposta",
    occurred_at="2026-09-07T12:00:00+00:00",
    send_outbound=lambda text: (_ for _ in ()).throw(RuntimeError("401 Authorization: Bearer super-secret-token https://db.example.co")),
    provider="zapi", attempt=2,
)
print(json.dumps({"result": result, "calls": transport.calls}))
`);

  assert.equal(output.result.delivery_status, 'failed');
  const failedUpdate = output.calls.find((call) => call.path === '/ai_messages' && call.method === 'PATCH');
  const failedEvent = output.calls.find((call) => call.path === '/ai_events' && call.payload.event_type === 'AI_RESPONSE_FAILED');
  assert.equal(failedUpdate.payload.delivery_status, 'failed');
  assert.equal(failedEvent.payload.severity, 'error');
  assert.deepEqual(Object.keys(failedEvent.payload.metadata_json).sort(), ['attempt', 'error_code', 'error_type', 'provider', 'safe_message']);
  assert.equal(failedEvent.payload.metadata_json.attempt, 2);
  assert.equal(failedEvent.payload.metadata_json.provider, 'zapi');
  assert.doesNotMatch(JSON.stringify(failedEvent.payload.metadata_json), /super-secret-token|Authorization|https:\/\/db\.example\.co/);
  assert.equal(failedEvent.payload.created_at, '2026-09-07T12:00:00+00:00');
});

test('@spec:AC-457 a new CRM conversation stores phone_number separately and scopes its identity by Z-API instance plus canonical contact', () => {
  const output = runPython(`
import json
from types import SimpleNamespace
from ai_agent_runtime.integrations.crm_conversations import CrmConversationMonitor, CrmConversationRepository, CrmOrganizationResolver
from ai_agent_runtime.whatsapp.adapter import _canonical_whatsapp_phone
from ai_agent_runtime.whatsapp.zapi_webhook import parse_zapi_webhook_payload
${fakeRestTransport}

event = parse_zapi_webhook_payload(json.dumps({
    "type": "ReceivedCallback", "instanceId": "instance:one", "messageId": "m-1",
    "phone": "+55 (11) 99999-0000", "momment": "2026-09-07T12:00:00Z", "text": {"message": "Oi"}
}).encode())[0]
lid_event = parse_zapi_webhook_payload(json.dumps({
    "type": "ReceivedCallback", "instanceId": "instance:one", "messageId": "m-lid",
    "senderLid": "123456789012345@lid", "momment": "2026-09-07T12:00:00Z", "text": {"message": "Oi"}
}).encode())[0]
transport = FakeRestTransport([
    [], {"id": "conv-a", "mode": "ai"}, {"id": "msg-a"}, {}, {"id": "event-a"}, [{"id": "conv-a", "mode": "ai"}],
    [], {"id": "conv-b", "mode": "ai"}, {"id": "msg-b"}, {}, {"id": "event-b"}, [{"id": "conv-b", "mode": "ai"}],
    [], {"id": "conv-lid", "mode": "ai"}, {"id": "msg-lid"}, {}, {"id": "event-lid"}, [{"id": "conv-lid", "mode": "ai"}],
])
monitor = CrmConversationMonitor(
    repository=CrmConversationRepository(transport=transport),
    organization_resolver=CrmOrganizationResolver({"instance:one": "crm-org", "instance/two": "crm-org"}),
)
first = monitor.prepare_inbound(
    instance_id=event["providerAccountId"], external_conversation_id=event["contactExternalId"],
    phone_number=event["metadata"]["canonicalPhoneNumber"], external_message_id="m-1",
    content="Oi", occurred_at="2026-09-07T12:00:00+00:00",
)
second = monitor.prepare_inbound(
    instance_id="instance/two", external_conversation_id=event["contactExternalId"],
    phone_number=event["metadata"]["canonicalPhoneNumber"], external_message_id="m-2",
    content="Oi de outra instancia", occurred_at="2026-09-07T12:00:01+00:00",
)
lid_phone = _canonical_whatsapp_phone(SimpleNamespace(
    metadata=lid_event["metadata"], contact_external_id=lid_event["contactExternalId"]
))
lid_only = monitor.prepare_inbound(
    instance_id=lid_event["providerAccountId"], external_conversation_id=lid_event["contactExternalId"],
    phone_number=lid_phone, external_message_id="m-lid",
    content="Oi via LID", occurred_at="2026-09-07T12:00:02+00:00",
)
inserts = [call["payload"] for call in transport.calls if call["path"] == "/ai_conversations" and call["method"] == "POST"]
print(json.dumps({"phone": event["metadata"]["canonicalPhoneNumber"], "lidPhone": lid_phone, "states": [first, second, lid_only], "inserts": inserts}))
`);

  assert.equal(output.phone, '5511999990000');
  assert.equal(output.lidPhone, null);
  assert.deepEqual(output.states.map((state) => state.duplicate), [false, false, false]);
  assert.deepEqual(output.inserts.map((insert) => insert.phone_number), ['5511999990000', '5511999990000', null]);
  assert.notEqual(output.inserts[0].external_conversation_id, output.inserts[1].external_conversation_id);
  assert.match(output.inserts[0].external_conversation_id, /^zapi:instance%3Aone:5511999990000$/);
  assert.match(output.inserts[1].external_conversation_id, /^zapi:instance%2Ftwo:5511999990000$/);
  assert.match(output.inserts[2].external_conversation_id, /^zapi:instance%3Aone:123456789012345%40lid$/);
});

test('@spec:AC-459 a logical batch stores every constituent id, suppresses replay after restart, and emits MESSAGE_RECEIVED only for new constituents', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.crm_conversations import CrmConversationMonitor, CrmConversationRepository, CrmOrganizationResolver, CrmRestConflictError
${fakeRestTransport}

transport = FakeRestTransport([
    [], {"id": "conv-1", "mode": "ai"}, {"id": "msg-1"}, {}, {"id": "event-1"}, {"id": "msg-2"}, {}, {"id": "event-2"}, [{"id": "conv-1", "mode": "ai"}],
    [{"id": "conv-1", "mode": "ai"}], CrmRestConflictError(), [{"id": "msg-1", "conversation_id": "conv-1"}],
    [{"id": "conv-1", "mode": "ai"}], CrmRestConflictError(), [{"id": "msg-1", "conversation_id": "conv-1"}], {"id": "msg-3"}, {}, {"id": "event-3"}, [{"id": "conv-1", "mode": "ai"}],
])
monitor = CrmConversationMonitor(
    repository=CrmConversationRepository(transport=transport),
    organization_resolver=CrmOrganizationResolver({"instance-a": "org-1"}),
)
def prepare(batch):
    return monitor.prepare_inbound(
        instance_id="instance-a", external_conversation_id="55119999", phone_number="55119999",
        external_message_id="composite-id-must-not-persist", content="logical", occurred_at="2026-09-07T12:00:00+00:00",
        batch_messages=batch,
    )
first = prepare([
    {"external_message_id": "m1", "content": "primeira", "occurred_at": "2026-09-07T12:00:00+00:00", "message_type": "text"},
    {"external_message_id": "m2", "content": "segunda", "occurred_at": "2026-09-07T12:00:01+00:00", "message_type": "text"},
])
replayed_after_restart = prepare([
    {"external_message_id": "m1", "content": "primeira", "occurred_at": "2026-09-07T12:00:00+00:00", "message_type": "text"},
])
mixed = prepare([
    {"external_message_id": "m1", "content": "primeira", "occurred_at": "2026-09-07T12:00:00+00:00", "message_type": "text"},
    {"external_message_id": "m3", "content": "terceira", "occurred_at": "2026-09-07T12:00:02+00:00", "message_type": "text"},
])
message_inserts = [call["payload"] for call in transport.calls if call["path"] == "/ai_messages" and call["method"] == "POST"]
received_events = [call["payload"] for call in transport.calls if call["path"] == "/ai_events" and call["payload"].get("event_type") == "MESSAGE_RECEIVED"]
print(json.dumps({"states": [first, replayed_after_restart, mixed], "messageInserts": message_inserts, "receivedEvents": received_events}))
`);

  assert.deepEqual(output.states.map((state) => state.duplicate), [false, true, false]);
  assert.deepEqual(output.messageInserts.map((message) => message.external_message_id), ['m1', 'm2', 'm1', 'm1', 'm3']);
  assert.equal(output.messageInserts.some((message) => message.external_message_id.includes('+')), false);
  assert.equal(output.receivedEvents.length, 3);
});

test('@spec:AC-459 a mixed duplicate/new physical batch invokes the LLM once while an all-duplicate replay invokes it zero times', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph, StaticResponseGenerator
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, MessageBatchingConfig, MessageBatchingWhatsAppChannelAdapter, OrganizationResolver, WhatsAppChannelAdapter

class Monitor:
    def __init__(self): self.repository = self; self.seen = set(); self.batches = []
    def prepare_inbound(self, *, batch_messages=None, **kwargs):
        messages = batch_messages or [{"external_message_id": kwargs["external_message_id"]}]
        self.batches.append([item["external_message_id"] for item in messages])
        inserted = [item for item in messages if item["external_message_id"] not in self.seen]
        self.seen.update(item["external_message_id"] for item in messages)
        return {"organization_id": "crm-org", "conversation_id": "crm-conv", "duplicate": not inserted, "mode": "ai" if inserted else None}
    def record_event(self, **kwargs): pass
    def deliver_ai_response(self, *, send_outbound, **kwargs): return {"delivery_status": "sent", **send_outbound(kwargs["content"])}
    def request_handoff(self, **kwargs): raise AssertionError("handoff not expected")

monitor = Monitor()
def run_batch(message_ids):
    provider = FakeWhatsAppProvider()
    adapter = WhatsAppChannelAdapter(
        provider=provider, store=InMemoryWhatsAppStore(), organization_resolver=OrganizationResolver({"instance-a": "org-a"}),
        runtime_graph=AgentRuntimeGraph(response_generator=StaticResponseGenerator("Resposta")), allow_placeholder_ack=False, crm_monitor=monitor,
    )
    batching = MessageBatchingWhatsAppChannelAdapter(adapter, config=MessageBatchingConfig(debounce_ms=6000, max_wait_ms=12000))
    for index, message_id in enumerate(message_ids):
        batching.process_event({"providerAccountId": "instance-a", "providerMessageId": message_id, "contactExternalId": "55119999", "type": "TEXT", "text": message_id, "timestamp": str(index + 1), "metadata": {"canonicalPhoneNumber": "55119999"}})
    batching.flush(next(iter(batching._pending)))
    return {"runtimeCalls": adapter.runtime_calls, "sent": len(provider.sent_texts)}

first = run_batch(["m1", "m2"])
replayed_after_restart = run_batch(["m1"])
mixed = run_batch(["m1", "m3"])
print(json.dumps({"first": first, "replayed": replayed_after_restart, "mixed": mixed, "batches": monitor.batches}))
`);

  assert.deepEqual(output.first, { runtimeCalls: 1, sent: 1 });
  assert.deepEqual(output.replayed, { runtimeCalls: 0, sent: 0 });
  assert.deepEqual(output.mixed, { runtimeCalls: 1, sent: 1 });
  assert.deepEqual(output.batches, [['m1', 'm2'], ['m1'], ['m1', 'm3']]);
});

test('@spec:AC-476 monitored media bypasses batching and cannot hand off or send outbound before CRM inbound persistence', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph, StaticResponseGenerator
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, MessageBatchingConfig, MessageBatchingWhatsAppChannelAdapter, OrganizationResolver, WhatsAppChannelAdapter
from ai_agent_runtime.whatsapp.media import MediaDecision, MediaProcessingResult

timeline = []
class RetryMediaProcessor:
    def process(self, **kwargs):
        timeline.append("media")
        return MediaProcessingResult(decision=MediaDecision.MEDIA_RETRY_REQUIRED, retry_message="Envie novamente")
class Provider(FakeWhatsAppProvider):
    def send_text(self, **kwargs): timeline.append("outbound"); return super().send_text(**kwargs)
class Monitor:
    def __init__(self): self.repository = self
    def prepare_inbound(self, **kwargs): timeline.append("crm_inbound_persisted"); return {"organization_id": "crm-org", "conversation_id": "crm-conv", "duplicate": False, "mode": "ai"}
    def record_event(self, **kwargs): pass
    def deliver_ai_response(self, *, send_outbound, **kwargs): timeline.append("crm_outbound_pending"); return {"delivery_status": "sent", **send_outbound(kwargs["content"])}
    def request_handoff(self, **kwargs): timeline.append("crm_handoff_persisted")

provider = Provider()
adapter = WhatsAppChannelAdapter(
    provider=provider, store=InMemoryWhatsAppStore(), organization_resolver=OrganizationResolver({"instance-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(response_generator=StaticResponseGenerator("nao deve rodar")), media_processor=RetryMediaProcessor(),
    allow_placeholder_ack=False, crm_monitor=Monitor(),
)
batching = MessageBatchingWhatsAppChannelAdapter(adapter, config=MessageBatchingConfig(debounce_ms=6000, max_wait_ms=12000))
record = batching.process_event({"providerAccountId": "instance-a", "providerMessageId": "image-1", "contactExternalId": "55119999", "type": "IMAGE", "timestamp": "1", "media": {"providerMediaId": "image-1", "url": "https://cdn.example/image.jpg"}, "metadata": {"canonicalPhoneNumber": "55119999"}})
print(json.dumps({"decision": record.decision.value, "timeline": timeline, "pending": len(batching._pending), "runtimeCalls": adapter.runtime_calls}))
`);

  assert.equal(output.decision, 'MEDIA_RETRY_REQUIRED');
  assert.equal(output.pending, 0);
  assert.equal(output.runtimeCalls, 0);
  assert.ok(output.timeline.indexOf('crm_inbound_persisted') < output.timeline.indexOf('media'));
  assert.ok(output.timeline.indexOf('crm_inbound_persisted') < output.timeline.indexOf('crm_outbound_pending'));
  assert.ok(output.timeline.indexOf('crm_outbound_pending') < output.timeline.indexOf('outbound'));
});

test('@spec:AC-470 mandatory handoff persists the actual reason, AI origin, handoff status, timestamp, and human mode', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.crm_conversations import CrmConversationMonitor, CrmConversationRepository
${fakeRestTransport}

transport = FakeRestTransport([{}, {"id": "event-1"}])
monitor = CrmConversationMonitor(repository=CrmConversationRepository(transport=transport))
monitor.request_handoff(
    organization_id="org-1", conversation_id="conv-1", reason="Paciente pediu atendente humano",
    occurred_at="2026-09-07T12:00:00+00:00", origin="ai"
)
print(json.dumps(transport.calls))
`);

  const conversationUpdate = output.find((call) => call.path === '/ai_conversations' && call.method === 'PATCH');
  const handoffEvent = output.find((call) => call.path === '/ai_events' && call.payload.event_type === 'HANDOFF_REQUESTED');
  assert.deepEqual(conversationUpdate.payload, {
    handoff_requested: true,
    handoff_reason: 'Paciente pediu atendente humano',
    handoff_requested_by: 'ai',
    handoff_requested_at: '2026-09-07T12:00:00+00:00',
    status: 'HANDOFF_REQUESTED',
    mode: 'human',
    updated_at: '2026-09-07T12:00:00+00:00',
  });
  assert.equal(handoffEvent.payload.organization_id, 'org-1');
  assert.equal(handoffEvent.payload.conversation_id, 'conv-1');
  assert.deepEqual(handoffEvent.payload.metadata_json, {});
  assert.equal(handoffEvent.payload.created_at, '2026-09-07T12:00:00+00:00');
});

test('@spec:AC-472 observing a CRM takeover never creates HUMAN_TAKEOVER or AI_TAKEOVER events', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.crm_conversations import CrmConversationMonitor, CrmConversationRepository
${fakeRestTransport}

transport = FakeRestTransport([
    [{"id": "conv-1", "mode": "human"}],
    [{"id": "conv-1", "mode": "ai"}],
])
monitor = CrmConversationMonitor(repository=CrmConversationRepository(transport=transport))
first_mode = monitor.current_mode(organization_id="org-1", conversation_id="conv-1")
second_mode = monitor.current_mode(organization_id="org-1", conversation_id="conv-1")
print(json.dumps({"firstMode": first_mode, "secondMode": second_mode, "calls": transport.calls, "eventCalls": [c for c in transport.calls if c["path"] == "/ai_events"]}))
`);

  assert.equal(output.firstMode, 'human');
  assert.equal(output.secondMode, 'ai');
  assert.equal(output.calls.filter((call) => call.method === 'GET').length, 2);
  assert.deepEqual(output.eventCalls, []);
});

test('@spec:AC-473 CRM organization resolution uses only an explicit Z-API instance mapping', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.crm_conversations import CrmOrganizationResolver, UnknownCrmInstanceError

resolver = CrmOrganizationResolver({"instance-a": "7a1943b1-0000-4000-8000-000000000001"})
unknown_rejected = False
try:
    resolver.resolve(instance_id="unknown", payload={"phone": "+5511999999999", "organization_id": "forged-org"})
except UnknownCrmInstanceError:
    unknown_rejected = True
print(json.dumps({
    "resolved": resolver.resolve(instance_id="instance-a", payload={"phone": "+5511888888888"}),
    "unknownRejected": unknown_rejected,
}))
`);

  assert.equal(output.resolved, '7a1943b1-0000-4000-8000-000000000001');
  assert.equal(output.unknownRejected, true);
});

test('@spec:AC-474 CRM repository construction uses only dedicated backend CRM Supabase credentials', () => {
  const output = runPython(`
import json
import os
import ai_agent_runtime.integrations.config as config_module
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.crm_conversations import CrmConversationRepository
${fakeRestTransport}

os.environ.update({
    "CRM_SUPABASE_URL": "https://crm.example.supabase.co",
    "CRM_SUPABASE_SERVICE_ROLE_KEY": "crm-service-role",
    "SUPABASE_URL": "https://rag.example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "rag-service-role",
})
load_env_calls = []
config_module.load_env_file = lambda: load_env_calls.append(True)
transport = FakeRestTransport([[]])
repository = CrmConversationRepository.from_config(IntegrationConfig.from_env(), transport=transport)
repository.find_conversation(organization_id="org-1", channel="whatsapp", external_conversation_id="chat-1")
print(json.dumps({"baseUrl": repository.base_url, "call": transport.calls[0], "loadEnvCalls": load_env_calls}))
`);

  assert.equal(output.baseUrl, 'https://crm.example.supabase.co');
  assert.equal(output.call.headers.Authorization, 'Bearer crm-service-role');
  assert.equal(output.call.headers.apikey, 'crm-service-role');
  assert.equal(output.call.headers.Authorization.includes('rag-service-role'), false);
  assert.equal(output.call.headers.Authorization.includes('SUPABASE_ANON_KEY'), false);
  assert.equal(output.call.path, '/ai_conversations');
  assert.deepEqual(output.loadEnvCalls, [true]);
});

test('@spec:AC-475 safe CRM errors remove tokens, authorization values, JWTs, database URLs, and secret metadata', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.crm_conversations import sanitize_crm_error

error = RuntimeError("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature token=super-secret postgres://admin:password@db.example.co/runtime")
safe = sanitize_crm_error(error, metadata={"token": "super-secret", "Authorization": "Bearer abc", "provider": "zapi", "nested": {"api_key": "hidden"}})
print(json.dumps(safe))
`);

  const serialized = JSON.stringify(output);
  assert.deepEqual(Object.keys(output).sort(), ['code', 'message', 'metadata', 'type']);
  assert.equal(output.metadata.provider, 'zapi');
  assert.doesNotMatch(serialized, /super-secret|Bearer\s+[A-Za-z0-9._-]+|eyJhbGci|postgres:\/\/|password@db\.example\.co|api_key/i);
});

test('@spec:AC-461 @spec:AC-465 an AI CRM mode is freshly read for every inbound and overrides a stale local handoff', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph, StaticResponseGenerator
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter

class MonitoringStub:
    def __init__(self):
        self.repository = self
        self.modes = ["ai", "ai"]
        self.calls = []
    def prepare_inbound(self, **kwargs):
        self.calls.append({"kind": "inbound", **kwargs})
        return {"organization_id": "crm-org", "conversation_id": "crm-conv", "duplicate": False, "mode": self.modes.pop(0)}
    def record_event(self, **kwargs):
        self.calls.append({"kind": "event", **kwargs})
    def deliver_ai_response(self, *, send_outbound, **kwargs):
        self.calls.append({"kind": "pending", **kwargs})
        sent = send_outbound(kwargs["content"])
        self.calls.append({"kind": "sent", "external_message_id": sent["external_message_id"]})
        return {"delivery_status": "sent", **sent}
    def request_handoff(self, **kwargs):
        self.calls.append({"kind": "handoff", **kwargs})

provider = FakeWhatsAppProvider()
store = InMemoryWhatsAppStore()
adapter = WhatsAppChannelAdapter(
    provider=provider, store=store, organization_resolver=OrganizationResolver({"instance-a": "rag-org"}),
    runtime_graph=AgentRuntimeGraph(response_generator=StaticResponseGenerator("Resposta")),
    allow_placeholder_ack=False, crm_monitor=MonitoringStub(),
)
conversation_id = store.conversation_id_for(organization_id="rag-org", channel="whatsapp", contact_external_id="55119999")
store.handoff_conversations[conversation_id] = {"reason": "old-local-state"}
first = adapter.process_event({"providerAccountId": "instance-a", "providerMessageId": "provider-real-1", "contactExternalId": "55119999", "type": "TEXT", "text": "Oi", "timestamp": "1757246400"})
second = adapter.process_event({"providerAccountId": "instance-a", "providerMessageId": "provider-real-2", "contactExternalId": "55119999", "type": "TEXT", "text": "Continuar", "timestamp": "1757246401"})
monitor = adapter.crm_monitor
print(json.dumps({"decisions": [first.decision.value, second.decision.value], "runtimeCalls": adapter.runtime_calls, "sent": provider.sent_texts, "calls": monitor.calls}))
`);

  assert.deepEqual(output.decisions, ['PROCESSED', 'PROCESSED']);
  assert.equal(output.runtimeCalls, 2);
  assert.equal(output.sent.length, 2);
  const inbound = output.calls.filter((call) => call.kind === 'inbound');
  assert.deepEqual(inbound.map((call) => call.external_message_id), ['provider-real-1', 'provider-real-2']);
  assert.deepEqual(inbound.map((call) => call.external_conversation_id), ['55119999', '55119999']);
  assert.ok(inbound.every((call) => call.instance_id === 'instance-a' && call.message_type === 'text'));
  assert.ok(inbound.every((call) => /\+00:00$/.test(call.occurred_at)));
});

test('@spec:AC-462 @spec:AC-463 a human CRM mode persists the inbound but suppresses LLM and outbound without creating takeover events', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph, StaticResponseGenerator
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter

class MonitoringStub:
    def __init__(self): self.repository = self; self.calls = []
    def prepare_inbound(self, **kwargs): self.calls.append({"kind": "inbound", **kwargs}); return {"organization_id": "crm-org", "conversation_id": "crm-conv", "duplicate": False, "mode": "human"}
    def record_event(self, **kwargs): self.calls.append({"kind": "event", **kwargs})
    def deliver_ai_response(self, **kwargs): raise AssertionError("must not send")
    def request_handoff(self, **kwargs): raise AssertionError("must not synthesize takeover")

provider = FakeWhatsAppProvider()
monitor = MonitoringStub()
adapter = WhatsAppChannelAdapter(provider=provider, store=InMemoryWhatsAppStore(), organization_resolver=OrganizationResolver({"instance-a": "rag-org"}), runtime_graph=AgentRuntimeGraph(response_generator=StaticResponseGenerator("Resposta")), allow_placeholder_ack=False, crm_monitor=monitor)
record = adapter.process_event({"providerAccountId": "instance-a", "providerMessageId": "human-1", "contactExternalId": "55119999", "type": "TEXT", "text": "Quero humano", "timestamp": "2026-09-07T12:00:00Z"})
print(json.dumps({"decision": record.decision.value, "runtimeCalls": adapter.runtime_calls, "sent": provider.sent_texts, "events": [c for c in monitor.calls if c["kind"] == "event"], "calls": monitor.calls}))
`);

  assert.equal(output.decision, 'CRM_AUTOMATION_SUPPRESSED');
  assert.equal(output.runtimeCalls, 0);
  assert.deepEqual(output.sent, []);
  assert.deepEqual(output.events, []);
  assert.equal(output.calls.filter((call) => call.kind === 'inbound').length, 1);
});

test('@spec:AC-464 CRM unknown-instance and read/write failures fail closed while the Z-API webhook acknowledges 200 without secret diagnostics', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph, StaticResponseGenerator
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class FailingMonitor:
    def prepare_inbound(self, **kwargs): raise RuntimeError("Authorization: Bearer super-secret-token https://crm.example.co")

logs = []
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(provider=provider, store=InMemoryWhatsAppStore(), organization_resolver=OrganizationResolver({"instance-a": "rag-org"}), runtime_graph=AgentRuntimeGraph(response_generator=StaticResponseGenerator("Resposta")), allow_placeholder_ack=False, crm_monitor=FailingMonitor(), stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}))
body = json.dumps({"type": "ReceivedCallback", "instanceId": "instance-a", "messageId": "fail-1", "phone": "55119999", "momment": "1757246400", "text": {"message": "Oi"}}).encode()
response, records = handle_zapi_webhook_post(raw_body=body, headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
print(json.dumps({"status": response.status_code, "decisions": [r.decision.value for r in records], "runtimeCalls": adapter.runtime_calls, "sent": provider.sent_texts, "logs": logs}))
`);

  assert.equal(output.status, 200);
  assert.deepEqual(output.decisions, ['CRM_MONITORING_BLOCKED']);
  assert.equal(output.runtimeCalls, 0);
  assert.deepEqual(output.sent, []);
  assert.doesNotMatch(JSON.stringify(output.logs), /super-secret-token|https:\/\/crm\.example\.co|Authorization/);
});

test('@spec:AC-466 AI_RESPONSE_STARTED is recorded before the runtime and @spec:AC-471 a CRM handoff blocks subsequent inbound until CRM returns ai', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter

timeline = []
class Generator:
    def generate(self, state, *, emit): timeline.append("runtime"); return "Resposta"
class MonitoringStub:
    def __init__(self): self.repository = self; self.persisted_mode = "ai"; self.calls = []
    def prepare_inbound(self, **kwargs):
        self.calls.append({"kind": "inbound", "mode": self.persisted_mode, **kwargs})
        return {"organization_id": "crm-org", "conversation_id": "crm-conv", "duplicate": False, "mode": self.persisted_mode}
    def record_event(self, **kwargs): timeline.append(kwargs["event_type"]); self.calls.append({"kind": "event", **kwargs})
    def deliver_ai_response(self, *, send_outbound, **kwargs):
        timeline.append("pending"); sent = send_outbound(kwargs["content"]); timeline.append("sent"); return {"delivery_status": "sent", **sent}
    def request_handoff(self, **kwargs):
        self.persisted_mode = "human"
        self.calls.append({"kind": "handoff", "persisted_mode": self.persisted_mode, **kwargs})

provider = FakeWhatsAppProvider(); monitor = MonitoringStub()
adapter = WhatsAppChannelAdapter(provider=provider, store=InMemoryWhatsAppStore(), organization_resolver=OrganizationResolver({"instance-a": "rag-org"}), runtime_graph=AgentRuntimeGraph(response_generator=Generator()), allow_placeholder_ack=False, crm_monitor=monitor)
handoff = adapter.process_event({"providerAccountId": "instance-a", "providerMessageId": "handoff-1", "contactExternalId": "55119999", "type": "TEXT", "text": "Quero um atendente humano", "timestamp": "1757246400"})
blocked = adapter.process_event({"providerAccountId": "instance-a", "providerMessageId": "blocked-2", "contactExternalId": "55119999", "type": "TEXT", "text": "Ainda preciso de ajuda", "timestamp": "1757246401"})
monitor.persisted_mode = "ai"  # CRM operator releases the conversation.
released = adapter.process_event({"providerAccountId": "instance-a", "providerMessageId": "released-3", "contactExternalId": "55119999", "type": "TEXT", "text": "Agora posso continuar", "timestamp": "1757246402"})
records = [handoff, blocked, released]
print(json.dumps({"decisions": [r.decision.value for r in records], "timeline": timeline, "runtimeCalls": adapter.runtime_calls, "sent": provider.sent_texts, "calls": monitor.calls}))
`);

  assert.deepEqual(output.decisions, ['HUMAN_HANDOFF_REQUIRED', 'CRM_AUTOMATION_SUPPRESSED', 'PROCESSED']);
  assert.equal(output.runtimeCalls, 2);
  assert.equal(output.sent.length, 1);
  assert.ok(output.timeline.indexOf('AI_RESPONSE_STARTED') < output.timeline.indexOf('runtime'));
  const handoff = output.calls.find((call) => call.kind === 'handoff');
  assert.equal(handoff.persisted_mode, 'human');
  assert.equal(handoff.reason, 'PATIENT_REQUESTED_HUMAN');
  assert.deepEqual(output.calls.filter((call) => call.kind === 'inbound').map((call) => call.mode), ['ai', 'human', 'ai']);
  assert.equal(output.calls.some((call) => call.kind === 'event' && /TAKEOVER/.test(call.event_type)), false);
});

test('@spec:AC-476 disabled monitoring preserves the legacy adapter and enabled malformed or incomplete CRM configuration fails closed at construction', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.crm_conversations import CrmConfigurationError
import ai_agent_runtime.whatsapp.zapi_server as server
from ai_agent_runtime.whatsapp.zapi import ZApiWhatsAppConfig

config = ZApiWhatsAppConfig(instance_id="instance-a")
original = server.IntegrationConfig.from_env
server.IntegrationConfig.from_env = classmethod(lambda cls: IntegrationConfig(crm_ai_monitoring_enabled=False))
disabled = server.build_default_adapter(config)
results = []
for integration in (
    IntegrationConfig(crm_ai_monitoring_enabled=True),
    IntegrationConfig(crm_ai_monitoring_enabled=True, crm_supabase_url="https://crm.example.co", crm_supabase_service_role_key="service-role", crm_zapi_instance_organization_map_json="not-json"),
    IntegrationConfig(crm_ai_monitoring_enabled=True, crm_supabase_url="https://crm.example.co", crm_supabase_service_role_key="service-role", crm_zapi_instance_organization_map_json='{"instance-a": ""}'),
    IntegrationConfig(crm_ai_monitoring_enabled=True, crm_supabase_url="https://crm.example.co", crm_supabase_service_role_key="service-role", crm_zapi_instance_organization_map_json='{"other-instance": "crm-org"}'),
):
    server.IntegrationConfig.from_env = classmethod(lambda cls, value=integration: value)
    try:
        server.build_default_adapter(config)
    except CrmConfigurationError:
        results.append(True)
    else:
        results.append(False)
server.IntegrationConfig.from_env = original
base_adapter = getattr(disabled, "adapter", disabled)
print(json.dumps({"disabledMonitor": base_adapter.crm_monitor is None, "failedClosed": results}))
`);

  assert.equal(output.disabledMonitor, true);
  assert.deepEqual(output.failedClosed, [true, true, true, true]);
});
