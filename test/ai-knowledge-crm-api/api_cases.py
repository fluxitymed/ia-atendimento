from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch
from urllib import error, request
from urllib.parse import urlencode
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, 'test/ai-knowledge-admin')
from cases import fixture, counts, Embeddings, SqlRuntime, A, B
from ai_agent_runtime.admin.knowledge_api import handle_knowledge_request as handle, BASE
from ai_agent_runtime.admin.markdown import source_from_text, read_sources
from ai_agent_runtime.admin.ingest_knowledge import main as cli_main
from ai_agent_runtime.crm_dispatch import CrmDispatchRequestHandler, handle_crm_dispatch

TOKEN = 'knowledge-service-token-' + 'x' * 32
DISPATCH_TOKEN = 'dispatch-service-token-' + 'y' * 32
ACTOR = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
CONTENT = '# Clínica teste\n\n## Avaliação\nAvaliação gratuita; exceto Dra. Teste por R$ 200.\n'
NAME = 'procedimentos-valores'
FILENAME = '02-procedimentos-e-valores.md'


def payload(**other):
    return {'organizationId': A, 'correlationId': str(uuid4()), **other}


def call(dsn, action, data=None, *, method='POST', auth=None, provider=None, retrieval=None, logs=None):
    def connector():
        return psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
    target = BASE + ('/documents' if action == 'list' else '/' + action)
    if method == 'GET':
        target += '?' + urlencode(data)
    return handle(method, target, json.dumps(data).encode() if method == 'POST' and data is not None else b'',
                  auth if auth is not None else 'Bearer ' + TOKEN, token=TOKEN,
                  content_type='application/json' if method == 'POST' else None,
                  connection_factory=connector, provider_factory=lambda: provider or Embeddings(),
                  retrieval_factory=lambda: retrieval, logger=lambda e, d: logs.append((e,d)) if logs is not None else None)


def doc_data(**other):
    return payload(logicalName=NAME, filename=FILENAME, content=CONTENT, **other)


def imported(dsn, provider=None):
    status, result = call(dsn, 'ingest', doc_data(actor=ACTOR), provider=provider)
    assert status == 200, result
    assert result['documents'][0]['status'] == 'REVIEW_REQUIRED'
    return result['documents'][0]


def authentication():
    with fixture() as (db, dsn, path, provider, admin):
        for auth in ('', 'Bearer bad', 'Bearer ' + DISPATCH_TOKEN):
            status, result = call(dsn, 'ingest', doc_data(), auth=auth, provider=provider)
            assert (status, result) == (401, {'error':'UNAUTHORIZED'})
        assert counts(db) == [0,0,0,0] and provider.calls == 0
        # Dispatch still accepts its own token but not the knowledge token.
        status, body = handle_crm_dispatch(b'{}', 'Bearer ' + TOKEN, token=DISPATCH_TOKEN)
        assert status == 401


def organization():
    with fixture() as (db, dsn, path, provider, admin):
        for org in (None, 'invalid', str(uuid4())):
            data = doc_data()
            data['organizationId'] = org
            status, result = call(dsn, 'ingest', data, provider=provider)
            assert status in (400,404)
        db.execute("UPDATE organizations SET status='inactive' WHERE id=%s", (A,))
        status, result = call(dsn, 'dry-run', doc_data(), provider=provider)
        assert status == 404 and counts(db) == [0,0,0,0] and provider.calls == 0


def dry_run():
    with fixture() as (db, dsn, path, provider, admin):
        status, result = call(dsn, 'dry-run', doc_data(), provider=provider)
        assert status == 200 and result['organizationId'] == A
        entry = result['documents'][0]
        assert entry['filename'] == FILENAME and entry['logicalName'] == NAME
        assert entry['changed'] and entry['proposedVersion'] == 1 and entry['estimatedChunks'] == 1
        assert len(entry['contentHash']) == 64 and CONTENT not in json.dumps(result)
        assert counts(db) == [0,0,0,0] and provider.calls == 0
        assert db.execute('SELECT count(*) n FROM operational_audit_events').fetchone()['n'] == 0


def ingest():
    with fixture() as (db, dsn, path, provider, admin):
        entry = imported(dsn, provider)
        assert entry['versionNumber'] == 1 and entry['chunkCount'] == 1
        assert counts(db) == [1,1,1,1] and provider.calls == 1
        assert db.execute("SELECT status,processing_valid FROM document_versions").fetchone() == {'status':'REVIEW_REQUIRED','processing_valid':False}
        assert db.execute("SELECT organization_id FROM chunks").fetchone()['organization_id'] == db.execute('SELECT id FROM organizations WHERE id=%s',(A,)).fetchone()['id']


def idempotency():
    with fixture() as (db, dsn, path, provider, admin):
        first = imported(dsn, provider)
        second = imported(dsn, provider)
        assert first['versionId'] == second['versionId'] and counts(db) == [1,1,1,1]
        assert provider.calls == 1


def validation():
    with fixture() as (db, dsn, path, provider, admin):
        entry = imported(dsn)
        status, result = call(dsn, 'validate', payload(versionId=entry['versionId'],actor=ACTOR))
        assert status == 200 and result['status'] == 'APPROVED'
        assert db.execute("SELECT count(*) n FROM document_versions WHERE status='PUBLISHED'").fetchone()['n'] == 0
        assert SqlRuntime(db).search(A,'avaliação') == []


def publication():
    with fixture() as (db, dsn, path, provider, admin):
        old = imported(dsn)
        call(dsn, 'validate', payload(versionId=old['versionId'],actor=ACTOR))
        assert call(dsn,'publish',payload(versionId=old['versionId'],actor=ACTOR))[0] == 200
        newdata=doc_data(); newdata['content']=CONTENT+'\nMudou.\n'
        status, r=call(dsn,'ingest',newdata)
        assert status == 200
        new=r['documents'][0]
        assert db.execute("SELECT status FROM document_versions WHERE id=%s",(old['versionId'],)).fetchone()['status']=='PUBLISHED'
        assert call(dsn,'validate',payload(versionId=new['versionId'],actor=ACTOR))[0] == 200
        assert call(dsn,'publish',payload(versionId=new['versionId'],actor=ACTOR))[0] == 200
        assert db.execute("SELECT status FROM document_versions WHERE id=%s",(old['versionId'],)).fetchone()['status']=='SUPERSEDED'
        row=db.execute("SELECT status,supersedes_version_id FROM document_versions WHERE id=%s",(new['versionId'],)).fetchone()
        assert row['status']=='PUBLISHED' and str(row['supersedes_version_id'])==old['versionId']
        assert len(SqlRuntime(db).search(A,'avaliação')) == 1


def read_isolation():
    with fixture() as (db, dsn, path, provider, admin):
        entry=imported(dsn)
        doc=entry['documentId']
        b=payload(); b['organizationId']=B
        assert call(dsn,'list',b,method='GET')[1]['documents']==[]
        for action in ('documents/'+doc,'documents/'+doc+'/versions',
                       'documents/'+doc+'/versions/'+entry['versionId']+'/review'):
            status, body=call(dsn,action,b,method='GET')
            assert status==404 and 'DOCUMENT' in body['error'] or status==404 and 'VERSION' in body['error']


def write_isolation():
    with fixture() as (db, dsn, path, provider, admin):
        entry=imported(dsn)
        for action in ('validate','publish'):
            d=payload(versionId=entry['versionId'],actor=ACTOR);d['organizationId']=B
            status,body=call(dsn,action,d)
            assert status==404 and body['error']=='VERSION_NOT_FOUND_IN_TENANT'
        assert counts(db)==[1,1,1,1]


def concurrency():
    with fixture() as (db, dsn, path, provider, admin):
        old=imported(dsn)
        call(dsn,'validate',payload(versionId=old['versionId'],actor=ACTOR))
        data=payload(versionId=old['versionId'],actor=ACTOR)
        with ThreadPoolExecutor(2) as pool:
            out=list(pool.map(lambda _:call(dsn,'publish',data),range(2)))
        assert [status for status,_ in out]==[200,200]
        assert db.execute("SELECT count(*) n FROM document_versions WHERE status='PUBLISHED'").fetchone()['n']==1
        fresh=doc_data();fresh['content']=CONTENT+'\nAtualizado.\n'
        new=call(dsn,'ingest',fresh)[1]['documents'][0]
        assert call(dsn,'publish',payload(versionId=old['versionId'],actor=ACTOR))[0]==409
        assert call(dsn,'publish',payload(versionId=new['versionId'],actor=ACTOR))[0]==409


def invalid_source():
    with fixture() as (db, dsn, path, provider, admin):
        for content in ('',' ', '# Heading', 'organization_id: '+B, '# H\n'+ 'x'*6001):
            data=doc_data();data['content']=content
            assert call(dsn,'ingest',data,provider=provider)[0] in (400,413)
        bad=doc_data();bad['filename']='../secret.md'
        assert call(dsn,'ingest',bad,provider=provider)[0]==400
        big=doc_data();big['content']='x'*512001
        assert call(dsn,'ingest',big,provider=provider)[0]==413
        assert counts(db)==[0,0,0,0] and provider.calls==0


def safe_output():
    with fixture() as (db, dsn, path, provider, admin):
        logs=[]
        status,result=call(dsn,'dry-run',doc_data(),logs=logs)
        assert status==200
        raw=json.dumps([result,logs])
        assert CONTENT not in raw and 'R$ 200' not in raw and 'embedding' not in raw
        assert TOKEN not in raw
        def bad(): raise RuntimeError('sk-secret vault-secret patient-data')
        status,result=call(dsn,'ingest',doc_data(),provider=type('P',(),{'config':provider.config,'create_embedding':lambda self,*,text:bad()})(),logs=logs)
        assert status==503 and 'sk-secret' not in json.dumps([result,logs])
        assert counts(db)==[0,0,0,0]


def listing():
    with fixture() as (db, dsn, path, provider, admin):
        old=imported(dsn)
        call(dsn,'validate',payload(versionId=old['versionId'],actor=ACTOR))
        call(dsn,'publish',payload(versionId=old['versionId'],actor=ACTOR))
        newer=doc_data();newer['content']=CONTENT+'\nRevisado.\n'
        new=call(dsn,'ingest',newer)[1]['documents'][0]
        status,result=call(dsn,'list',{'organizationId':A,'correlationId':str(uuid4())},method='GET')
        assert status==200 and len(result['documents'])==1
        row=result['documents'][0]
        assert row['publishedVersion']==1 and row['pendingVersion']==2 and row['pendingStatus']=='REVIEW_REQUIRED'
        assert row['updatedAt'] and row['lastPublishedAt']
        doc=new['documentId']
        status,detail=call(dsn,'documents/'+doc,{'organizationId':A,'correlationId':str(uuid4())},method='GET')
        status2,versions=call(dsn,'documents/'+doc+'/versions',{'organizationId':A,'correlationId':str(uuid4())},method='GET')
        assert status==status2==200 and detail['document']['documentId']==doc
        assert len(versions['versions'])==2 and versions['versions'][0]['contentHash']==new['contentHash']
        assert versions['versions'][0]['filename']==FILENAME
        assert CONTENT not in json.dumps([result,detail,versions])


def review():
    with fixture() as (db, dsn, path, provider, admin):
        entry=imported(dsn)
        endpoint='documents/'+entry['documentId']+'/versions/'+entry['versionId']+'/review'
        status,result=call(dsn,endpoint,{'organizationId':A,'correlationId':str(uuid4())},method='GET')
        assert status==200 and result['chunks'][0]['content'].endswith('R$ 200.')
        assert 'embedding' not in json.dumps(result)
        assert call(dsn,endpoint,{'organizationId':B,'correlationId':str(uuid4())},method='GET')[0]==404


def smoke_test():
    with fixture() as (db, dsn, path, provider, admin):
        entry=imported(dsn)
        call(dsn,'validate',payload(versionId=entry['versionId'],actor=ACTOR))
        call(dsn,'publish',payload(versionId=entry['versionId'],actor=ACTOR))
        status,result=call(dsn,'smoke',payload(versionId=entry['versionId'],queries=['avaliação']),retrieval=SqlRuntime(db))
        assert status==200 and result['passed'] and result['queriesChecked']==1
        assert 'R$' not in json.dumps(result)


def audit():
    with fixture() as (db, dsn, path, provider, admin):
        logs=[];data=doc_data(actor=ACTOR)
        cor=data['correlationId']
        status,result=call(dsn,'ingest',data,logs=logs)
        assert status==200
        version=result['documents'][0]['versionId']
        call(dsn,'validate',payload(versionId=version,actor=ACTOR),logs=logs)
        call(dsn,'publish',payload(versionId=version,actor=ACTOR),logs=logs)
        rows=db.execute("SELECT decision,payload FROM operational_audit_events WHERE decision LIKE 'knowledge_%' ORDER BY created_at").fetchall()
        assert {r['decision'] for r in rows}=={'knowledge_ingested','knowledge_validated','knowledge_published'}
        assert rows[0]['payload']['correlationId']==cor and rows[0]['payload']['actor']==ACTOR
        assert any(x[1]['outcome']=='success' for x in logs)
        assert CONTENT not in json.dumps(rows,default=str)


def cli_compatibility():
    with fixture() as (db, dsn, path, provider, admin):
        one=path/(NAME+'.md');one.write_text(CONTENT)
        with patch.dict(os.environ,{'KNOWLEDGE_DATABASE_URL':dsn}):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                assert cli_main(['--organization-id',A,'--file',str(one),'--dry-run'])==0
            assert json.loads(out.getvalue())['summary']['new_document']==1
        cli_report=admin.ingest(read_sources(one))
        before=counts(db)
        api=imported(dsn,provider)
        assert api['documentId'] == cli_report['documents'][0]['document_id']
        assert api['versionId'] == cli_report['documents'][0]['version_id']
        assert counts(db)==before and provider.calls==1
        assert call(dsn,'validate',payload(versionId=api['versionId'],actor=ACTOR))[0]==200


def http_boundary():
    with fixture() as (db, dsn, path, provider, admin):
        # Real HTTP listener, same class and port architecture as CRM dispatch.
        with patch.dict(os.environ,{'KNOWLEDGE_DATABASE_URL':dsn,'CRM_KNOWLEDGE_SERVICE_TOKEN':TOKEN}),\
             patch('ai_agent_runtime.admin.knowledge_api._default_provider',return_value=provider):
            server=ThreadingHTTPServer(('127.0.0.1',0),CrmDispatchRequestHandler)
            thread=Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                url=f'http://127.0.0.1:{server.server_port}/internal/knowledge/ingest'
                data=json.dumps(doc_data(actor=ACTOR)).encode()
                req=request.Request(url,data=data,headers={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'},method='POST')
                with request.urlopen(req,timeout=10) as resp:
                    body=json.loads(resp.read())
                    assert resp.status==200 and resp.headers['Cache-Control']=='no-store'
                    assert body['documents'][0]['status']=='REVIEW_REQUIRED'
                for headers in ({},{'Authorization':'Bearer '+DISPATCH_TOKEN}):
                    req=request.Request(url,data=data,headers={**headers,'Content-Type':'application/json'},method='POST')
                    try:request.urlopen(req,timeout=10);assert False
                    except error.HTTPError as exc:assert exc.code==401
                assert counts(db)==[1,1,1,1]
            finally:
                server.shutdown();server.server_close();thread.join(timeout=5)


if __name__ == '__main__':
    name=sys.argv[1]
    globals()[name]()
    print(json.dumps({'passed':name}))
