'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { readFileSync } = require('node:fs');

function runPython(source) {
  const result = spawnSync('python3', ['-c', source], {
    cwd: process.cwd(),
    env: { ...process.env, PYTHONPATH: 'src' },
    encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout.trim();
}

test('@spec:AC-172 @spec:AC-174 Evolution smoke blocks without credentials and prints names only', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import EvolutionWhatsAppConfig
from ai_agent_runtime.whatsapp.evolution_sandbox import run_evolution_live_smoke

result = run_evolution_live_smoke(EvolutionWhatsAppConfig())
print(json.dumps(result))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 'BLOCKED_MISSING_CREDENTIALS');
  assert.deepEqual(parsed.missing, [
    'EVOLUTION_API_BASE_URL',
    'EVOLUTION_API_KEY',
    'EVOLUTION_INSTANCE_NAME',
    'EVOLUTION_WEBHOOK_SECRET',
    'EVOLUTION_PUBLIC_WEBHOOK_URL',
  ]);
  assert.equal(JSON.stringify(parsed).includes('secret-value'), false);
});

test('@spec:AC-173 Evolution smoke plans all live scenarios and never marks LIVE_VERIFIED without real calls', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import EvolutionWhatsAppConfig
from ai_agent_runtime.whatsapp.evolution_sandbox import run_evolution_live_smoke

cfg = EvolutionWhatsAppConfig(
    base_url="https://evolution.example",
    api_key="secret-value",
    instance_name="clinic-a",
    webhook_secret="hook-secret",
    public_webhook_url="https://public.example",
)
result = run_evolution_live_smoke(cfg)
print(json.dumps(result))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 'READY_FOR_LIVE_EXECUTION');
  assert.equal(parsed.webhookPath, '/webhooks/evolution/whatsapp');
  assert.equal(parsed.liveVerifiedRequiresRealEvolutionCalls, true);
  assert.deepEqual(parsed.scenarios, [
    'connection_state',
    'create_instance',
    'qr_connect',
    'webhook_setup',
    'inbound_text',
    'outbound_text',
    'inbound_audio',
    'inbound_image',
    'inbound_document',
    'duplicate_webhook',
    'self_message',
    'handoff',
    'scheduling',
  ]);
  assert.equal(JSON.stringify(parsed).includes('secret-value'), false);
});

test('@spec:AC-169 @spec:AC-170 @spec:AC-171 sandbox guide documents exact Evolution commands', () => {
  const guide = readFileSync('.spec/features/ai-whatsapp-evolution-provider/evolution-sandbox.md', 'utf8');
  assert.match(guide, /ai_agent_runtime\.whatsapp\.evolution_server/);
  assert.match(guide, /evolution_sandbox status/);
  assert.match(guide, /evolution_sandbox create-instance/);
  assert.match(guide, /evolution_sandbox connect/);
  assert.match(guide, /evolution_sandbox set-webhook/);
  assert.match(guide, /\/webhooks\/evolution\/whatsapp/);
});

test('@spec:AC-176 Evolution feature does not alter CRM, RAG, Calendar, or grounding contracts', () => {
  const files = [
    'src/ai_agent_runtime/crm.py',
    'src/ai_agent_runtime/retrieval.py',
    'src/ai_agent_runtime/scheduling.py',
    'src/ai_agent_runtime/grounding.py',
  ];
  for (const file of files) {
    const content = readFileSync(file, 'utf8');
    assert.doesNotMatch(content, /Evolution|EVOLUTION|evolution/);
  }
});
