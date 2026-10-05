const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

function runPython(code) {
  const result = spawnSync('python3', ['-c', code], {
    encoding: 'utf8',
    env: { ...process.env, PYTHONPATH: 'src' },
  });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

const fixture = String.raw`
import json
from ai_agent_runtime.whatsapp.zapi_server import ZApiRuntimeRetrieval

A = '38002ccb-9edb-4dcb-aacf-76c0b6ca1692'
B = '11111111-1111-4111-8111-111111111111'

def version(id, org, doc, number, status='PUBLISHED', valid=True, **extra):
    return {'id': id, 'organization_id': org, 'document_id': doc, 'version_number': number,
            'status': status, 'processing_valid': valid, **extra}

def chunk(id, org, doc, ver, content):
    return {'id': id, 'organization_id': org, 'document_id': doc,
            'document_version_id': ver, 'content': content}

VERSIONS = [
    version('a-old', A, 'doc-a', 1),
    version('a-current', A, 'doc-a', 2),
    version('b-current', B, 'doc-b', 1),
    version('a-draft', A, 'doc-draft', 1, 'DRAFT'),
    version('a-inactive', A, 'doc-inactive', 1, 'INACTIVE'),
    version('a-superseded', A, 'doc-superseded', 1, 'SUPERSEDED'),
    version('a-invalid', A, 'doc-invalid', 1, valid=False),
    version('a-expired', A, 'doc-expired', 1, effective_until='2020-01-01T00:00:00Z'),
]
CHUNKS = [
    chunk('a-good', A, 'doc-a', 'a-current', 'Hartmann atende na Rua das Flores.'),
    chunk('a-old-hit', A, 'doc-a', 'a-old', 'Hartmann antiga Rua das Flores.'),
    chunk('b-good', B, 'doc-b', 'b-current', 'Boreal atende na Rua das Flores.'),
    chunk('a-draft-hit', A, 'doc-draft', 'a-draft', 'Rascunho Rua das Flores.'),
    chunk('a-inactive-hit', A, 'doc-inactive', 'a-inactive', 'Inativo Rua das Flores.'),
    chunk('a-superseded-hit', A, 'doc-superseded', 'a-superseded', 'Superado Rua das Flores.'),
    chunk('a-invalid-hit', A, 'doc-invalid', 'a-invalid', 'Invalido Rua das Flores.'),
    chunk('a-expired-hit', A, 'doc-expired', 'a-expired', 'Expirado Rua das Flores.'),
    chunk('a-orphan', A, 'doc-b', 'a-current', 'Orfao Rua das Flores.'),
]

class Retrieval(ZApiRuntimeRetrieval):
    def __init__(self):
        self.calls = []
    def _get_json(self, table, params, *, endpoint):
        self.calls.append((table, params))
        if table == 'document_versions':
            return VERSIONS
        if table == 'chunks':
            return CHUNKS
        return []
`;

test('@spec:AC-494 @spec:AC-495 @spec:AC-496 @spec:AC-497 tenant and lifecycle filters reject foreign, stale and inconsistent chunks', () => {
  const result = runPython(fixture + String.raw`
r = Retrieval()
a = r.search(A, 'Rua das Flores')
b = r.search(B, 'Rua das Flores')
print(json.dumps({'a': [x['id'] for x in a], 'b': [x['id'] for x in b],
                  'scoped': all(call[1].get('organization_id') in ('eq.' + A, 'eq.' + B) for call in r.calls)}))
`);
  assert.deepEqual(result.a, ['a-good']);
  assert.deepEqual(result.b, ['b-good']);
  assert.equal(result.scoped, true);
});

test('@spec:AC-498 missing organization fails closed before querying', () => {
  const result = runPython(fixture + String.raw`
r = Retrieval()
try:
    r.search('', 'Rua das Flores')
    failed = False
except Exception as exc:
    failed = type(exc).__name__ == 'RetrievalIsolationError'
print(json.dumps({'failedClosed': failed, 'calls': len(r.calls)}))
`);
  assert.deepEqual(result, { failedClosed: true, calls: 0 });
});

test('@spec:AC-499 grounding rejects unrelated evidence, mismatched prices and cached-only chunks', () => {
  const result = runPython(fixture + String.raw`
from ai_agent_runtime.whatsapp.zapi_server import validate_live_grounding, _reusable_conversation_evidence
evidence = [{'id': 'a-good', 'organization_id': A, 'document_version_id': 'a-current',
             'content': 'A clinica oferece Botox por R$ 900.'}]
unrelated = validate_live_grounding('A clinica oferece implante.', evidence_count=1, evidence=evidence)
wrong_price = validate_live_grounding('Botox custa R$ 700 na clinica.', evidence_count=1, evidence=evidence)
opposite = validate_live_grounding('A clinica oferece Botox.', evidence_count=1,
    evidence=[{'content': 'A clinica nao oferece Botox.'}])
mixed_price = validate_live_grounding('Botox custa R$ 900 na clinica.', evidence_count=1,
    evidence=[{'content': 'Botox custa R$ 700. Preenchimento custa R$ 900.'}])
grounded = validate_live_grounding('A clinica oferece Botox por R$ 900.', evidence_count=1, evidence=evidence)
cached = [{'id': 'a-old-hit', 'organization_id': A, 'document_version_id': 'a-old',
           'content': 'Fato antigo', 'scopeTerms': ['botox'], 'datasetVersion': 'sandbox-v3'}]
reused = _reusable_conversation_evidence(cached, organization_id=A, query='botox', current_evidence=evidence)
print(json.dumps({'unrelated': unrelated['passed'], 'wrongPrice': wrong_price['passed'], 'opposite': opposite['passed'], 'mixedPrice': mixed_price['passed'],
                  'grounded': grounded['passed'], 'reused': len(reused)}))
`);
  assert.deepEqual(result, { unrelated: false, wrongPrice: false, opposite: false, mixedPrice: false, grounded: true, reused: 0 });
});

test('@spec:AC-499 truncated closed-world catalog cannot justify a negative answer', () => {
  const result = runPython(fixture + String.raw`
class LargeCatalog(Retrieval):
    def _closed_world_catalog_versions(self, organization_id):
        return {'a-current': 'doc-a'}
    def _chunks_for_versions(self, *, organization_id, version_ids):
        return [chunk('item-' + str(i), A, 'doc-a', 'a-current', 'Procedimento listado') for i in range(100)]
r = LargeCatalog()
class InconsistentCatalog(LargeCatalog):
    def _chunks_for_versions(self, *, organization_id, version_ids):
        return [chunk('orphan', A, 'doc-b', 'a-current', 'Botox')]
print(json.dumps({'decision': r.closed_world_procedure_decision(A, 'Voces fazem transplante capilar?'),
                  'inconsistent': InconsistentCatalog().closed_world_procedure_decision(A, 'Voces fazem transplante capilar?')}))
`);
  assert.equal(result.decision, null);
  assert.equal(result.inconsistent, null);
});
