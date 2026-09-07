'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

function runPython(source, env = {}) {
  const result = spawnSync('python3', ['-c', source], {
    cwd: process.cwd(),
    env: { ...process.env, ...env, PYTHONPATH: 'src' },
    encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout.trim();
}

test('@spec:AC-154 Meta live smoke blocks by credential names only and never prints secret values', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import MetaWhatsAppConfig
from ai_agent_runtime.whatsapp.meta_sandbox import run_meta_live_smoke

result = run_meta_live_smoke(MetaWhatsAppConfig())
print(json.dumps(result))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 'BLOCKED_MISSING_CREDENTIALS');
  assert.deepEqual(parsed.missing, [
    'META_WHATSAPP_ACCESS_TOKEN',
    'META_WHATSAPP_PHONE_NUMBER_ID',
    'META_WHATSAPP_BUSINESS_ACCOUNT_ID',
    'META_WHATSAPP_VERIFY_TOKEN',
    'META_WHATSAPP_APP_SECRET',
    'META_WHATSAPP_PUBLIC_WEBHOOK_URL',
  ]);
  assert.equal(JSON.stringify(parsed).includes('secret-value'), false);
  assert.equal(JSON.stringify(parsed).includes('token-value'), false);
});

test('@spec:AC-155 Meta live smoke declares all required scenarios and does not mark LIVE_VERIFIED without real Meta calls', () => {
  const output = runPython(`
import json
from ai_agent_runtime.whatsapp import MetaWhatsAppConfig
from ai_agent_runtime.whatsapp.meta_sandbox import run_meta_live_smoke

cfg = MetaWhatsAppConfig(
    access_token="token-value",
    phone_number_id="phone-123",
    business_account_id="waba-123",
    verify_token="verify-value",
    app_secret="secret-value",
    public_webhook_url="https://example.test/webhooks/meta/whatsapp",
)
result = run_meta_live_smoke(cfg)
print(json.dumps(result))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 'READY_FOR_LIVE_EXECUTION');
  assert.equal(parsed.webhookPath, '/webhooks/meta/whatsapp');
  assert.equal(parsed.liveVerifiedRequiresRealMetaCalls, true);
  assert.deepEqual(parsed.scenarios, [
    'webhook_verification',
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
});
