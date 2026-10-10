'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

function probe(source) {
  const run = spawnSync('python3', ['-c', `import json,runpy\np=runpy.run_path('test/ai-hartmann-knowledge-readiness/grounding_probe.py')\n${source}`], {
    cwd: process.cwd(), env: { ...process.env, PYTHONPATH: 'src' }, encoding: 'utf8',
  });
  assert.equal(run.status, 0, run.stderr || run.stdout);
  return JSON.parse(run.stdout);
}

test('@spec:AC-554 local probe exposes only synthetic claim text, source and rejection rule', () => {
  const result = probe("print(json.dumps({'paraphrase':p['inspect_response'](p['RESPONSES']['paraphrased_price']),'time':p['inspect_response'](p['RESPONSES']['invented_time']),'invitation':p['inspect_response'](p['RESPONSES']['price_and_invite'])}))");
  assert.match(result.paraphrase.syntheticResponse, /R\$ 120/);
  assert.equal(result.paraphrase.claims[0].classification, 'FACTUAL');
  assert.ok(result.paraphrase.syntheticSources.some((source) => source.includes('custa R$ 120')));
  assert.match(result.paraphrase.claims[0].rule, /_grounding_claim_diagnostics/);
  assert.equal(result.time.claims.length, 2);
  assert.ok(result.time.claims.every((claim) => claim.text && claim.rule));
  assert.match(result.time.claims[1].candidateSyntheticSource, /agendamento/);
  assert.deepEqual(result.invitation.claims.map((claim) => claim.classification), ['FACTUAL', 'NON_FACTUAL']);
  assert.match(result.invitation.claims[0].supportingSyntheticSource, /R\$ 120/);
});

test('@spec:AC-555 bounded price and budget paraphrases need exact authorized conditions', () => {
  const result = probe(String.raw`
from ai_agent_runtime.whatsapp.zapi_server import validate_live_grounding
sources=p['SOURCES']
def verdict(text, evidence=sources):
    x=validate_live_grounding(text,evidence_count=len(evidence),evidence=evidence)
    return [x['passed'],x['requiresEvidence']]
print(json.dumps({
 'literal':verdict(p['RESPONSES']['literal_price']),
 'paraphrase':verdict(p['RESPONSES']['paraphrased_price']),
 'budget':verdict(p['RESPONSES']['budget_policy']),
 'noBudgetSource':verdict(p['RESPONSES']['budget_policy'],sources[:1]),
 'invented':verdict(p['RESPONSES']['invented_price']),
 'diverging':verdict(p['RESPONSES']['diverging_price']),
 'negated':verdict('O orçamento final não depende da avaliação.'),
}))`);
  assert.deepEqual(result, {
    literal: [true, true], paraphrase: [true, true], budget: [true, true],
    noBudgetSource: [false, true], invented: [false, true], diverging: [false, true], negated: [false, true],
  });
});

test('@spec:AC-556 neutral invitation is not a fact and invented appointment time is factual', () => {
  const result = probe(String.raw`
from ai_agent_runtime.whatsapp.zapi_server import validate_live_grounding
def verdict(text):
    x=validate_live_grounding(text,evidence_count=len(p['SOURCES']),evidence=p['SOURCES'])
    return [x['passed'],x['requiresEvidence']]
print(json.dumps({
 'invite':verdict(p['RESPONSES']['commercial_invite']),
 'priceAndInvite':verdict(p['RESPONSES']['price_and_invite']),
 'priceAndScheduling':verdict(p['RESPONSES']['price_and_scheduling']),
 'neutral':verdict(p['RESPONSES']['neutral_question']),
 'inventedTime':verdict(p['RESPONSES']['invented_time']),
 'inventedTimeOnly':verdict('A avaliação pode ser marcada amanhã às 10h.'),
 'inventedPayment':verdict(p['RESPONSES']['invented_payment']),
 'inventedResult':verdict(p['RESPONSES']['invented_result']),
 'clinical':verdict(p['RESPONSES']['clinical_advice']),
}))`);
  assert.deepEqual(result, {
    invite: [true, false], priceAndInvite: [true, true], priceAndScheduling: [true, true],
    neutral: [true, false], inventedTime: [false, true], inventedTimeOnly: [false, true],
    inventedPayment: [false, true], inventedResult: [false, true], clinical: [false, true],
  });
});

test('@spec:AC-557 CRM dispatch accepts supported response, salvages safe part and handoffs twice-unsupported fact', () => {
  const result = probe(String.raw`
run=p['dispatch']; r=p['RESPONSES']
print(json.dumps({
 'supported':run([r['price_and_invite']]),
 'partial':run([r['partial']]),
 'unsupported':run([r['invented_price'],r['invented_price']]),
 'inventedTime':run(['A avaliação pode ser marcada amanhã às 10h.']*2),
}))`);
  assert.deepEqual([result.supported.action, result.partial.action, result.unsupported.action, result.inventedTime.action],
    ['SEND_MESSAGE', 'SEND_MESSAGE', 'HANDOFF', 'HANDOFF']);
  assert.equal(result.supported.modelCalls, 1);
  assert.equal(result.partial.reasonCode, 'SUPPORTED_PARTIAL_RESPONSE');
  assert.doesNotMatch(result.partial.message, /R\$ 190/);
  for (const item of [result.unsupported, result.inventedTime]) {
    assert.equal(item.modelCalls, 2);
    assert.equal(item.regenerationUsed, true);
    assert.equal(item.reasonCode, 'UNSUPPORTED_FACTUAL_CLAIM');
    assert.equal(item.decisionOrigin, 'GROUNDING');
    assert.equal(item.message, null);
  }
  for (const item of Object.values(result)) {
    assert.equal(item.promptTopicCoverage, 'COMPLETE');
    assert.equal(item.promptChunkIds.length, 4);
    assert.doesNotMatch(JSON.stringify(item.safeTerminalLog), /R\$ 120|R\$ 190|synthetic-service-token|amanhã às 10h/);
  }
});
