const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

for (const name of ['production_entrypoint', 'canonical_handler_and_webhook']) {
  test(`@spec:AC-532 CRM dispatch on Production listener ${name}`, () => {
    const result = spawnSync(process.env.ADMIN_TEST_PYTHON || '.venv/bin/python',
      ['test/ai-crm-dispatch/listener_cases.py', name], {
        encoding: 'utf8', timeout: 30000,
        env: { ...process.env, PYTHONPATH: 'src' },
      });
    assert.equal(result.status, 0, result.stderr || result.stdout || String(result.error));
    assert.deepEqual(JSON.parse(result.stdout), { passed: name });
  });
}
