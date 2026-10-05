from __future__ import annotations

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from ai_agent_runtime.admin.markdown import KnowledgeError, chunk_markdown, read_sources
from ai_agent_runtime.admin.knowledge import KnowledgeAdmin
from ai_agent_runtime.admin.ingest_knowledge import main, smoke
from ai_agent_runtime.integrations.openai_provider import EmbeddingResult
from ai_agent_runtime.whatsapp.zapi_server import ZApiRuntimeRetrieval
from local_postgres import database

A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
NAMES = ['01-clinica-exemplo-institucional.md', '02-procedimentos-e-valores.md', '03-profissionais.md',
         '04-agendamento-e-fluxo-comercial.md', '05-pagamentos-e-condicoes-comerciais.md',
         '06-produtos.md', '07-regras-de-seguranca-e-handoff.md']
TEXTS = ['# Clínica sintética\n\n## Horários\nAtendimento das 8h às 18h.\n',
         '# Procedimentos\n\n## Avaliação\nAvaliação gratuita, exceto com Dra. Exemplo por R$ 200.\n\n'
         '| Procedimento | Valor |\n|---|---|\n| Consulta | R$ 200 |\n| Limpeza | R$ 100 |\n',
         '# Profissionais\n\n## Dra. Exemplo\nEspecialidade: dermatologia.\n',
         '# Agendamento\n\nSolicitar dia e período. Não confirmar sem disponibilidade.\n',
         '# Pagamentos\n\nParcelamento em 6x.\n\nExceto valores abaixo de R$ 300.\n',
         '# Produtos\n\nProduto sintético A. Somente uso conforme orientação.\n',
         '# Segurança\n\n## Handoff\nNunca diagnosticar. Encaminhar urgências ao atendimento humano.\n']


class Embeddings:
    config = SimpleNamespace(openai_embedding_model='text-embedding-3-small')
    def __init__(self, fail_at=None):
        self.calls = 0
        self.fail_at = fail_at
    def create_embedding(self, *, text):
        self.calls += 1
        if self.calls == self.fail_at:
            raise RuntimeError('secret-from-vault sk-secret sentinel-patient')
        return EmbeddingResult([1.0] + [0.0] * 1535, self.config.openai_embedding_model, 'v1', '2026-01-01T00:00:00Z')


class SqlRuntime(ZApiRuntimeRetrieval):
    """Actual runtime eligibility/search code with a local SQL read transport."""
    def __init__(self, db):
        self.db = db
    def _get_json(self, table, params, *, endpoint):
        org = params['organization_id'][3:]
        if table == 'document_versions':
            rows = self.db.execute('SELECT * FROM document_versions WHERE organization_id=%s', (org,)).fetchall()
        elif table == 'chunks':
            versions = params['document_version_id'][4:-1].split(',')
            term = params.get('content', 'ilike.**')[7:-1]
            rows = self.db.execute('''SELECT * FROM chunks WHERE organization_id=%s
                AND document_version_id=ANY(%s::uuid[]) AND content ILIKE %s LIMIT %s''',
                (org, versions, '%' + term + '%', int(params['limit']))).fetchall()
        else:
            raise AssertionError(table)
        return json.loads(json.dumps(rows, default=str))


@contextlib.contextmanager
def fixture():
    with database() as (db, dsn), tempfile.TemporaryDirectory() as directory:
        db.execute("INSERT INTO organizations(id,name,status) VALUES (%s,'Synthetic A','active'),(%s,'Synthetic B','active')", (A, B))
        path = Path(directory)
        for name, text in zip(NAMES, TEXTS):
            (path / name).write_text(text, encoding='utf-8')
        provider = Embeddings()
        admin = KnowledgeAdmin(db, A, provider)
        yield db, dsn, path, provider, admin


def counts(db):
    return [db.execute(f'SELECT count(*) AS n FROM {table}').fetchone()['n']
            for table in ('documents', 'document_versions', 'chunks', 'retrieval_index_entries')]


def rejected(fn, code=None):
    try:
        fn()
    except KnowledgeError as exc:
        if code:
            assert str(exc) == code, str(exc)
    else:
        raise AssertionError('operation should fail closed')


def publish(admin, sources):
    m = admin.ingest(sources)
    m = admin.validate(m, sources, 'reviewer')
    return admin.publish(m, 'publisher')


def seven_sources():
    with fixture() as (db, _, path, provider, admin):
        sources = read_sources(path)
        m = admin.ingest(sources)
        assert counts(db) == [7, 7, 8, 8]
        assert provider.calls == 8
        assert all(e['status'] == 'REVIEW_REQUIRED' for e in m['documents'])
        assert db.execute("SELECT count(*) n FROM document_versions WHERE processing_valid").fetchone()['n'] == 0
        assert SqlRuntime(db).search(A, 'avaliação') == []
        for table in ('documents', 'document_versions', 'chunks', 'retrieval_index_entries'):
            assert db.execute(f'SELECT count(*) n FROM {table} WHERE organization_id<>%s', (A,)).fetchone()['n'] == 0


def idempotency():
    with fixture() as (db, dsn, path, provider, admin):
        sources = read_sources(path)
        first = admin.ingest(sources)
        before = counts(db)
        again = admin.ingest(sources)
        assert counts(db) == before and provider.calls == 8
        assert again['summary'] == {'new_document': 0, 'new_version': 0, 'unchanged': 7}
        assert [e['version_id'] for e in first['documents']] == [e['version_id'] for e in again['documents']]
        # Concurrent first import for a second tenant, actual connections and row locks.
        providers = [Embeddings(), Embeddings()]
        def run(i):
            with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as conn:
                return KnowledgeAdmin(conn, B, providers[i]).ingest(sources)
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(run, [0, 1]))
        assert sum(p.calls for p in providers) == 8
        assert counts(db) == [14, 14, 16, 16]
        assert sorted(m['summary']['unchanged'] for m in results) == [0, 7]


def one_update():
    with fixture() as (db, _, path, provider, admin):
        old = publish(admin, read_sources(path))
        source = path / NAMES[1]
        source.write_text(TEXTS[1].replace('200', '250'))
        m = admin.ingest(read_sources(path))
        assert m['summary'] == {'new_document': 0, 'new_version': 1, 'unchanged': 6}
        assert counts(db) == [7, 8, 10, 10] and provider.calls == 10
        hits = SqlRuntime(db).search(A, 'avaliação')
        assert hits and all(x['document_version_id'] == old['documents'][1]['version_id'] for x in hits)
        assert 'R$ 200' in hits[0]['content']
        admin.validate(m, read_sources(path), 'reviewer')
        admin.publish(m, 'publisher')
        hits = SqlRuntime(db).search(A, 'avaliação')
        assert hits and all(x['document_version_id'] == m['documents'][1]['version_id'] for x in hits)
        assert 'R$ 250' in hits[0]['content']
        assert db.execute('SELECT status FROM document_versions WHERE id=%s', (old['documents'][1]['version_id'],)).fetchone()['status'] == 'SUPERSEDED'
        replacement = db.execute('SELECT supersedes_version_id FROM document_versions WHERE id=%s', (m['documents'][1]['version_id'],)).fetchone()
        assert str(replacement['supersedes_version_id']) == old['documents'][1]['version_id']
        rejected(lambda: admin.publish(old, 'publisher'), 'STALE_VERSION')


def isolation():
    with fixture() as (db, _, path, provider, admin):
        sources = read_sources(path)
        m = publish(admin, sources)
        other = KnowledgeAdmin(db, B, provider)
        assert SqlRuntime(db).search(B, 'avaliação') == []
        for method in (lambda: other.validate(m, sources, 'reviewer'), lambda: other.publish(m, 'publisher'), lambda: other.deactivate(m, 'publisher')):
            rejected(method)
        forged = copy.deepcopy(m)
        forged['organization_id'] = B
        rejected(lambda: other.publish(forged, 'publisher'), 'VERSION_NOT_FOUND_IN_TENANT')
        mb = other.ingest(sources)
        assert set(e['document_id'] for e in mb['documents']).isdisjoint(e['document_id'] for e in m['documents'])
        other.validate(mb, sources, 'reviewer')
        other.publish(mb, 'publisher')
        assert all(x['organization_id'] == B for x in SqlRuntime(db).search(B, 'avaliação'))


def organization():
    with fixture() as (db, _, path, provider, admin):
        sources = read_sources(path)
        for org in ('', None, 'not-a-uuid'):
            rejected(lambda: KnowledgeAdmin(db, org, provider))
        missing = KnowledgeAdmin(db, str(uuid4()), provider)
        rejected(lambda: missing.ingest(sources), 'ORGANIZATION_NOT_ACTIVE_OR_MISSING')
        db.execute("UPDATE organizations SET status='inactive' WHERE id=%s", (A,))
        rejected(lambda: admin.ingest(sources))
        rejected(lambda: admin.ingest(sources, dry_run=True))
        assert counts(db) == [0, 0, 0, 0] and provider.calls == 0
        with contextlib.redirect_stderr(io.StringIO()) as err:
            assert main(['--dry-run', '--directory', str(path)]) == 2
        assert 'INVALID_ARGUMENTS' in err.getvalue()


def lifecycle():
    with fixture() as (db, _, path, provider, admin):
        sources = read_sources(path)
        m = admin.ingest(sources)
        rejected(lambda: admin.publish(m, 'publisher'), 'APPROVAL_REQUIRED')
        assert SqlRuntime(db).search(A, 'avaliação') == []
        m = admin.validate(m, sources, 'reviewer')
        assert SqlRuntime(db).search(A, 'avaliação') == []
        m = admin.publish(m, 'publisher')
        assert SqlRuntime(db).search(A, 'avaliação')
        before = db.execute('SELECT id,published_at FROM document_versions ORDER BY id').fetchall()
        admin.publish(m, 'publisher')
        assert before == db.execute('SELECT id,published_at FROM document_versions ORDER BY id').fetchall()
        db.execute("UPDATE document_versions SET effective_until='2020-01-01',effective_from='2019-01-01' WHERE id=%s", (m['documents'][1]['version_id'],))
        assert SqlRuntime(db).search(A, 'avaliação') == []


def atomicity():
    with fixture() as (db, _, path, _, admin):
        sources = read_sources(path)
        admin.embeddings = Embeddings(fail_at=3)
        try:
            admin.ingest(sources)
            assert False
        except RuntimeError:
            pass
        assert counts(db) == [0, 0, 0, 0]
        admin.embeddings = Embeddings()
        original = publish(admin, sources)
        for name, text in zip(NAMES, TEXTS):
            (path / name).write_text(text + '\nRevisão de teste.\n')
        sources = read_sources(path)
        m = admin.validate(admin.ingest(sources), sources, 'reviewer')
        # Fail at the second version update AFTER the first new publication and
        # first supersession. PostgreSQL must restore the entire old batch.
        target = m['documents'][1]['version_id']
        db.execute('''CREATE FUNCTION fail_publication() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.status='PUBLISHED' AND NEW.id::text = TG_ARGV[0] THEN
            RAISE EXCEPTION 'injected publication failure'; END IF; RETURN NEW; END $$''')
        from psycopg import sql
        db.execute(sql.SQL('CREATE TRIGGER fail_publication BEFORE UPDATE ON document_versions FOR EACH ROW EXECUTE FUNCTION fail_publication({})').format(sql.Literal(target)))
        try:
            admin.publish(m, 'publisher')
            assert False
        except psycopg.Error:
            pass
        rows = db.execute("SELECT id FROM document_versions WHERE status='PUBLISHED'").fetchall()
        assert {str(r['id']) for r in rows} == {e['version_id'] for e in original['documents']}
        assert db.execute("SELECT count(*) n FROM document_versions WHERE status='SUPERSEDED'").fetchone()['n'] == 0


def chunking():
    with tempfile.TemporaryDirectory() as directory:
        p = Path(directory) / 'acentuação.md'
        text = '# Clínica\nRegra: nunca diagnosticar.\n\n## Dra. Exemplo\n\n### Avaliação\nGrátis.\n\nExceto consulta por R$ 200.\n'
        p.write_text(text)
        a, b = read_sources(p)[0], read_sources(p)[0]
        assert a.sha256 == b.sha256 and a.chunks == b.chunks
        assert a.chunks[0]['section_path'] == ['Clínica', 'Dra. Exemplo', 'Avaliação']
        assert all(term in a.chunks[0]['content'] for term in ['nunca', 'Grátis', 'Exceto', 'R$ 200'])
        chunks = chunk_markdown(TEXTS[1])
        assert len(chunks) == 2
        assert all('exceto' in c['content'] and 'Valor:' in c['content'] for c in chunks)
        assert 'Procedimento: Consulta' in chunks[0]['content']
        assert chunks == chunk_markdown(TEXTS[1])


def safe_reports():
    with fixture() as (db, dsn, path, _, admin):
        report = admin.ingest(read_sources(path))
        raw = json.dumps(report)
        assert all(text.strip() not in raw for text in TEXTS)
        assert 'embedding' not in raw and 'R$' not in raw
        with patch.dict(os.environ, {'KNOWLEDGE_DATABASE_URL': dsn, 'OPENAI_API_KEY': 'sk-secret', 'VAULT_TOKEN': 'vault-secret'}):
            with patch('ai_agent_runtime.integrations.openai_provider.OpenAIResponsesProvider.create_embedding', side_effect=RuntimeError('sk-secret vault-secret sentinel-patient')):
                (path / NAMES[0]).write_text(TEXTS[0] + '\nMudou.\n')
                with contextlib.redirect_stderr(io.StringIO()) as err, contextlib.redirect_stdout(io.StringIO()) as out:
                    assert main(['--organization-id', A, '--directory', str(path), '--ingest']) == 1
                assert json.loads(err.getvalue()) == {'error': 'KNOWLEDGE_OPERATION_FAILED'}
                assert out.getvalue() == ''
        with contextlib.redirect_stderr(io.StringIO()) as err:
            assert main(['--secret', 'sk-secret']) == 2
        assert 'sk-secret' not in err.getvalue()


def invalid_sources():
    with tempfile.TemporaryDirectory() as directory:
        p = Path(directory) / 'source.md'
        for content in [b'', b'   ', b'\xff', b'\x00', b'# Title\n', b'---\norganization_id: B\n---\nhi', b'organization_id: B', b'## Big\n' + b'x' * 6001]:
            p.write_bytes(content)
            rejected(lambda: read_sources(p))
        p.write_text('## Content\nvalid')
        q = Path(directory) / 'link.md'
        q.symlink_to(p)
        rejected(lambda: read_sources(q))
        rejected(lambda: read_sources(Path(directory)))


def dry_run():
    with fixture() as (db, dsn, path, provider, admin):
        sources = read_sources(path)
        m = admin.ingest(sources, dry_run=True)
        assert m['summary']['new_document'] == 7
        assert counts(db) == [0, 0, 0, 0] and provider.calls == 0
        with patch.dict(os.environ, {'KNOWLEDGE_DATABASE_URL': dsn}), contextlib.redirect_stdout(io.StringIO()) as out:
            assert main(['--organization-id', A, '--directory', str(path), '--dry-run']) == 0
        assert json.loads(out.getvalue())['summary']['new_document'] == 7
        assert counts(db) == [0, 0, 0, 0]
        admin.ingest(sources)
        (path / NAMES[1]).write_text(TEXTS[1].replace('200', '250'))
        before = counts(db)
        m = admin.ingest(read_sources(path), dry_run=True)
        assert m['summary'] == {'new_document': 0, 'new_version': 1, 'unchanged': 6}
        assert counts(db) == before and provider.calls == 8
        assert sum(e['chunk_count'] for e in m['documents']) == 8
        # Server-enforced READ ONLY transaction, not just a mocked no-write flag.
        try:
            with admin.transaction(readonly=True):
                db.execute("UPDATE organizations SET name='unexpected' WHERE id=%s", (A,))
            assert False
        except psycopg.errors.ReadOnlySqlTransaction:
            pass


def validation():
    with fixture() as (db, _, path, provider, admin):
        sources = read_sources(path)
        m = admin.ingest(sources)
        rejected(lambda: admin.validate(m, sources, ''), 'ACTOR_REQUIRED')
        (path / NAMES[1]).write_text(TEXTS[1].replace('200', '300'))
        rejected(lambda: admin.validate(m, read_sources(path), 'reviewer'), 'VALIDATION_SOURCE_CHANGED')
        assert db.execute("SELECT count(*) n FROM document_versions WHERE status='APPROVED'").fetchone()['n'] == 0
        admin.validate(m, sources, 'reviewer')
        cid = db.execute('SELECT id FROM chunks ORDER BY id LIMIT 1').fetchone()['id']
        db.execute("UPDATE chunks SET content=content || ' adulterado' WHERE id=%s", (cid,))
        rejected(lambda: admin.publish(m, 'publisher'), 'CHUNK_CONTENT_MISMATCH')
        assert db.execute("SELECT count(*) n FROM document_versions WHERE status='PUBLISHED'").fetchone()['n'] == 0
        db.execute("UPDATE chunks SET content=left(content,length(content)-11) WHERE id=%s", (cid,))
        # Embedding corruption with valid dimensions is also detected after approval.
        db.execute("UPDATE retrieval_index_entries SET embedding=%s::vector WHERE chunk_id=%s", (json.dumps([0.0, 1.0] + [0.0] * 1534), cid))
        rejected(lambda: admin.publish(m, 'publisher'), 'INDEX_CONTENT_MISMATCH')


def smoke_rollback():
    with fixture() as (db, _, path, provider, admin):
        sources = read_sources(path)
        m = publish(admin, sources)
        result = smoke(admin, m, SqlRuntime(db), ['avaliação', 'pagamentos', 'handoff'])
        assert result['passed'] and result['versions_checked'] == 7
        assert 'R$' not in json.dumps(result)
        rejected(lambda: smoke(admin, m, SqlRuntime(db), ['termo-inexistente']), 'SMOKE_NO_EVIDENCE')
        admin.deactivate(m, 'publisher')
        assert db.execute("SELECT payload FROM operational_audit_events WHERE decision='KNOWLEDGE_DEACTIVATED'").fetchone()['payload'] == {'actor': 'publisher'}
        assert SqlRuntime(db).search(A, 'avaliação') == []
        assert counts(db) == [7, 7, 8, 8]
        restored = admin.ingest(sources)
        assert restored['summary']['new_version'] == 7
        admin.publish(admin.validate(restored, sources, 'reviewer'), 'publisher')
        assert SqlRuntime(db).search(A, 'avaliação')


if __name__ == '__main__':
    case = sys.argv[1]
    globals()[case]()
    print(json.dumps({'passed': case}))
