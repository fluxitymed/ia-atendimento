const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const cases = [
  ['@spec:AC-513','authentication'], ['@spec:AC-514','organization'], ['@spec:AC-515','dry_run'],
  ['@spec:AC-516','ingest'], ['@spec:AC-517','idempotency'], ['@spec:AC-518','validation'],
  ['@spec:AC-519','publication'], ['@spec:AC-520','read_isolation'], ['@spec:AC-521','write_isolation'],
  ['@spec:AC-522','concurrency'], ['@spec:AC-523','invalid_source'], ['@spec:AC-524','safe_output'],
  ['@spec:AC-525','listing'], ['@spec:AC-526','review'], ['@spec:AC-527','smoke_test'],
  ['@spec:AC-528','audit'], ['@spec:AC-529','cli_compatibility'], ['@spec:AC-530','http_boundary'],
];
for (const [criterion, name] of cases) {
  test(`${criterion} CRM knowledge API ${name}`, () => {
    const result = spawnSync(process.env.ADMIN_TEST_PYTHON || '.venv/bin/python', ['test/ai-knowledge-crm-api/api_cases.py', name], {
      encoding: 'utf8', timeout: 120000,
      env: { ...process.env, PYTHONPATH: ['src', process.env.PYTHONPATH].filter(Boolean).join(':') },
    });
    assert.equal(result.status, 0, result.stderr || result.stdout || String(result.error));
    assert.deepEqual(JSON.parse(result.stdout), { passed: name });
  });
}
