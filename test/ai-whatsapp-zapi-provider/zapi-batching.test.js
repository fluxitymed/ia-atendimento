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

test('@spec:AC-310 @spec:AC-312 @spec:AC-315 @spec:AC-317 batching debounce creates one logical patient turn after silence', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, MessageBatchingConfig, MessageBatchingWhatsAppChannelAdapter, OrganizationResolver, WhatsAppChannelAdapter

class Handle:
    def __init__(self, task):
        self.task = task
    def cancel(self):
        self.task["cancelled"] = True

class ManualScheduler:
    def __init__(self):
        self.now = 0
        self.tasks = []
    def now_ms(self):
        return self.now
    def call_later(self, delay_ms, callback):
        task = {"due": self.now + delay_ms, "callback": callback, "cancelled": False}
        self.tasks.append(task)
        return Handle(task)
    def advance(self, ms):
        self.now += ms
        while True:
            due = sorted([task for task in self.tasks if not task["cancelled"] and task["due"] <= self.now], key=lambda item: item["due"])
            if not due:
                return
            task = due[0]
            task["cancelled"] = True
            task["callback"]()

class CaptureGenerator:
    def __init__(self):
        self.calls = []
    def generate(self, state, *, emit):
        self.calls.append({"text": state.current_message, "metadata": state.messages[-1].get("metadata") if state.messages else {}})
        emit("retrieval_completed", {"status": "NOT_CONFIGURED", "hitCount": 0})
        emit("model_called", {"mode": "test"})
        emit("grounding_result", {"passed": True})
        return "Resposta do lote"

logs = []
scheduler = ManualScheduler()
generator = CaptureGenerator()
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(response_generator=generator),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
batching = MessageBatchingWhatsAppChannelAdapter(adapter, config=MessageBatchingConfig(debounce_ms=6000, max_wait_ms=12000), scheduler=scheduler)

for message_id, text, advance in [("m1", "oi", 0), ("m2", "coloquei um implante", 2000), ("m3", "ontem", 2000)]:
    scheduler.advance(advance)
    batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": message_id, "contactExternalId": "contact-1", "type": "TEXT", "text": text, "timestamp": str(scheduler.now_ms())})

before = adapter.runtime_calls
scheduler.advance(5999)
almost = adapter.runtime_calls
scheduler.advance(1)
print(json.dumps({
  "before": before,
  "almost": almost,
  "runtimeCalls": adapter.runtime_calls,
  "outboundCount": len(provider.sent_texts),
  "turnText": generator.calls[0]["text"],
  "metadata": generator.calls[0]["metadata"],
  "processedAliases": sorted(adapter.store.records_by_provider_message_id.keys()),
  "logs": logs,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.before, 0);
  assert.equal(parsed.almost, 0);
  assert.equal(parsed.runtimeCalls, 1);
  assert.equal(parsed.outboundCount, 1);
  assert.equal(parsed.turnText, 'oi\ncoloquei um implante\nontem');
  assert.deepEqual(parsed.metadata.batchProviderMessageIds, ['m1', 'm2', 'm3']);
  assert.deepEqual(parsed.metadata.batchTimestamps, ['0', '2000', '4000']);
  assert.ok(parsed.processedAliases.includes('clinic-a:m1'));
  assert.ok(parsed.processedAliases.includes('clinic-a:m2'));
  assert.ok(parsed.processedAliases.includes('clinic-a:m3'));
  for (const stage of ['message_batch_started', 'message_batch_message_added', 'message_batch_debounce_reset', 'message_batch_flushed', 'message_batch_size', 'message_batch_age_ms', 'logical_patient_turn_created', 'conversation_lock_acquired', 'conversation_lock_released', 'queued_inbound_count']) {
    assert.ok(parsed.logs.some((entry) => entry.stage === stage), `${stage} missing`);
  }
});

test('@spec:AC-311 max wait flushes continuous inbound without waiting indefinitely', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph, StaticResponseGenerator
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, MessageBatchingConfig, MessageBatchingWhatsAppChannelAdapter, OrganizationResolver, WhatsAppChannelAdapter

class Handle:
    def __init__(self, task): self.task = task
    def cancel(self): self.task["cancelled"] = True
class ManualScheduler:
    def __init__(self): self.now = 0; self.tasks = []
    def now_ms(self): return self.now
    def call_later(self, delay_ms, callback):
        task = {"due": self.now + delay_ms, "callback": callback, "cancelled": False}
        self.tasks.append(task); return Handle(task)
    def advance(self, ms):
        self.now += ms
        while True:
            due = sorted([task for task in self.tasks if not task["cancelled"] and task["due"] <= self.now], key=lambda item: item["due"])
            if not due: return
            due[0]["cancelled"] = True; due[0]["callback"]()

logs = []
scheduler = ManualScheduler()
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(provider=provider, store=InMemoryWhatsAppStore(), organization_resolver=OrganizationResolver({"clinic-a": "org-a"}), runtime_graph=AgentRuntimeGraph(response_generator=StaticResponseGenerator("Batch")), allow_placeholder_ack=False, stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}))
batching = MessageBatchingWhatsAppChannelAdapter(adapter, config=MessageBatchingConfig(debounce_ms=6000, max_wait_ms=12000), scheduler=scheduler)
for message_id, text, advance in [("m1", "oi", 0), ("m2", "implante", 5000), ("m3", "ontem", 5000)]:
    scheduler.advance(advance)
    batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": message_id, "contactExternalId": "contact-1", "type": "TEXT", "text": text, "timestamp": str(scheduler.now_ms())})
scheduler.advance(1999)
before = adapter.runtime_calls
scheduler.advance(1)
print(json.dumps({"before": before, "runtimeCalls": adapter.runtime_calls, "outboundCount": len(provider.sent_texts), "maxWaitLogs": [entry for entry in logs if entry["stage"] == "message_batch_max_wait_reached"], "ageLogs": [entry["details"] for entry in logs if entry["stage"] == "message_batch_age_ms"]}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.before, 0);
  assert.equal(parsed.runtimeCalls, 1);
  assert.equal(parsed.outboundCount, 1);
  assert.equal(parsed.maxWaitLogs.length, 1);
  assert.equal(parsed.ageLogs.at(-1).ageMs, 12000);
});

test('@spec:AC-313 conversation lock queues next batch while runtime is active', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, MessageBatchingConfig, MessageBatchingWhatsAppChannelAdapter, OrganizationResolver, WhatsAppChannelAdapter

class Handle:
    def __init__(self, task): self.task = task
    def cancel(self): self.task["cancelled"] = True
class ManualScheduler:
    def __init__(self): self.now = 0; self.tasks = []
    def now_ms(self): return self.now
    def call_later(self, delay_ms, callback):
        task = {"due": self.now + delay_ms, "callback": callback, "cancelled": False}
        self.tasks.append(task); return Handle(task)
    def advance(self, ms):
        self.now += ms
        while True:
            due = sorted([task for task in self.tasks if not task["cancelled"] and task["due"] <= self.now], key=lambda item: item["due"])
            if not due: return
            due[0]["cancelled"] = True; due[0]["callback"]()

class ReentrantGenerator:
    def __init__(self): self.active = 0; self.max_active = 0; self.calls = []; self.batching = None; self.scheduler = None
    def generate(self, state, *, emit):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.calls.append(state.current_message)
        if len(self.calls) == 1:
            self.scheduler.advance(100)
            self.batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "m2", "contactExternalId": "contact-1", "type": "TEXT", "text": "segunda mensagem", "timestamp": str(self.scheduler.now_ms())})
        emit("retrieval_completed", {"status": "NOT_CONFIGURED", "hitCount": 0})
        emit("model_called", {"mode": "test"})
        emit("grounding_result", {"passed": True})
        self.active -= 1
        return f"Resposta {len(self.calls)}"

logs = []
scheduler = ManualScheduler()
generator = ReentrantGenerator()
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(provider=provider, store=InMemoryWhatsAppStore(), organization_resolver=OrganizationResolver({"clinic-a": "org-a"}), runtime_graph=AgentRuntimeGraph(response_generator=generator), allow_placeholder_ack=False, stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}))
batching = MessageBatchingWhatsAppChannelAdapter(adapter, config=MessageBatchingConfig(debounce_ms=6000, max_wait_ms=12000), scheduler=scheduler)
generator.batching = batching
generator.scheduler = scheduler
batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "m1", "contactExternalId": "contact-1", "type": "TEXT", "text": "primeira mensagem", "timestamp": "0"})
scheduler.advance(6000)
print(json.dumps({"runtimeCalls": adapter.runtime_calls, "outboundCount": len(provider.sent_texts), "maxActive": generator.max_active, "calls": generator.calls, "queuedLogs": [entry["details"] for entry in logs if entry["stage"] == "queued_inbound_count"]}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.runtimeCalls, 2);
  assert.equal(parsed.outboundCount, 2);
  assert.equal(parsed.maxActive, 1);
  assert.deepEqual(parsed.calls, ['primeira mensagem', 'segunda mensagem']);
  assert.ok(parsed.queuedLogs.some((entry) => entry.count === 1));
});

test('@spec:AC-314 distinct conversations can process while another conversation lock is active', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, MessageBatchingConfig, MessageBatchingWhatsAppChannelAdapter, OrganizationResolver, WhatsAppChannelAdapter

class Handle:
    def __init__(self, task): self.task = task
    def cancel(self): self.task["cancelled"] = True
class ManualScheduler:
    def __init__(self): self.now = 0; self.tasks = []
    def now_ms(self): return self.now
    def call_later(self, delay_ms, callback):
        task = {"due": self.now + delay_ms, "callback": callback, "cancelled": False}
        self.tasks.append(task); return Handle(task)
    def advance(self, ms):
        self.now += ms
        while True:
            due = sorted([task for task in self.tasks if not task["cancelled"] and task["due"] <= self.now], key=lambda item: item["due"])
            if not due: return
            due[0]["cancelled"] = True; due[0]["callback"]()

class ParallelProbeGenerator:
    def __init__(self): self.active = 0; self.max_active = 0; self.calls = []; self.batching = None
    def generate(self, state, *, emit):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.calls.append({"conversationId": state.conversation_id, "text": state.current_message})
        if len(self.calls) == 1:
            conv_b = self.batching.adapter.store.conversation_id_for(organization_id="org-a", channel="whatsapp", contact_external_id="contact-2")
            self.batching.flush(conv_b, reason="MANUAL")
        emit("retrieval_completed", {"status": "NOT_CONFIGURED", "hitCount": 0})
        emit("model_called", {"mode": "test"})
        emit("grounding_result", {"passed": True})
        self.active -= 1
        return "ok"

scheduler = ManualScheduler()
generator = ParallelProbeGenerator()
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(provider=provider, store=InMemoryWhatsAppStore(), organization_resolver=OrganizationResolver({"clinic-a": "org-a"}), runtime_graph=AgentRuntimeGraph(response_generator=generator), allow_placeholder_ack=False)
batching = MessageBatchingWhatsAppChannelAdapter(adapter, config=MessageBatchingConfig(debounce_ms=6000, max_wait_ms=12000), scheduler=scheduler)
generator.batching = batching
batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "a1", "contactExternalId": "contact-1", "type": "TEXT", "text": "conv a", "timestamp": "0"})
batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "b1", "contactExternalId": "contact-2", "type": "TEXT", "text": "conv b", "timestamp": "0"})
conv_a = adapter.store.conversation_id_for(organization_id="org-a", channel="whatsapp", contact_external_id="contact-1")
batching.flush(conv_a, reason="MANUAL")
print(json.dumps({"runtimeCalls": adapter.runtime_calls, "outboundCount": len(provider.sent_texts), "maxActive": generator.max_active, "conversationIds": [call["conversationId"] for call in generator.calls]}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.runtimeCalls, 2);
  assert.equal(parsed.outboundCount, 2);
  assert.equal(parsed.maxActive, 2);
  assert.equal(new Set(parsed.conversationIds).size, 2);
});

test('@spec:AC-316 early flush is deterministic and respects negation context', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph, StaticResponseGenerator
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, MessageBatchingConfig, MessageBatchingWhatsAppChannelAdapter, OrganizationResolver, WhatsAppChannelAdapter

class Scheduler:
    def now_ms(self): return 0
    def call_later(self, delay_ms, callback):
        class Handle:
            def cancel(self): pass
        return Handle()

logs = []
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(provider=provider, store=InMemoryWhatsAppStore(), organization_resolver=OrganizationResolver({"clinic-a": "org-a"}), runtime_graph=AgentRuntimeGraph(response_generator=StaticResponseGenerator("Early")), allow_placeholder_ack=False, stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}))
batching = MessageBatchingWhatsAppChannelAdapter(adapter, config=MessageBatchingConfig(debounce_ms=6000, max_wait_ms=12000), scheduler=Scheduler())
early = batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "m1", "contactExternalId": "contact-1", "type": "TEXT", "text": "estou com sangramento intenso", "timestamp": "1"})
negated = batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "m2", "contactExternalId": "contact-2", "type": "TEXT", "text": "nao estou sangrando", "timestamp": "2"})
print(json.dumps({"earlyDecision": early.decision.value, "negatedDecision": negated.decision.value, "runtimeCalls": adapter.runtime_calls, "outboundCount": len(provider.sent_texts), "earlyLogs": [entry for entry in logs if entry["details"].get("reason") == "EARLY_FLUSH"]}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.earlyDecision, 'PROCESSED');
  assert.equal(parsed.negatedDecision, 'BATCH_QUEUED');
  assert.equal(parsed.runtimeCalls, 1);
  assert.equal(parsed.outboundCount, 1);
  assert.ok(parsed.earlyLogs.length >= 1);
});

test('@spec:AC-310 batching config validates max wait is not shorter than debounce', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import MessageBatchingConfig
error = None
try:
    MessageBatchingConfig(debounce_ms=6000, max_wait_ms=5999).validate()
except ValueError as exc:
    error = str(exc)
print(json.dumps({"error": error, "defaults": MessageBatchingConfig().debounce_ms == 6000 and MessageBatchingConfig().max_wait_ms == 12000}))
`);
  const parsed = JSON.parse(output);
  assert.match(parsed.error, /MAX_WAIT/);
  assert.equal(parsed.defaults, true);
});

test('@spec:AC-359 runtime failure inside batch releases lock and next message can be processed', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, MessageBatchingConfig, MessageBatchingWhatsAppChannelAdapter, OrganizationResolver, WhatsAppChannelAdapter

class Handle:
    def __init__(self, task): self.task = task
    def cancel(self): self.task["cancelled"] = True
class ManualScheduler:
    def __init__(self): self.now = 0; self.tasks = []
    def now_ms(self): return self.now
    def call_later(self, delay_ms, callback):
        task = {"due": self.now + delay_ms, "callback": callback, "cancelled": False}
        self.tasks.append(task); return Handle(task)
    def advance(self, ms):
        self.now += ms
        while True:
            due = sorted([task for task in self.tasks if not task["cancelled"] and task["due"] <= self.now], key=lambda item: item["due"])
            if not due: return
            due[0]["cancelled"] = True; due[0]["callback"]()

class FailsOnceGenerator:
    def __init__(self): self.calls = 0
    def generate(self, state, *, emit):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary runtime failure")
        emit("retrieval_completed", {"status": "NOT_CONFIGURED", "hitCount": 0})
        emit("model_called", {"mode": "test"})
        emit("grounding_result", {"passed": True})
        return "Recuperei e segui o atendimento"

logs = []
scheduler = ManualScheduler()
generator = FailsOnceGenerator()
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(response_generator=generator),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
batching = MessageBatchingWhatsAppChannelAdapter(adapter, config=MessageBatchingConfig(debounce_ms=100, max_wait_ms=200), scheduler=scheduler)
batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "fail-1", "contactExternalId": "contact-1", "type": "TEXT", "text": "primeira", "timestamp": "0"})
scheduler.advance(100)
batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "ok-2", "contactExternalId": "contact-1", "type": "TEXT", "text": "segunda", "timestamp": "300"})
scheduler.advance(100)
print(json.dumps({
  "generatorCalls": generator.calls,
  "runtimeCalls": adapter.runtime_calls,
  "outboundCount": len(provider.sent_texts),
  "sentText": provider.sent_texts[0]["text"] if provider.sent_texts else "",
  "failedLogs": [entry["details"] for entry in logs if entry["stage"] == "batch_processing_failed"],
  "releasedLogs": [entry["details"] for entry in logs if entry["stage"] == "conversation_lock_released"],
  "recoveredLogs": [entry["details"] for entry in logs if entry["stage"] == "conversation_recovered_after_failure"],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.generatorCalls, 2);
  assert.equal(parsed.runtimeCalls, 2);
  assert.equal(parsed.outboundCount, 1);
  assert.equal(parsed.sentText, 'Recuperei e segui o atendimento');
  assert.equal(parsed.failedLogs.length, 1);
  assert.equal(parsed.failedLogs[0].errorType, 'WhatsAppRuntimeError');
  assert.equal(parsed.releasedLogs.length, 2);
  assert.equal(parsed.recoveredLogs.length, 1);
});

test('@spec:AC-373 @spec:AC-374 same Z-API message id with phone and LID is rejected before second conversation', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph, StaticResponseGenerator
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, MessageBatchingConfig, MessageBatchingWhatsAppChannelAdapter, OrganizationResolver, WhatsAppChannelAdapter

class Handle:
    def __init__(self, task): self.task = task
    def cancel(self): self.task["cancelled"] = True
class ManualScheduler:
    def __init__(self): self.now = 0; self.tasks = []
    def now_ms(self): return self.now
    def call_later(self, delay_ms, callback):
        task = {"due": self.now + delay_ms, "callback": callback, "cancelled": False}
        self.tasks.append(task); return Handle(task)
    def advance(self, ms):
        self.now += ms
        while True:
            due = sorted([task for task in self.tasks if not task["cancelled"] and task["due"] <= self.now], key=lambda item: item["due"])
            if not due: return
            due[0]["cancelled"] = True; due[0]["callback"]()

logs = []
scheduler = ManualScheduler()
provider = FakeWhatsAppProvider()
store = InMemoryWhatsAppStore()
adapter = WhatsAppChannelAdapter(provider=provider, store=store, organization_resolver=OrganizationResolver({"clinic-a": "org-a"}), runtime_graph=AgentRuntimeGraph(response_generator=StaticResponseGenerator("ok")), allow_placeholder_ack=False, stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}))
batching = MessageBatchingWhatsAppChannelAdapter(adapter, config=MessageBatchingConfig(debounce_ms=100, max_wait_ms=200), scheduler=scheduler)
first = batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "3AA10434B9DB7FDE3AAE", "contactExternalId": "557191986031", "type": "TEXT", "text": "Faz implante ai?", "timestamp": "1", "metadata": {"canonicalContactExternalId": "557191986031", "contactAliases": ["557191986031", "139496326742018@lid"]}})
duplicate = batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "3AA10434B9DB7FDE3AAE", "contactExternalId": "139496326742018@lid", "type": "TEXT", "text": "Faz implante ai?", "timestamp": "1", "metadata": {"canonicalContactExternalId": "557191986031", "contactAliases": ["557191986031", "139496326742018@lid"]}})
conv = first.inbound.conversation_id
scheduler.advance(100)
print(json.dumps({
  "decisions": [first.decision.value, duplicate.decision.value],
  "conversationCount": len(store.conversation_ids),
  "runtimeCalls": adapter.runtime_calls,
  "outboundCount": len(provider.sent_texts),
  "duplicateConversation": duplicate.inbound.conversation_id,
  "logs": [entry["stage"] for entry in logs],
  "history": [message.text for message in store.history_for(conv)],
}))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed.decisions, ['BATCH_QUEUED', 'DUPLICATE_SUPPRESSED']);
  assert.equal(parsed.conversationCount, 1);
  assert.equal(parsed.duplicateConversation, '');
  assert.equal(parsed.runtimeCalls, 1);
  assert.equal(parsed.outboundCount, 1);
  assert.deepEqual(parsed.history, ['Faz implante ai?']);
  assert.ok(parsed.logs.includes('provider_message_idempotency_checked'));
  assert.ok(parsed.logs.includes('provider_message_duplicate_rejected'));
});

test('@spec:AC-375 phone/LID alias resolves later LID-only turn to same conversation and history', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, MessageBatchingConfig, MessageBatchingWhatsAppChannelAdapter, OrganizationResolver, WhatsAppChannelAdapter

class Handle:
    def __init__(self, task): self.task = task
    def cancel(self): self.task["cancelled"] = True
class ManualScheduler:
    def __init__(self): self.now = 0; self.tasks = []
    def now_ms(self): return self.now
    def call_later(self, delay_ms, callback):
        task = {"due": self.now + delay_ms, "callback": callback, "cancelled": False}
        self.tasks.append(task); return Handle(task)
    def advance(self, ms):
        self.now += ms
        while True:
            due = sorted([task for task in self.tasks if not task["cancelled"] and task["due"] <= self.now], key=lambda item: item["due"])
            if not due: return
            due[0]["cancelled"] = True; due[0]["callback"]()

class CaptureGenerator:
    def __init__(self): self.calls = []
    def generate(self, state, *, emit):
        self.calls.append({"conversationId": state.conversation_id, "text": state.current_message, "history": [item["text"] for item in state.messages]})
        emit("retrieval_completed", {"status": "NOT_CONFIGURED", "hitCount": 0})
        emit("model_called", {"mode": "test"})
        emit("grounding_result", {"passed": True})
        return "ok"

scheduler = ManualScheduler()
generator = CaptureGenerator()
provider = FakeWhatsAppProvider()
store = InMemoryWhatsAppStore()
adapter = WhatsAppChannelAdapter(provider=provider, store=store, organization_resolver=OrganizationResolver({"clinic-a": "org-a"}), runtime_graph=AgentRuntimeGraph(response_generator=generator), allow_placeholder_ack=False)
batching = MessageBatchingWhatsAppChannelAdapter(adapter, config=MessageBatchingConfig(debounce_ms=100, max_wait_ms=200), scheduler=scheduler)
first = batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "m1", "contactExternalId": "557191986031", "type": "TEXT", "text": "Oi", "timestamp": "1", "metadata": {"canonicalContactExternalId": "557191986031", "contactAliases": ["557191986031", "139496326742018@lid"]}})
scheduler.advance(100)
second = batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "m2", "contactExternalId": "139496326742018@lid", "type": "TEXT", "text": "Tenho interesse na testa", "timestamp": "2", "metadata": {"canonicalContactExternalId": "139496326742018@lid", "contactAliases": ["139496326742018@lid"]}})
scheduler.advance(100)
print(json.dumps({
  "sameConversation": first.inbound.conversation_id == second.inbound.conversation_id,
  "contactExternalIds": [first.inbound.contact_external_id, second.inbound.contact_external_id],
  "runtimeCalls": adapter.runtime_calls,
  "secondHistory": generator.calls[1]["history"],
  "aliasCount": len(store.contact_aliases),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.sameConversation, true);
  assert.deepEqual(parsed.contactExternalIds, ['557191986031', '557191986031']);
  assert.equal(parsed.runtimeCalls, 2);
  assert.equal(parsed.secondHistory[0], 'Oi');
  assert.ok(parsed.secondHistory.includes('Tenho interesse na testa'));
  assert.equal(parsed.aliasCount, 2);
});

test('@spec:AC-376 @spec:AC-377 distinct LIDs are not merged and same id across accounts is isolated', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph, StaticResponseGenerator
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, MessageBatchingConfig, MessageBatchingWhatsAppChannelAdapter, OrganizationResolver, WhatsAppChannelAdapter

class Handle:
    def __init__(self, task): self.task = task
    def cancel(self): self.task["cancelled"] = True
class ManualScheduler:
    def __init__(self): self.now = 0; self.tasks = []
    def now_ms(self): return self.now
    def call_later(self, delay_ms, callback):
        task = {"due": self.now + delay_ms, "callback": callback, "cancelled": False}
        self.tasks.append(task); return Handle(task)
    def advance(self, ms):
        self.now += ms
        while True:
            due = sorted([task for task in self.tasks if not task["cancelled"] and task["due"] <= self.now], key=lambda item: item["due"])
            if not due: return
            due[0]["cancelled"] = True; due[0]["callback"]()

scheduler = ManualScheduler()
provider = FakeWhatsAppProvider()
store = InMemoryWhatsAppStore()
adapter = WhatsAppChannelAdapter(provider=provider, store=store, organization_resolver=OrganizationResolver({"clinic-a": "org-a", "clinic-b": "org-b"}), runtime_graph=AgentRuntimeGraph(response_generator=StaticResponseGenerator("ok")), allow_placeholder_ack=False)
batching = MessageBatchingWhatsAppChannelAdapter(adapter, config=MessageBatchingConfig(debounce_ms=100, max_wait_ms=200), scheduler=scheduler)
lid_a = batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "lid-a", "contactExternalId": "111@lid", "type": "TEXT", "text": "Oi", "timestamp": "1", "metadata": {"canonicalContactExternalId": "111@lid", "contactAliases": ["111@lid"]}})
lid_b = batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "lid-b", "contactExternalId": "222@lid", "type": "TEXT", "text": "Oi", "timestamp": "1", "metadata": {"canonicalContactExternalId": "222@lid", "contactAliases": ["222@lid"]}})
same_id_a = batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "same-id", "contactExternalId": "333@lid", "type": "TEXT", "text": "A", "timestamp": "1", "metadata": {"canonicalContactExternalId": "333@lid", "contactAliases": ["333@lid"]}})
same_id_b = batching.process_event({"providerAccountId": "clinic-b", "providerMessageId": "same-id", "contactExternalId": "333@lid", "type": "TEXT", "text": "B", "timestamp": "1", "metadata": {"canonicalContactExternalId": "333@lid", "contactAliases": ["333@lid"]}})
scheduler.advance(100)
print(json.dumps({
  "distinctLids": lid_a.inbound.conversation_id != lid_b.inbound.conversation_id,
  "sameIdDifferentAccountsDecisions": [same_id_a.decision.value, same_id_b.decision.value],
  "sameIdDifferentAccountsConversation": same_id_a.inbound.conversation_id != same_id_b.inbound.conversation_id,
  "runtimeCalls": adapter.runtime_calls,
  "outboundCount": len(provider.sent_texts),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.distinctLids, true);
  assert.deepEqual(parsed.sameIdDifferentAccountsDecisions, ['BATCH_QUEUED', 'BATCH_QUEUED']);
  assert.equal(parsed.sameIdDifferentAccountsConversation, true);
  assert.equal(parsed.runtimeCalls, 4);
  assert.equal(parsed.outboundCount, 4);
});

test('@spec:AC-378 @spec:AC-380 duplicate provider message inside batch is not added twice', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, MessageBatchingConfig, MessageBatchingWhatsAppChannelAdapter, OrganizationResolver, WhatsAppChannelAdapter

class Handle:
    def __init__(self, task): self.task = task
    def cancel(self): self.task["cancelled"] = True
class ManualScheduler:
    def __init__(self): self.now = 0; self.tasks = []
    def now_ms(self): return self.now
    def call_later(self, delay_ms, callback):
        task = {"due": self.now + delay_ms, "callback": callback, "cancelled": False}
        self.tasks.append(task); return Handle(task)
    def advance(self, ms):
        self.now += ms
        while True:
            due = sorted([task for task in self.tasks if not task["cancelled"] and task["due"] <= self.now], key=lambda item: item["due"])
            if not due: return
            due[0]["cancelled"] = True; due[0]["callback"]()

class CaptureGenerator:
    def __init__(self): self.calls = []
    def generate(self, state, *, emit):
        self.calls.append({"text": state.current_message, "metadata": state.messages[-1].get("metadata") if state.messages else {}})
        emit("retrieval_completed", {"status": "NOT_CONFIGURED", "hitCount": 0})
        emit("model_called", {"mode": "test"})
        emit("grounding_result", {"passed": True})
        return "ok"

logs = []
scheduler = ManualScheduler()
generator = CaptureGenerator()
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(provider=provider, store=InMemoryWhatsAppStore(), organization_resolver=OrganizationResolver({"clinic-a": "org-a"}), runtime_graph=AgentRuntimeGraph(response_generator=generator), allow_placeholder_ack=False, stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}))
batching = MessageBatchingWhatsAppChannelAdapter(adapter, config=MessageBatchingConfig(debounce_ms=100, max_wait_ms=200), scheduler=scheduler)
batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "M1", "contactExternalId": "557191986031", "type": "TEXT", "text": "Meu dente caiu", "timestamp": "1", "metadata": {"canonicalContactExternalId": "557191986031", "contactAliases": ["557191986031", "139496326742018@lid"]}})
batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "M2", "contactExternalId": "557191986031", "type": "TEXT", "text": "Faz implante ai?", "timestamp": "2", "metadata": {"canonicalContactExternalId": "557191986031", "contactAliases": ["557191986031", "139496326742018@lid"]}})
duplicate = batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "M2", "contactExternalId": "139496326742018@lid", "type": "TEXT", "text": "Faz implante ai?", "timestamp": "2", "metadata": {"canonicalContactExternalId": "139496326742018@lid", "contactAliases": ["139496326742018@lid"]}})
scheduler.advance(100)
metadata = generator.calls[0]["metadata"]
print(json.dumps({
  "duplicateDecision": duplicate.decision.value,
  "runtimeCalls": adapter.runtime_calls,
  "outboundCount": len(provider.sent_texts),
  "turnText": generator.calls[0]["text"],
  "batchIds": metadata["batchProviderMessageIds"],
  "batchKeys": metadata["batchProviderMessageKeys"],
  "batchSizeLogs": [entry["details"] for entry in logs if entry["stage"] == "message_batch_size"],
  "safeIdentityLogs": [entry for entry in logs if entry["stage"] in ("contact_identifiers_extracted", "contact_alias_resolved", "canonical_contact_resolved", "contact_alias_persisted")],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.duplicateDecision, 'DUPLICATE_SUPPRESSED');
  assert.equal(parsed.runtimeCalls, 1);
  assert.equal(parsed.outboundCount, 1);
  assert.equal(parsed.turnText, 'Meu dente caiu\nFaz implante ai?');
  assert.deepEqual(parsed.batchIds, ['M1', 'M2']);
  assert.deepEqual(parsed.batchKeys, ['clinic-a:M1', 'clinic-a:M2']);
  assert.equal(parsed.batchSizeLogs.at(-1).count, 2);
  assert.ok(parsed.safeIdentityLogs.length >= 4);
  assert.equal(JSON.stringify(parsed.safeIdentityLogs).includes('557191986031'), false);
  assert.equal(JSON.stringify(parsed.safeIdentityLogs).includes('139496326742018@lid'), false);
});

test('@spec:AC-381 @spec:AC-383 @spec:AC-390 audible Z-API audio is transcribed once and replies with text only', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, MediaProcessor, MessageBatchingConfig, MessageBatchingWhatsAppChannelAdapter, OrganizationResolver, WhatsAppChannelAdapter

class Handle:
    def __init__(self, task): self.task = task
    def cancel(self): self.task["cancelled"] = True
class ManualScheduler:
    def __init__(self): self.now = 0; self.tasks = []
    def now_ms(self): return self.now
    def call_later(self, delay_ms, callback):
        task = {"due": self.now + delay_ms, "callback": callback, "cancelled": False}
        self.tasks.append(task); return Handle(task)
    def advance(self, ms):
        self.now += ms
        while True:
            due = sorted([task for task in self.tasks if not task["cancelled"] and task["due"] <= self.now], key=lambda item: item["due"])
            if not due: return
            due[0]["cancelled"] = True; due[0]["callback"]()

class STT:
    model = "gpt-4o-mini-transcribe"
    def __init__(self): self.calls = 0
    def transcribe(self, *, audio, mime_type, file_name):
        self.calls += 1
        return "Oi, gostaria de saber sobre implante"
class Generator:
    def __init__(self): self.calls = []
    def generate(self, state, *, emit):
        self.calls.append({"text": state.current_message, "messages": state.messages})
        emit("retrieval_completed", {"status": "NOT_CONFIGURED", "hitCount": 0})
        emit("model_called", {"mode": "test"})
        emit("grounding_result", {"passed": True})
        return "Claro, posso te ajudar por texto."

logs = []
scheduler = ManualScheduler()
provider = FakeWhatsAppProvider({"aud-1": b"audio-bytes"})
stt = STT()
generator = Generator()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(response_generator=generator),
    media_processor=MediaProcessor(provider=provider, speech_to_text=stt, stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}})),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
batching = MessageBatchingWhatsAppChannelAdapter(adapter, config=MessageBatchingConfig(debounce_ms=100, max_wait_ms=200), scheduler=scheduler)
queued = batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "aud-1", "contactExternalId": "557191986031", "type": "AUDIO", "mimeType": "audio/ogg", "fileName": "voice.ogg", "media": {"providerMediaId": "aud-1", "sizeBytes": 11, "metadata": {"type": "audio"}}})
scheduler.advance(100)
record = batching.flushed_records[0]
print(json.dumps({
  "queuedDecision": queued.decision.value,
  "finalDecision": record.decision.value,
  "runtimeCalls": adapter.runtime_calls,
  "sttCalls": stt.calls,
  "sentTextCount": len(provider.sent_texts),
  "sentMediaCount": len(provider.sent_media),
  "runtimeText": generator.calls[0]["text"],
  "historyType": record.inbound.type.value,
  "transcript": record.transcript,
  "metadata": record.inbound.metadata,
  "logs": [entry["stage"] for entry in logs],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.queuedDecision, 'BATCH_QUEUED');
  assert.equal(parsed.finalDecision, 'PROCESSED');
  assert.equal(parsed.runtimeCalls, 1);
  assert.equal(parsed.sttCalls, 1);
  assert.equal(parsed.sentTextCount, 1);
  assert.equal(parsed.sentMediaCount, 0);
  assert.equal(parsed.runtimeText, 'Oi, gostaria de saber sobre implante');
  assert.equal(parsed.historyType, 'AUDIO');
  assert.equal(parsed.transcript, 'Oi, gostaria de saber sobre implante');
  assert.equal(parsed.metadata.sourceMessageType, 'AUDIO');
  for (const stage of ['audio_inbound_detected', 'media_download_started', 'media_download_completed', 'transcription_started', 'transcription_completed', 'transcript_length', 'audio_added_to_batch']) {
    assert.ok(parsed.logs.includes(stage), `${stage} missing`);
  }
});

test('@spec:AC-384 audio plus text creates one multimodal batch with preserved order', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, MediaProcessor, MessageBatchingConfig, MessageBatchingWhatsAppChannelAdapter, OrganizationResolver, WhatsAppChannelAdapter

class Handle:
    def __init__(self, task): self.task = task
    def cancel(self): self.task["cancelled"] = True
class ManualScheduler:
    def __init__(self): self.now = 0; self.tasks = []
    def now_ms(self): return self.now
    def call_later(self, delay_ms, callback):
        task = {"due": self.now + delay_ms, "callback": callback, "cancelled": False}
        self.tasks.append(task); return Handle(task)
    def advance(self, ms):
        self.now += ms
        while True:
            due = sorted([task for task in self.tasks if not task["cancelled"] and task["due"] <= self.now], key=lambda item: item["due"])
            if not due: return
            due[0]["cancelled"] = True; due[0]["callback"]()

class STT:
    model = "gpt-4o-mini-transcribe"
    def transcribe(self, *, audio, mime_type, file_name): return "perdi um dente faz alguns meses"
class Generator:
    def __init__(self): self.calls = []
    def generate(self, state, *, emit):
        self.calls.append({"text": state.current_message, "metadata": state.messages[-1]["metadata"]})
        emit("retrieval_completed", {"status": "NOT_CONFIGURED", "hitCount": 0})
        emit("model_called", {"mode": "test"})
        emit("grounding_result", {"passed": True})
        return "Vamos seguir por texto."

scheduler = ManualScheduler()
provider = FakeWhatsAppProvider({"aud-1": b"audio-bytes"})
generator = Generator()
adapter = WhatsAppChannelAdapter(provider=provider, store=InMemoryWhatsAppStore(), organization_resolver=OrganizationResolver({"clinic-a": "org-a"}), runtime_graph=AgentRuntimeGraph(response_generator=generator), media_processor=MediaProcessor(provider=provider, speech_to_text=STT()), allow_placeholder_ack=False)
batching = MessageBatchingWhatsAppChannelAdapter(adapter, config=MessageBatchingConfig(debounce_ms=6000, max_wait_ms=12000), scheduler=scheduler)
batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "aud-1", "contactExternalId": "557191986031", "type": "AUDIO", "mimeType": "audio/ogg", "fileName": "voice.ogg", "timestamp": "0", "media": {"providerMediaId": "aud-1", "sizeBytes": 11, "metadata": {"type": "audio"}}})
scheduler.advance(3000)
batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "txt-1", "contactExternalId": "557191986031", "type": "TEXT", "text": "queria saber sobre implante", "timestamp": "3000"})
scheduler.advance(6000)
metadata = generator.calls[0]["metadata"]
print(json.dumps({"runtimeCalls": adapter.runtime_calls, "outboundCount": len(provider.sent_texts), "text": generator.calls[0]["text"], "metadata": metadata}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.runtimeCalls, 1);
  assert.equal(parsed.outboundCount, 1);
  assert.equal(parsed.text, 'perdi um dente faz alguns meses\nqueria saber sobre implante');
  assert.deepEqual(parsed.metadata.batchProviderMessageIds, ['aud-1', 'txt-1']);
  assert.deepEqual(parsed.metadata.batchMessageTypes, ['AUDIO', 'TEXT']);
  assert.deepEqual(parsed.metadata.batchTranscripts, ['perdi um dente faz alguns meses', null]);
});

test('@spec:AC-385 duplicate Z-API audio by phone and LID is not transcribed twice', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, MediaProcessor, MessageBatchingConfig, MessageBatchingWhatsAppChannelAdapter, OrganizationResolver, WhatsAppChannelAdapter

class Handle:
    def __init__(self, task): self.task = task
    def cancel(self): self.task["cancelled"] = True
class ManualScheduler:
    def __init__(self): self.now = 0; self.tasks = []
    def now_ms(self): return self.now
    def call_later(self, delay_ms, callback):
        task = {"due": self.now + delay_ms, "callback": callback, "cancelled": False}
        self.tasks.append(task); return Handle(task)
    def advance(self, ms):
        self.now += ms
        while True:
            due = sorted([task for task in self.tasks if not task["cancelled"] and task["due"] <= self.now], key=lambda item: item["due"])
            if not due: return
            due[0]["cancelled"] = True; due[0]["callback"]()

class STT:
    model = "gpt-4o-mini-transcribe"
    def __init__(self): self.calls = 0
    def transcribe(self, *, audio, mime_type, file_name):
        self.calls += 1
        return "audio sobre implante"
class Generator:
    def generate(self, state, *, emit):
        emit("retrieval_completed", {"status": "NOT_CONFIGURED", "hitCount": 0})
        emit("model_called", {"mode": "test"})
        emit("grounding_result", {"passed": True})
        return "ok"

scheduler = ManualScheduler()
provider = FakeWhatsAppProvider({"aud-dup": b"audio-bytes"})
stt = STT()
adapter = WhatsAppChannelAdapter(provider=provider, store=InMemoryWhatsAppStore(), organization_resolver=OrganizationResolver({"clinic-a": "org-a"}), runtime_graph=AgentRuntimeGraph(response_generator=Generator()), media_processor=MediaProcessor(provider=provider, speech_to_text=stt), allow_placeholder_ack=False)
batching = MessageBatchingWhatsAppChannelAdapter(adapter, config=MessageBatchingConfig(debounce_ms=100, max_wait_ms=200), scheduler=scheduler)
first = batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "aud-dup", "contactExternalId": "557191986031", "type": "AUDIO", "mimeType": "audio/ogg", "media": {"providerMediaId": "aud-dup", "sizeBytes": 11, "metadata": {"type": "audio"}}, "metadata": {"canonicalContactExternalId": "557191986031", "contactAliases": ["557191986031", "139496326742018@lid"]}})
dup = batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": "aud-dup", "contactExternalId": "139496326742018@lid", "type": "AUDIO", "mimeType": "audio/ogg", "media": {"providerMediaId": "aud-dup", "sizeBytes": 11, "metadata": {"type": "audio"}}, "metadata": {"canonicalContactExternalId": "139496326742018@lid", "contactAliases": ["139496326742018@lid"]}})
scheduler.advance(100)
print(json.dumps({"decisions": [first.decision.value, dup.decision.value], "sttCalls": stt.calls, "runtimeCalls": adapter.runtime_calls, "outboundCount": len(provider.sent_texts)}))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed.decisions, ['BATCH_QUEUED', 'DUPLICATE_SUPPRESSED']);
  assert.equal(parsed.sttCalls, 1);
  assert.equal(parsed.runtimeCalls, 1);
  assert.equal(parsed.outboundCount, 1);
});

test('@spec:AC-386 @spec:AC-387 inaudible and transient STT failures return controlled media retry', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, MediaProcessor, MessageBatchingConfig, MessageBatchingWhatsAppChannelAdapter, OrganizationResolver, SpeechToTextTransientError, WhatsAppChannelAdapter

class Scheduler:
    def now_ms(self): return 0
    def call_later(self, delay_ms, callback):
        class Handle:
            def cancel(self): pass
        return Handle()
class EmptySTT:
    model = "gpt-4o-mini-transcribe"
    def __init__(self): self.calls = 0
    def transcribe(self, *, audio, mime_type, file_name):
        self.calls += 1
        return ""
class FailingSTT:
    model = "gpt-4o-mini-transcribe"
    def __init__(self): self.calls = 0
    def transcribe(self, *, audio, mime_type, file_name):
        self.calls += 1
        raise SpeechToTextTransientError("temporary outage")

def run(stt):
    provider = FakeWhatsAppProvider({"aud": b"audio-bytes"})
    adapter = WhatsAppChannelAdapter(provider=provider, store=InMemoryWhatsAppStore(), organization_resolver=OrganizationResolver({"clinic-a": "org-a"}), media_processor=MediaProcessor(provider=provider, speech_to_text=stt, stt_max_attempts=2), allow_placeholder_ack=False)
    batching = MessageBatchingWhatsAppChannelAdapter(adapter, config=MessageBatchingConfig(debounce_ms=100, max_wait_ms=200), scheduler=Scheduler())
    record = batching.process_event({"providerAccountId": "clinic-a", "providerMessageId": f"aud-{stt.__class__.__name__}", "contactExternalId": "557191986031", "type": "AUDIO", "mimeType": "audio/ogg", "media": {"providerMediaId": "aud", "sizeBytes": 11, "metadata": {"type": "audio"}}})
    return {"decision": record.decision.value, "outbound": provider.sent_texts[0]["text"], "runtimeCalls": adapter.runtime_calls, "sttCalls": stt.calls, "handoff": record.handoff_context is not None}

print(json.dumps({"empty": run(EmptySTT()), "technical": run(FailingSTT())}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.empty.decision, 'MEDIA_RETRY_REQUIRED');
  assert.match(parsed.empty.outbound, /mandar novamente|escrever/i);
  assert.equal(parsed.empty.runtimeCalls, 0);
  assert.equal(parsed.empty.handoff, false);
  assert.equal(parsed.empty.sttCalls, 1);
  assert.equal(parsed.technical.decision, 'MEDIA_RETRY_REQUIRED');
  assert.equal(parsed.technical.runtimeCalls, 0);
  assert.equal(parsed.technical.handoff, false);
  assert.equal(parsed.technical.sttCalls, 2);
});
