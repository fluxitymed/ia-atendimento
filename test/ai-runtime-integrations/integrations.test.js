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

test('@spec:AC-049 @spec:AC-050 config reads environment and env example has no real secrets', () => {
  const output = runPython(`
import json
import os
from ai_agent_runtime.integrations.config import IntegrationConfig
os.environ["OPENAI_API_KEY"] = "test-key-from-env"
os.environ["SUPABASE_URL"] = "https://example.supabase.co"
cfg = IntegrationConfig.from_env()
print(json.dumps({
  "openai": cfg.openai_api_key,
  "model": cfg.openai_responses_model,
  "effort": cfg.openai_reasoning_effort,
  "sttModel": cfg.openai_stt_model,
  "supabase": cfg.supabase_url,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.openai, 'test-key-from-env');
  assert.equal(parsed.model, 'gpt-5.6-luna');
  assert.equal(parsed.effort, 'low');
  assert.equal(parsed.sttModel, 'gpt-4o-mini-transcribe');
  assert.equal(parsed.supabase, 'https://example.supabase.co');

  const envExample = readFileSync('.env.example', 'utf8');
  for (const key of ['OPENAI_API_KEY=', 'SUPABASE_SERVICE_ROLE_KEY=', 'LANGSMITH_API_KEY=', 'GOOGLE_CALENDAR_ACCESS_TOKEN=']) {
    assert.match(envExample, new RegExp(`^${key}$`, 'm'));
  }
  assert.doesNotMatch(envExample, /(sk-|Bearer\s+[A-Za-z0-9]|AIza|ya29\.)/);
});

test('@spec:AC-382 OpenAI speech-to-text provider uses env model and multipart audio endpoint', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.whatsapp import OpenAISpeechToTextProvider

class Transport:
    def __init__(self): self.calls = []
    def post_multipart(self, url, *, headers, fields, files):
        self.calls.append({"url": url, "headers": headers, "fields": fields, "files": {key: (value[0], len(value[1]), value[2]) for key, value in files.items()}})
        return {"text": "Oi, gostaria de saber sobre implante"}

transport = Transport()
provider = OpenAISpeechToTextProvider(IntegrationConfig(openai_api_key="test-key", openai_stt_model="gpt-4o-mini-transcribe"), transport)
text = provider.transcribe(audio=b"audio-bytes", mime_type="audio/ogg", file_name="voice.ogg")
print(json.dumps({"text": text, "model": provider.model, "call": transport.calls[0]}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.text, 'Oi, gostaria de saber sobre implante');
  assert.equal(parsed.model, 'gpt-4o-mini-transcribe');
  assert.equal(parsed.call.url, 'https://api.openai.com/v1/audio/transcriptions');
  assert.equal(parsed.call.fields.model, 'gpt-4o-mini-transcribe');
  assert.equal(parsed.call.files.file[0], 'voice.ogg');
  assert.equal(parsed.call.files.file[1], 11);
  assert.equal(parsed.call.files.file[2], 'audio/ogg');
  assert.match(parsed.call.headers.Authorization, /^Bearer /);
});

test('@spec:AC-051 @spec:AC-052 @spec:AC-053 migration enables pgvector, org constraints, and no patient memory in knowledge tables', () => {
  const sql = readFileSync('supabase/migrations/202608200001_ai_runtime_integrations.sql', 'utf8');
  assert.match(sql, /create extension if not exists vector/i);
  for (const table of [
    'organizations',
    'documents',
    'document_versions',
    'chunks',
    'retrieval_index_entries',
    'conversations',
    'conversation_messages',
    'operational_audit_events',
  ]) {
    assert.match(sql, new RegExp(`create table if not exists ${table}`, 'i'));
  }
  assert.match(sql, /foreign key \(organization_id, document_id\) references documents\(organization_id, id\)/i);
  assert.match(sql, /foreign key \(organization_id, document_version_id\) references document_versions\(organization_id, id\)/i);

  const knowledgeTables = sql.match(/create table if not exists (documents|document_versions|chunks|retrieval_index_entries)[\s\S]*?\);/gi).join('\n');
  assert.doesNotMatch(knowledgeTables, /\bpatient_id\b/i);
});

test('@spec:AC-054 @spec:AC-055 @spec:AC-056 Supabase hybrid retrieval filters org and eligibility and keeps grounding required', () => {
  const output = runPython(`
import json
from datetime import datetime, timezone, timedelta
from ai_agent_runtime.integrations.supabase_retrieval import SupabaseCandidate, SupabaseHybridRetrievalProvider
from ai_agent_runtime.retrieval import RetrievalIsolationError

class FakeTransport:
    def lexical_candidates(self, *, organization_id, query, limit):
        return [
          SupabaseCandidate("lex-1", organization_id, "doc-1", "ver-1", "published", 0.8, "lexical", "PUBLISHED", True),
          SupabaseCandidate("draft-1", organization_id, "doc-2", "ver-2", "draft", 0.95, "lexical", "DRAFT", True),
        ]
    def vector_candidates(self, *, organization_id, query, limit):
        return [
          SupabaseCandidate("vec-1", organization_id, "doc-3", "ver-3", "vector", 0.99, "vector", "PUBLISHED", True),
          SupabaseCandidate("expired-1", organization_id, "doc-4", "ver-4", "expired", 0.97, "vector", "PUBLISHED", True, effective_until=datetime.now(timezone.utc)-timedelta(days=1)),
        ]

missing = False
try:
    SupabaseHybridRetrievalProvider(FakeTransport()).search(organization_id="", query="preco")
except RetrievalIsolationError:
    missing = True
results = SupabaseHybridRetrievalProvider(FakeTransport()).search(organization_id="org-1", query="preco")
print(json.dumps({
  "missing": missing,
  "ids": [item.result.id for item in results],
  "sources": [item.result.source for item in results],
  "groundingRequired": [item.grounding_required for item in results],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.missing, true);
  assert.deepEqual(parsed.ids, ['vec-1', 'lex-1']);
  assert.deepEqual(parsed.sources, ['vector', 'lexical']);
  assert.deepEqual(parsed.groundingRequired, [true, true]);
});

test('@spec:AC-057 @spec:AC-058 @spec:AC-059 @spec:AC-060 @spec:AC-061 OpenAI provider builds Responses requests, handles failures, and traces embeddings', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIProviderError, OpenAIResponsesProvider

class FakeTransport:
    def __init__(self):
        self.calls = []
    def post_json(self, url, *, headers, payload):
        self.calls.append({"url": url, "headers": headers, "payload": payload})
        if url.endswith("/embeddings"):
            return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
        return {"id": "resp-1", "status": "completed", "output": []}

transport = FakeTransport()
provider = OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), transport)
schema = {"name": "intent", "schema": {"type": "object", "properties": {"intent": {"type": "string"}}, "required": ["intent"], "additionalProperties": False}}
payload = provider.build_response_payload(input_messages=[{"role": "user", "content": "oi"}], json_schema=schema)
provider.create_response(input_messages=[{"role": "user", "content": "oi"}], json_schema=schema)
embedding = provider.create_embedding(text="consulta", embedding_version="runtime-v1")

class FailingTransport:
    def post_json(self, url, *, headers, payload):
        return {"status": "failed", "error": {"message": "boom"}}
failed = False
try:
    OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), FailingTransport()).create_response(input_messages=[])
except OpenAIProviderError:
    failed = True

print(json.dumps({
  "responsesUrl": transport.calls[0]["url"],
  "model": payload["model"],
  "effort": payload["reasoning"]["effort"],
  "format": payload["text"]["format"]["type"],
  "failed": failed,
  "embedding": {"model": embedding.model, "version": embedding.embedding_version, "vector": embedding.vector, "indexed": bool(embedding.indexed_at)}
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.responsesUrl, 'https://api.openai.com/v1/responses');
  assert.equal(parsed.model, 'gpt-5.6-luna');
  assert.equal(parsed.effort, 'low');
  assert.equal(parsed.format, 'json_schema');
  assert.equal(parsed.failed, true);
  assert.deepEqual(parsed.embedding, {
    model: 'text-embedding-3-small',
    version: 'runtime-v1',
    vector: [0.1, 0.2, 0.3],
    indexed: true,
  });
});

test('@spec:AC-062 @spec:AC-063 LangSmith observer redacts and local audit survives failures', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.langsmith_observer import LangSmithObserver
from ai_agent_runtime.observability import AuditEvent, AuditStore, RuntimeObservability

class BrokenTransport:
    def send(self, payload):
        raise RuntimeError("offline")

event = AuditEvent(
  conversation_id="conv-1",
  organization_id="org-1",
  intent="SCHEDULING_REQUEST",
  decision="CALL_TOOL",
  tool_called="consultar_agenda",
  handoff_reason="Paciente +55 71 99999-8888 ana@example.com",
  timestamp="2026-08-20T20:14:00+00:00",
)
observer = LangSmithObserver(api_key="test", project="proj", transport=BrokenTransport())
payload = observer.prepare_payload(event)
store = AuditStore()
RuntimeObservability(store, observer).record_event(event)
print(json.dumps({"payload": payload, "stored": len(store.events)}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.stored, 1);
  assert.equal(parsed.payload.handoffReason.includes('[REDACTED_PHONE]'), true);
  assert.equal(parsed.payload.handoffReason.includes('[REDACTED_EMAIL]'), true);
  assert.equal(parsed.payload.timestamp, '2026-08-20T20:14:00+00:00');
});

test('@spec:AC-064 @spec:AC-065 @spec:AC-066 Google Calendar provider is guarded and never invents slots', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.google_calendar import GoogleCalendarProvider
from ai_agent_runtime.scheduling import CalendarTools, SchedulingGuardError, update_scheduling_context
from ai_agent_runtime.state import AgentState

class FakeGoogleTransport:
    def __init__(self):
        self.calls = []
    def post(self, path, payload):
        self.calls.append(("post", path, payload))
        if path == "/freeBusy":
            return {"availableSlots": [{"start": "2026-08-21T10:00:00-03:00", "end": "2026-08-21T10:30:00-03:00"}]}
        return {"id": "event-1", **payload}
    def patch(self, path, payload):
        self.calls.append(("patch", path, payload))
        return {"id": path.split("/")[-1], **payload}
    def delete(self, path):
        self.calls.append(("delete", path, {}))
        return {"cancelled": True}

transport = FakeGoogleTransport()
provider = GoogleCalendarProvider(calendar_id="cal-1", transport=transport)
tools = CalendarTools(provider)
blocked = False
try:
    tools.consultar_agenda(AgentState("conv-1", "org-1", "Quanto custa?"), {"timeMin": "a", "timeMax": "b"})
except SchedulingGuardError:
    blocked = True
active = update_scheduling_context(AgentState("conv-2", "org-1", "Tem horario sexta?"))
slots = tools.consultar_agenda(active, {"timeMin": "2026-08-21T00:00:00-03:00", "timeMax": "2026-08-22T00:00:00-03:00"})
created = provider.create_appointment(organization_id="org-1", payload={"summary": "Consulta"})
rescheduled = provider.reschedule_appointment(organization_id="org-1", appointment_id="event-1", payload={"summary": "Consulta 2"})
cancelled = provider.cancel_appointment(organization_id="org-1", appointment_id="event-1")
print(json.dumps({"blocked": blocked, "slots": slots, "calls": transport.calls, "created": created["id"], "rescheduled": rescheduled["id"], "cancelled": cancelled["cancelled"]}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.blocked, true);
  assert.deepEqual(parsed.slots, [{ start: '2026-08-21T10:00:00-03:00', end: '2026-08-21T10:30:00-03:00' }]);
  assert.equal(parsed.calls[0][1], '/freeBusy');
  assert.equal(Object.hasOwn(parsed.calls[0][2], 'organizationId'), false);
  assert.equal(parsed.created, 'event-1');
  assert.equal(parsed.rescheduled, 'event-1');
  assert.equal(parsed.cancelled, true);
});

test('@spec:AC-064 @spec:AC-066 Google Calendar HTTP transport refreshes expired access tokens without manual rotation', () => {
  const output = runPython(`
import json
import ai_agent_runtime.integrations.google_calendar as google_calendar
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.google_calendar import GoogleCalendarHttpTransport

class Unauthorized(Exception):
    code = 401

class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, traceback):
        return False
    def read(self):
        return json.dumps(self.payload).encode("utf-8")

calls = []
def fake_urlopen(req, timeout=30):
    calls.append({
        "url": req.full_url,
        "method": req.get_method(),
        "authorization": req.headers.get("Authorization"),
        "data": req.data.decode("utf-8") if req.data else None,
    })
    if len(calls) == 1:
        raise Unauthorized("expired")
    if req.full_url == "https://oauth2.googleapis.com/token":
        return FakeResponse({"access_token": "ya29.new-access-token", "expires_in": 3600, "token_type": "Bearer"})
    return FakeResponse({"id": "calendar-1"})

original = google_calendar.request.urlopen
google_calendar.request.urlopen = fake_urlopen
try:
    transport = GoogleCalendarHttpTransport(IntegrationConfig(
        google_calendar_access_token="ya29.old-access-token",
        google_calendar_refresh_token="1//refresh-token",
        google_oauth_client_id="client-id",
        google_oauth_client_secret="client-secret",
    ))
    result = transport.get("/calendars/calendar-1")
finally:
    google_calendar.request.urlopen = original

print(json.dumps({
  "result": result,
  "refreshCount": transport.refresh_count,
  "urls": [call["url"] for call in calls],
  "retryAuthorization": calls[-1]["authorization"],
  "tokenPayload": calls[1]["data"],
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.result.id, 'calendar-1');
  assert.equal(parsed.refreshCount, 1);
  assert.deepEqual(parsed.urls, [
    'https://www.googleapis.com/calendar/v3/calendars/calendar-1',
    'https://oauth2.googleapis.com/token',
    'https://www.googleapis.com/calendar/v3/calendars/calendar-1',
  ]);
  assert.equal(parsed.retryAuthorization, 'Bearer ya29.new-access-token');
  assert.match(parsed.tokenPayload, /grant_type=refresh_token/);
});
