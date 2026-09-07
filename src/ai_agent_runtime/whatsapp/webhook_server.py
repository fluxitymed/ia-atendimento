from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from os import environ
from urllib import parse

from .adapter import OrganizationResolver, WhatsAppChannelAdapter
from .channel import InMemoryWhatsAppStore
from .media import FakeSpeechToTextProvider, MediaProcessor
from .meta import MetaWhatsAppCloudProvider, MetaWhatsAppConfig
from .meta_webhook import WEBHOOK_PATH, handle_meta_webhook_post, verify_webhook_get


def build_default_adapter(config: MetaWhatsAppConfig) -> WhatsAppChannelAdapter:
    provider = MetaWhatsAppCloudProvider(config=config)
    organization_id = environ.get("META_WHATSAPP_ORGANIZATION_ID", "sandbox-org-aurora")
    resolver = OrganizationResolver({config.phone_number_id or "missing-phone-number-id": organization_id})
    return WhatsAppChannelAdapter(
        provider=provider,
        store=InMemoryWhatsAppStore(),
        organization_resolver=resolver,
        media_processor=MediaProcessor(provider=provider, speech_to_text=FakeSpeechToTextProvider()),
    )


class MetaWebhookRequestHandler(BaseHTTPRequestHandler):
    config: MetaWhatsAppConfig
    adapter: WhatsAppChannelAdapter

    def do_GET(self):  # noqa: N802
        parsed = parse.urlparse(self.path)
        if parsed.path != WEBHOOK_PATH:
            self._respond(404, "Not found")
            return
        query = {key: values[0] for key, values in parse.parse_qs(parsed.query).items()}
        response = verify_webhook_get(query, self.config)
        self._respond(response.status_code, response.body, response.headers)

    def do_POST(self):  # noqa: N802
        parsed = parse.urlparse(self.path)
        if parsed.path != WEBHOOK_PATH:
            self._respond(404, "Not found")
            return
        length = int(self.headers.get("content-length", "0"))
        raw_body = self.rfile.read(length)
        response, records = handle_meta_webhook_post(
            raw_body=raw_body,
            headers={key: value for key, value in self.headers.items()},
            config=self.config,
            adapter=self.adapter,
        )
        self._respond(response.status_code, response.body, response.headers, {"processed": len(records)})

    def log_message(self, format, *args):  # noqa: A003
        return

    def _respond(self, status_code: int, body: str, headers: dict[str, str] | None = None, diagnostic: dict | None = None) -> None:
        payload = body
        response_headers = headers or {"Content-Type": "text/plain"}
        if diagnostic is not None:
            response_headers = {"Content-Type": "application/json"}
            payload = json.dumps({"status": body, **diagnostic})
        encoded = payload.encode("utf-8")
        self.send_response(status_code)
        for key, value in response_headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def run_server(host: str = "127.0.0.1", port: int = 8080) -> None:
    config = MetaWhatsAppConfig.from_env()
    handler = MetaWebhookRequestHandler
    handler.config = config
    handler.adapter = build_default_adapter(config)
    server = HTTPServer((host, port), handler)
    print(json.dumps({
        "status": "READY",
        "path": WEBHOOK_PATH,
        "url": f"http://{host}:{port}{WEBHOOK_PATH}",
        "provider": config.provider,
        "phoneNumberIdConfigured": bool(config.phone_number_id),
    }))
    server.serve_forever()


if __name__ == "__main__":
    run_server(port=int(environ.get("META_WHATSAPP_WEBHOOK_PORT", "8080")))
