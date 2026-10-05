const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

const cases = [
  ['@spec:AC-500', 'seven_sources'],
  ['@spec:AC-501', 'idempotency'],
  ['@spec:AC-502', 'one_update'],
  ['@spec:AC-503', 'isolation'],
  ['@spec:AC-504', 'organization'],
  ['@spec:AC-505', 'lifecycle'],
  ['@spec:AC-506', 'atomicity'],
  ['@spec:AC-507', 'chunking'],
  ['@spec:AC-508', 'safe_reports'],
  ['@spec:AC-509', 'invalid_sources'],
  ['@spec:AC-510', 'dry_run'],
  ['@spec:AC-511', 'validation'],
  ['@spec:AC-512', 'smoke_rollback'],
];
for (const [criterion, name] of cases) {
  test(`${criterion} PostgreSQL admin ${name}`, () => {
    const result = spawnSync(process.env.ADMIN_TEST_PYTHON || 'python3', ['test/ai-knowledge-admin/cases.py', name], {
      encoding: 'utf8', timeout: 120000,
      env: { ...process.env, PYTHONPATH: ['src', process.env.PYTHONPATH].filter(Boolean).join(':') },
    });
    assert.equal(result.status, 0, result.stderr || result.stdout || String(result.error));
    assert.deepEqual(JSON.parse(result.stdout), { passed: name });
  });
}
