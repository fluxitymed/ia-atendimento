'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {spawnSync} = require('node:child_process');
function run(name) {
  const result = spawnSync('python3', ['test/ai-whatsapp-zapi-provider/reliability_cases.py', 'Reliability.test_'+name], {
    env: {...process.env, PYTHONPATH: 'src'}, encoding: 'utf8', timeout: 20000,
  });
  assert.equal(result.status, 0, result.stdout+result.stderr);
}

test('@spec:AC-477 concurrent_duplicate', () => run('concurrent_duplicate'));
test('@spec:AC-478 stale_timer', () => run('stale_timer'));
test('@spec:AC-484 corrupt_store', () => run('corrupt_store'));
test('@spec:AC-477 two_processes', () => run('two_processes'));
test('@spec:AC-477 @spec:AC-480 restart_and_retry', () => run('restart_and_retry'));
test('@spec:AC-480 ambiguous_outbound', () => run('ambiguous_outbound'));
test('@spec:AC-480 before_outbound_failure', () => run('before_outbound_failure'));
test('@spec:AC-480 record_failure_after_send', () => run('record_failure_after_send'));
test('@spec:AC-484 write_failure_before_send', () => run('write_failure_before_send'));
test('@spec:AC-478 two_messages_batch_and_timer_race', () => run('two_messages_batch_and_timer_race'));
test('@spec:AC-478 @spec:AC-479 during_flush', () => run('during_flush'));
test('@spec:AC-479 conversation_isolation', () => run('conversation_isolation'));
test('@spec:AC-483 callbacks_aliases', () => run('callbacks_aliases'));
test('@spec:AC-481 fast_ingress', () => run('fast_ingress'));
test('@spec:AC-482 latency', () => run('latency'));
test('@spec:AC-481 http_media_and_early', () => run('http_media_and_early'));
test('@spec:AC-477 @spec:AC-478 service_singleton', () => run('service_singleton'));
test('@spec:AC-484 disk_failure_and_disappearance', () => run('disk_failure_and_disappearance'));
test('@spec:AC-477 batch_concurrent_duplicate', () => run('batch_concurrent_duplicate'));
