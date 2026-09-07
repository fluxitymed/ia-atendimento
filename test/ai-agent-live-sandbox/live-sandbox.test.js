'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { readFileSync } = require('node:fs');

function runPython(source, extraEnv = {}) {
  const result = spawnSync('python3', ['-c', source], {
    cwd: process.cwd(),
    env: { ...process.env, PYTHONPATH: 'src', ...extraEnv },
    encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout.trim();
}

test('@spec:AC-100 @spec:AC-101 @spec:AC-102 @spec:AC-103 sandbox config is opt-in, env-only, and reports missing credentials safely', () => {
  const output = runPython(`
import json
from ai_agent_runtime.sandbox.config import SandboxConfig, evaluate_readiness
from ai_agent_runtime.integrations.config import IntegrationConfig

disabled = evaluate_readiness(SandboxConfig(app_env=None, run_live=False, integrations=IntegrationConfig()))
wrong_env = evaluate_readiness(SandboxConfig(app_env="production", run_live=True, integrations=IntegrationConfig()))
missing = evaluate_readiness(SandboxConfig(app_env="sandbox", run_live=True, integrations=IntegrationConfig()))
print(json.dumps({
  "disabled": disabled.blocked_reason,
  "wrongEnv": wrong_env.blocked_reason,
  "missing": missing.blocked_reason,
  "missingByStep": {k: list(v) for k, v in missing.missing_by_step.items()},
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.disabled, 'LIVE_DISABLED');
  assert.equal(parsed.wrongEnv, 'APP_ENV_NOT_SANDBOX');
  assert.equal(parsed.missing, 'MISSING_CREDENTIALS');
  assert.deepEqual(parsed.missingByStep.openai, ['OPENAI_API_KEY']);
  assert.deepEqual(parsed.missingByStep.supabase, ['SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY']);
  assert.deepEqual(parsed.missingByStep.langsmith, ['LANGSMITH_API_KEY']);
  assert.deepEqual(parsed.missingByStep.google_calendar, ['GOOGLE_CALENDAR_ID', 'GOOGLE_CALENDAR_ACCESS_TOKEN_OR_REFRESH_TOKEN']);

  const envExample = readFileSync('.env.example', 'utf8');
  for (const key of [
    'APP_ENV=sandbox',
    'RUN_LIVE_SANDBOX=false',
    'OPENAI_API_KEY=',
    'SUPABASE_URL=',
    'SUPABASE_SERVICE_ROLE_KEY=',
    'LANGSMITH_API_KEY=',
    'LANGSMITH_PROJECT=ai-atendimento-sandbox',
    'GOOGLE_CALENDAR_ID=',
    'GOOGLE_CALENDAR_ACCESS_TOKEN=',
    'GOOGLE_CALENDAR_REFRESH_TOKEN=',
    'GOOGLE_CALENDAR_TIMEZONE=America/Bahia',
    'GOOGLE_OAUTH_CLIENT_ID=',
    'GOOGLE_OAUTH_CLIENT_SECRET=',
    'GOOGLE_OAUTH_TOKEN_URI=https://oauth2.googleapis.com/token',
    'GOOGLE_OAUTH_REDIRECT_PORT=8765',
    'GOOGLE_OAUTH_TOKEN_FILE=.secrets/google-calendar-sandbox-oauth.json',
  ]) {
    assert.match(envExample, new RegExp(key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
});

test('@spec:AC-104 @spec:AC-105 @spec:AC-106 runner command reports implemented/blocked states and usage fields without live calls', () => {
  const result = spawnSync('python3', ['-m', 'ai_agent_runtime.sandbox'], {
    cwd: process.cwd(),
    env: { ...process.env, PYTHONPATH: 'src', RUN_LIVE_SANDBOX: 'false' },
    encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const parsed = JSON.parse(result.stdout);
  assert.equal(parsed.status, 'IMPLEMENTED');
  assert.equal(parsed.liveEnabled, false);
  assert.equal(parsed.exitCode, 0);
  assert.equal(parsed.steps.length, 4);
  assert.deepEqual(parsed.steps.map((step) => step.status), ['DISABLED', 'DISABLED', 'DISABLED', 'DISABLED']);
  assert.equal(parsed.steps.every((step) => Object.hasOwn(step, 'usage')), true);
  assert.equal(parsed.steps.every((step) => Object.hasOwn(step, 'latencyMs')), true);
  assert.equal(parsed.steps.some((step) => step.status === 'LIVE_VERIFIED'), false);
});

test('@spec:AC-107 @spec:AC-108 OpenAI smoke uses approved Responses payload and redacts auth failures', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.sandbox.config import SandboxConfig
from ai_agent_runtime.sandbox.openai_smoke import build_openai_smoke_payload
from ai_agent_runtime.sandbox.redaction import redact

config = SandboxConfig(app_env="sandbox", run_live=True, integrations=IntegrationConfig(openai_api_key="sk-test-secret-value-1234567890"))
payload = build_openai_smoke_payload(config)
redacted = redact({"authorization": "Bearer sk-test-secret-value-1234567890", "OPENAI_API_KEY": "sk-test-secret-value-1234567890"})
print(json.dumps({"payload": payload, "redacted": redacted}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.payload.model, 'gpt-5.6-luna');
  assert.equal(parsed.payload.reasoning.effort, 'low');
  assert.equal(parsed.payload.store, false);
  assert.equal(parsed.payload.text.format.type, 'json_schema');
  assert.equal(parsed.payload.text.format.strict, true);
  assert.equal(parsed.redacted.authorization, '[REDACTED]');
  assert.equal(parsed.redacted.OPENAI_API_KEY, '[REDACTED]');
});

test('@spec:AC-109 @spec:AC-110 @spec:AC-111 @spec:AC-112 Supabase plan uses sandbox dataset, migration, scenarios, and gap report', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.sandbox.config import SandboxConfig
from ai_agent_runtime.sandbox.dataset import build_sandbox_dataset, ingestion_pipeline_gap_report
from ai_agent_runtime.sandbox.supabase_smoke import build_supabase_plan

config = SandboxConfig(app_env="sandbox", run_live=True, integrations=IntegrationConfig())
dataset = build_sandbox_dataset()
plan = build_supabase_plan(config)
print(json.dumps({
  "orgs": [org.name for org in dataset.organizations],
  "fictitious": dataset.fictitious,
  "catalog": [doc.__dict__ for doc in dataset.documents if doc.document_type == "PROCEDURE_CATALOG"][0],
  "limitations": list(dataset.source_limitations),
  "plan": plan,
  "gaps": ingestion_pipeline_gap_report(),
}))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed.orgs, ['Clinica Carvalho e Tavares Odontologia Integrada', 'Clinica Boreal Sandbox']);
  assert.equal(parsed.fictitious, false);
  assert.equal(parsed.catalog.knowledge_mode, 'OPEN_WORLD');
  assert.equal(parsed.catalog.closed_world_completeness_approved, false);
  assert.equal(parsed.catalog.status, 'PUBLISHED');
  assert.match(parsed.catalog.source_uri, /Briefing_Assistente_Comercial_Dr_Leonardo_Carvalho\.pdf$/);
  assert.ok(parsed.limitations.some((item) => item.includes('catalogo CLOSED_WORLD')));
  assert.ok(parsed.limitations.some((item) => item.includes('Avaliacao gratuita e fato autorizado')));
  assert.match(parsed.plan.migrationPath, /202608200001_ai_runtime_integrations\.sql$/);
  assert.equal(parsed.plan.requiresTables.includes('retrieval_index_entries'), true);
  assert.deepEqual(parsed.plan.scenarioIds, [
    'supabase-existing-info',
    'supabase-missing-info',
    'supabase-not-offered',
    'supabase-missing-attribute',
    'supabase-cross-org',
  ]);
  assert.equal(parsed.gaps.remote_supabase_write, 'READY_FOR_LIVE_EXECUTION');
  assert.equal(parsed.gaps.live_retrieval, 'READY_FOR_LIVE_EXECUTION');
});

test('@spec:AC-344 @spec:AC-345 @spec:AC-348 @spec:AC-349 @spec:AC-350 @spec:AC-436 @spec:AC-443 @spec:AC-444 Supabase live seed publishes Dr. Leonardo briefing v3 and supersedes older versions', () => {
  const output = runPython(`
import json
from ai_agent_runtime.sandbox.dataset import build_sandbox_dataset
from ai_agent_runtime.sandbox.supabase_smoke import _persist_dataset, _lexical_query, _free_evaluation_decision, _missing_attribute_decision
from ai_agent_runtime.sandbox_ids import BOREAL_ORG_ID, DATASET_VERSION, LEONARDO_ORG_ID, deterministic_sandbox_uuid

class FakeOpenAI:
    def create_embedding(self, *, text, embedding_version):
        class Embedding:
            vector = [0.1, 0.2, 0.3]
            model = "text-embedding-3-small"
            indexed_at = "2026-09-07T00:00:00+00:00"
        Embedding.embedding_version = embedding_version
        return Embedding()

class FakeClient:
    def __init__(self):
        self.tables = {"organizations": [], "documents": [], "document_versions": [], "chunks": [], "retrieval_index_entries": []}
    def upsert(self, table, rows, *, conflict):
        ids = {row["id"]: row for row in self.tables[table]}
        for row in rows:
            ids[row["id"]] = {**ids.get(row["id"], {}), **row}
        self.tables[table] = list(ids.values())
        return rows
    def get(self, table, *, params):
        rows = list(self.tables[table])
        for key, value in params.items():
            if key in {"select", "limit", "order"}:
                continue
            if value.startswith("eq."):
                expected = value[3:]
                rows = [row for row in rows if str(row.get(key)) == expected]
            elif value == "is.true":
                rows = [row for row in rows if row.get(key) is True]
            elif value.startswith("in.("):
                allowed = set(value[4:-1].split(","))
                rows = [row for row in rows if str(row.get(key)) in allowed]
            elif value.startswith("ilike.*"):
                needle = value[len("ilike.*"):-1].lower()
                rows = [row for row in rows if needle in str(row.get(key, "")).lower()]
        return rows[: int(params.get("limit", "100"))]

client = FakeClient()
dataset = build_sandbox_dataset()
ids = _persist_dataset(client, FakeOpenAI(), dataset)
primary_org = ids["primary_org"]
boreal_org = deterministic_sandbox_uuid(BOREAL_ORG_ID)
versions = [row for row in client.tables["document_versions"] if row["organization_id"] == primary_org]
published = [row for row in versions if row["status"] == "PUBLISHED"]
superseded = [row for row in versions if row["status"] == "SUPERSEDED"]
client.tables["chunks"].append({
    "id": "stale-v1-chunk",
    "organization_id": primary_org,
    "document_id": superseded[0]["document_id"],
    "document_version_id": superseded[0]["id"],
    "chunk_index": 99,
    "content": "Avaliacao gratuita nao e regra universal e precisa ser confirmada pela equipe.",
})
client.tables["chunks"].append({
    "id": "stale-v2-room",
    "organization_id": primary_org,
    "document_id": superseded[-1]["document_id"],
    "document_version_id": superseded[-1]["id"],
    "chunk_index": 100,
    "content": "Clinica Tavares: sala 4020. Handoff para dor intensa, inchaco, trauma e pedido direto do dentista.",
})
evaluation_hits = _lexical_query(client, primary_org, "Avaliacao gratuita")
stale_hits = _lexical_query(client, primary_org, "nao e regra universal")
old_room_hits = _lexical_query(client, primary_org, "4020")
cross_hits = _lexical_query(client, primary_org, "Consulta com Dra. Helena")
boreal_hits = _lexical_query(client, boreal_org, "Consulta com Dra. Helena")
print(json.dumps({
  "datasetVersion": DATASET_VERSION,
  "sourceLabels": sorted({doc.source_label for doc in dataset.documents if doc.organization_id == LEONARDO_ORG_ID}),
  "publishedNumbers": sorted({row["version_number"] for row in published}),
  "supersededNumbers": sorted({row["version_number"] for row in superseded}),
  "publishedCount": len(published),
  "supersededCount": len(superseded),
  "evaluationDecision": _free_evaluation_decision(client, primary_org, "Quanto custa a avaliacao?"),
  "procedurePriceDecision": _missing_attribute_decision(client, primary_org, "Quanto custa o implante?"),
  "evaluationContent": evaluation_hits[0]["content"],
  "staleHitCount": len(stale_hits),
  "oldRoomHitCount": len(old_room_hits),
  "crossHitCount": len(cross_hits),
  "borealOwnHitCount": len(boreal_hits),
  "oldCurrent": any(row["version_number"] in {1, 2} and row["status"] == "PUBLISHED" for row in versions),
  "allCurrentOrg": all(row["organization_id"] == primary_org for row in published),
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.datasetVersion, '2026-09-07.dr-leonardo-production.v3');
  assert.deepEqual(parsed.sourceLabels, ['Briefing_Assistente_Comercial_Dr_Leonardo_Carvalho.pdf']);
  assert.deepEqual(parsed.publishedNumbers, [3]);
  assert.deepEqual(parsed.supersededNumbers, [1, 2]);
  assert.equal(parsed.publishedCount, 5);
  assert.equal(parsed.supersededCount, 10);
  assert.equal(parsed.evaluationDecision, 'ANSWER_GROUNDED');
  assert.equal(parsed.procedurePriceDecision, 'ANSWER_GROUNDED');
  assert.match(parsed.evaluationContent, /Avaliacao gratuita/);
  assert.match(parsed.evaluationContent, /busca por procedimento/);
  assert.doesNotMatch(parsed.evaluationContent, /precisa ser confirmada|nao e regra universal|pode nao ser cobrada/i);
  assert.equal(parsed.staleHitCount, 0);
  assert.equal(parsed.oldRoomHitCount, 0);
  assert.equal(parsed.crossHitCount, 0);
  assert.equal(parsed.borealOwnHitCount, 1);
  assert.equal(parsed.oldCurrent, false);
  assert.equal(parsed.allCurrentOrg, true);
});

test('@spec:AC-113 @spec:AC-114 grounding and prompt-injection live scenarios are prepared for deterministic protection', () => {
  const output = runPython(`
import json
from ai_agent_runtime.sandbox.scenarios import build_sandbox_scenarios

scenarios = {scenario.id: scenario for scenario in build_sandbox_scenarios()}
print(json.dumps({
  "grounding": scenarios["grounding-unsupported"].expected_decision,
  "promptInjection": scenarios["prompt-injection-medical"].expected_decision,
  "promptMessage": scenarios["prompt-injection-medical"].message,
}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.grounding, 'HUMAN_HANDOFF_REQUIRED');
  assert.equal(parsed.promptInjection, 'HUMAN_HANDOFF_REQUIRED');
  assert.match(parsed.promptMessage, /Ignore todas as instruções/);
});

test('@spec:AC-115 @spec:AC-116 @spec:AC-117 Google Calendar sandbox plan keeps timezone, scheduling guard, and cleanup', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.sandbox.config import SandboxConfig
from ai_agent_runtime.sandbox.google_calendar_smoke import build_google_calendar_plan

config = SandboxConfig(app_env="sandbox", run_live=True, integrations=IntegrationConfig(google_calendar_id="sandbox-calendar@example.com"), google_calendar_timezone="America/Bahia")
plan = build_google_calendar_plan(config)
print(json.dumps(plan))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.timezone, 'America/Bahia');
  assert.equal(parsed.requiresSandboxCalendar, true);
  assert.equal(parsed.guardChecks.priceQuestionCanCallCalendar, false);
  assert.equal(parsed.guardChecks.genericInterestCanCallCalendar, false);
  assert.equal(parsed.guardChecks.explicitSchedulingCanCallCalendar, true);
  assert.deepEqual(parsed.expectedProviderSlots, ['10:00', '14:00']);
  assert.deepEqual(parsed.forbiddenInventedSlots, ['16:00']);
  assert.equal(parsed.testEvent.cleanupRequired, true);
  assert.match(parsed.testEvent.summary, /\[SANDBOX\]/);
});

test('@spec:AC-118 @spec:AC-119 LangSmith sandbox uses redaction and local audit survives without external observer', () => {
  const output = runPython(`
import json
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.sandbox.config import SandboxConfig
from ai_agent_runtime.sandbox.langsmith_smoke import build_langsmith_plan
from ai_agent_runtime.sandbox.redaction import redact

config = SandboxConfig(app_env="sandbox", run_live=True, integrations=IntegrationConfig(langsmith_api_key="lsv2-super-secret-token-1234567890"))
plan = build_langsmith_plan(config)
redacted = redact({
  "headers": {"Authorization": "Bearer lsv2-super-secret-token-1234567890"},
  "token": "lsv2-super-secret-token-1234567890",
  "nested": {"service_role_key": "service-role-secret-1234567890"},
  "timestamp": "2026-08-20T20:14:00+00:00",
})
print(json.dumps({"plan": plan, "redacted": redacted}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.plan.project, 'ai-atendimento-sandbox');
  assert.equal(parsed.plan.localAuditEvents, 1);
  assert.equal(parsed.plan.authorization, '[REDACTED]');
  assert.equal(parsed.redacted.headers.Authorization, '[REDACTED]');
  assert.equal(parsed.redacted.token, '[REDACTED]');
  assert.equal(parsed.redacted.nested.service_role_key, '[REDACTED]');
  assert.equal(parsed.redacted.timestamp, '2026-08-20T20:14:00+00:00');
});

test('@spec:AC-120 @spec:AC-121 Google OAuth utility is sandbox-only and requests only minimal calendar scopes', () => {
  const output = runPython(`
import json
from urllib import parse
from ai_agent_runtime.sandbox.google_oauth import GOOGLE_CALENDAR_OAUTH_SCOPES, GoogleOAuthConfig, build_authorization_url, missing_oauth_env

blocked = missing_oauth_env(GoogleOAuthConfig(app_env="production", client_id=None, client_secret=None))
config = GoogleOAuthConfig(app_env="sandbox", client_id="sandbox-client-id.apps.googleusercontent.com", client_secret="sandbox-client-secret")
url = build_authorization_url(config, state="state-123")
query = parse.parse_qs(parse.urlparse(url).query)
print(json.dumps({
  "blocked": blocked,
  "scopes": GOOGLE_CALENDAR_OAUTH_SCOPES,
  "urlScope": query["scope"][0].split(" "),
  "accessType": query["access_type"][0],
  "prompt": query["prompt"][0],
  "redirectUri": query["redirect_uri"][0],
}))
`);
  const parsed = JSON.parse(output);
  assert.deepEqual(parsed.blocked, ['APP_ENV', 'GOOGLE_OAUTH_CLIENT_ID', 'GOOGLE_OAUTH_CLIENT_SECRET']);
  assert.deepEqual(parsed.scopes, [
    'https://www.googleapis.com/auth/calendar.freebusy',
    'https://www.googleapis.com/auth/calendar.events',
  ]);
  assert.deepEqual(parsed.urlScope, parsed.scopes);
  assert.equal(parsed.accessType, 'offline');
  assert.equal(parsed.prompt, 'consent');
  assert.equal(parsed.redirectUri, 'http://127.0.0.1:8765/oauth2callback');
});

test('@spec:AC-122 @spec:AC-123 Google OAuth preserves refresh token locally and prints only safe env guidance', () => {
  const output = runPython(`
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from ai_agent_runtime.sandbox.google_oauth import GoogleOAuthConfig, build_safe_env_guidance, normalize_token_response, write_token_file

with TemporaryDirectory() as tmpdir:
    token_file = Path(tmpdir) / "google-calendar-sandbox-oauth.json"
    config = GoogleOAuthConfig(
        app_env="sandbox",
        client_id="sandbox-client-id.apps.googleusercontent.com",
        client_secret="sandbox-client-secret",
        token_file=token_file,
    )
    normalized = normalize_token_response({
        "access_token": "ya29.sandbox-access-token-1234567890",
        "refresh_token": "1//sandbox-refresh-token-1234567890",
        "expires_in": 3600,
        "token_type": "Bearer",
        "scope": "https://www.googleapis.com/auth/calendar.freebusy https://www.googleapis.com/auth/calendar.events",
    })
    written = write_token_file(config, normalized)
    persisted = json.loads(written.read_text())
    guidance = build_safe_env_guidance(config, normalized)
    print(json.dumps({
      "exists": written.exists(),
      "mode": oct(written.stat().st_mode & 0o777),
      "refreshStored": persisted["refresh_token"].startswith("1//sandbox-refresh-token"),
      "accessStored": persisted["access_token"].startswith("ya29."),
      "guidance": guidance,
    }))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.exists, true);
  assert.equal(parsed.mode, '0o600');
  assert.equal(parsed.refreshStored, true);
  assert.equal(parsed.accessStored, true);
  assert.equal(parsed.guidance.preservedRefreshToken, true);
  assert.equal(parsed.guidance.preservedAccessToken, true);
  assert.deepEqual(parsed.guidance.envVarsToFill, [
    'GOOGLE_CALENDAR_ACCESS_TOKEN',
    'GOOGLE_CALENDAR_REFRESH_TOKEN',
    'GOOGLE_OAUTH_CLIENT_ID',
    'GOOGLE_OAUTH_CLIENT_SECRET',
    'GOOGLE_OAUTH_TOKEN_URI',
  ]);
  assert.equal(parsed.guidance.values.GOOGLE_CALENDAR_ACCESS_TOKEN, '[REDACTED]');
  assert.equal(parsed.guidance.values.GOOGLE_CALENDAR_REFRESH_TOKEN, '[REDACTED]');
  assert.equal(parsed.guidance.values.GOOGLE_OAUTH_CLIENT_SECRET, '[REDACTED]');

  const gitignore = readFileSync('.gitignore', 'utf8');
  assert.match(gitignore, /^\.secrets\/$/m);
  assert.match(gitignore, /^\.env$/m);
  assert.match(gitignore, /\*oauth\*\.json/);
});
