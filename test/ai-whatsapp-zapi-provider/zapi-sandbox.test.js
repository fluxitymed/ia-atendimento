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

test('@spec:AC-194 Z-API smoke blocks without credentials and prints names only', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_sandbox import run_zapi_live_smoke

result = run_zapi_live_smoke(ZApiWhatsAppConfig())
print(json.dumps(result))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 'BLOCKED_MISSING_CREDENTIALS');
  assert.deepEqual(parsed.missing, [
    'ZAPI_BASE_URL',
    'ZAPI_INSTANCE_ID',
    'ZAPI_INSTANCE_TOKEN',
    'ZAPI_CLIENT_TOKEN',
    'ZAPI_PUBLIC_WEBHOOK_URL',
  ]);
  assert.equal(JSON.stringify(parsed).includes('secret-value'), false);
});

test('@spec:AC-195 Z-API smoke plans all live scenarios and never marks LIVE_VERIFIED without real calls', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_sandbox import run_zapi_live_smoke

cfg = ZApiWhatsAppConfig(
    base_url="https://api.z-api.io",
    instance_id="clinic-a",
    instance_token="instance-secret-value",
    client_token="client-secret-value",
    public_webhook_url="https://public.example",
)
result = run_zapi_live_smoke(cfg)
print(json.dumps(result))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 'READY_FOR_LIVE_EXECUTION');
  assert.equal(parsed.webhookPath, '/webhooks/zapi/whatsapp');
  assert.equal(parsed.liveVerifiedRequiresRealZApiCalls, true);
  assert.deepEqual(parsed.scenarios, [
    'validate_config',
    'instance_status',
    'qr_code',
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
  assert.equal(JSON.stringify(parsed).includes('instance-secret-value'), false);
  assert.equal(JSON.stringify(parsed).includes('client-secret-value'), false);
});

test('@spec:AC-191 @spec:AC-192 @spec:AC-193 sandbox guide documents exact Z-API commands', () => {
  const guide = readFileSync('.spec/features/ai-whatsapp-zapi-provider/zapi-sandbox.md', 'utf8');
  assert.match(guide, /ai_agent_runtime\.whatsapp\.zapi_server/);
  assert.match(guide, /zapi_sandbox status/);
  assert.match(guide, /zapi_sandbox qr-code/);
  assert.match(guide, /zapi_sandbox set-webhook/);
  assert.match(guide, /\/webhooks\/zapi\/whatsapp/);
  assert.match(guide, /Z-API opera sessao de WhatsApp Web/);
  assert.match(guide, /nao documenta secret, signature ou header custom/);
});

test('@spec:AC-197 @spec:AC-420 Z-API feature does not alter CRM, RAG, Calendar, or grounding contracts', () => {
  const files = [
    'src/ai_agent_runtime/crm.py',
    'src/ai_agent_runtime/retrieval.py',
    'src/ai_agent_runtime/scheduling.py',
    'src/ai_agent_runtime/grounding.py',
  ];
  for (const file of files) {
    const content = readFileSync(file, 'utf8');
    assert.doesNotMatch(content, /ZApi|ZAPI|Z-API|zapi/);
  }
});
