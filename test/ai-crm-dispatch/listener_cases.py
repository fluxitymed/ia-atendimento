"""HTTP proofs for CRM dispatch on the published Z-API listener."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from threading import Thread
import time
from unittest.mock import patch
from urllib import error, request
from http.server import ThreadingHTTPServer

from ai_agent_runtime.whatsapp.zapi_server import ZApiWebhookRequestHandler, WEBHOOK_PATH
from ai_agent_runtime.whatsapp.zapi_webhook import ZApiWebhookResponse

TOKEN = 'local-dispatch-token-' + 'x' * 32
OTHER_TOKEN = 'local-knowledge-token-' + 'y' * 32
PATH = '/internal/crm/whatsapp-dispatch'
A = '11111111-1111-4111-8111-111111111111'
C = '22222222-2222-4222-8222-222222222222'
P = '33333333-3333-4333-8333-333333333333'
M = '44444444-4444-4444-8444-444444444444'
R = '55555555-5555-4555-8555-555555555555'
EVENT = {'version': '1', 'correlationId': R, 'organizationId': A,
         'conversationId': C, 'providerConnectionId': P, 'contactId': None,
         'inboundMessageId': M, 'mode': 'AI', 'modeVersion': 1,
         'message': {'type': 'text', 'text': 'Ola', 'timestamp': '2026-10-07T12:00:00Z'}}


def http(base, path, *, method='GET', body=None, token=None):
    headers = {} if token is None else {'Authorization': 'Bearer ' + token}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    req = request.Request(base + path, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=5) as response:
            return response.status, response.headers, response.read()
    except error.HTTPError as response:
        return response.code, response.headers, response.read()


def production_entrypoint():
    with tempfile.TemporaryDirectory() as directory, socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
        probe.close()
        env = os.environ.copy()
        env.update(PYTHONPATH='src', HOST='127.0.0.1', PORT=str(port),
                   ZAPI_STORE_PATH=str(Path(directory) / 'store.json'),
                   AI_INBOUND_ENABLED='false', CRM_DISPATCH_SERVICE_TOKEN=TOKEN)
        process = subprocess.Popen(
            [sys.executable, '-m', 'ai_agent_runtime.whatsapp.zapi_server'],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        base = f'http://127.0.0.1:{port}'
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise AssertionError('Production entrypoint exited')
                try:
                    assert http(base, '/health')[0] == 200
                    break
                except (error.URLError, TimeoutError):
                    time.sleep(0.05)
            else:
                raise AssertionError('Production entrypoint did not start')
            for token, expected in ((None, 401), ('wrong', 401), (TOKEN, 400)):
                status, headers, raw = http(base, PATH, method='POST', body=b'{}', token=token)
                assert status == expected and headers['Cache-Control'] == 'no-store'
                assert json.loads(raw) == {'error': 'INVALID_REQUEST' if expected == 400 else 'UNAUTHORIZED'}
                assert TOKEN.encode() not in raw
            assert http(base, PATH + '/', method='POST', body=b'{}', token=TOKEN)[0] == 404
            assert http(base, '/internal/knowledge/documents')[0] == 401
            assert http(base, '/missing', method='POST', body=b'{}')[0] == 404
        finally:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)


def canonical_handler_and_webhook():
    class Processor:
        def __init__(self):
            self.events = []

        def process(self, event):
            self.events.append(event)
            action = ('HANDOFF' if event['message']['text'] == 'handoff' else
                      'NO_ACTION' if event['message']['text'] == 'silent' else 'SEND_MESSAGE')
            result = {key: event[key] for key in ('version', 'correlationId',
                'organizationId', 'conversationId', 'inboundMessageId', 'modeVersion')}
            result.update(action=action, metadata={})
            if action == 'SEND_MESSAGE':
                result['message'] = 'Resposta sintetica'
            return result

    processor = Processor()
    handler = type('TestZApiHandler', (ZApiWebhookRequestHandler,),
                   {'crm_dispatch_processor': processor, 'adapter': object(), 'config': object()})
    with patch.dict(os.environ, {'CRM_DISPATCH_SERVICE_TOKEN': TOKEN,
                                 'CRM_KNOWLEDGE_SERVICE_TOKEN': OTHER_TOKEN}), \
         patch('ai_agent_runtime.whatsapp.zapi_server.handle_zapi_webhook_post',
               return_value=(ZApiWebhookResponse(status_code=200, body='ok'), [])):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            for message, action in (('Ola', 'SEND_MESSAGE'), ('handoff', 'HANDOFF'),
                                    ('silent', 'NO_ACTION')):
                event = dict(EVENT, message=dict(EVENT['message'], text=message))
                status, headers, raw = http(base, PATH, method='POST',
                                            body=json.dumps(event).encode(), token=TOKEN)
                result = json.loads(raw)
                assert status == 200 and result['action'] == action
                assert result['organizationId'] == A and result['correlationId'] == R
                assert headers['Cache-Control'] == 'no-store' and TOKEN.encode() not in raw
            assert len(processor.events) == 3
            assert http(base, WEBHOOK_PATH, method='POST', body=b'{}')[0] == 200
            assert http(base, '/internal/knowledge/documents')[0] == 401
            with patch.dict(os.environ, {'CRM_DISPATCH_SERVICE_TOKEN': ''}):
                status, _, raw = http(base, PATH, method='POST', body=b'{}', token=TOKEN)
                assert status == 401 and json.loads(raw) == {'error': 'UNAUTHORIZED'}
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    globals()[sys.argv[1]]()
    print(json.dumps({'passed': sys.argv[1]}))
