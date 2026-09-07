from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from os import environ
from urllib import parse

from .adapter import OrganizationResolver, WhatsAppChannelAdapter
from .channel import InMemoryWhatsAppStore
from .evolution import EvolutionWhatsAppConfig
from .evolution_webhook import WEBHOOK_PATH, EvolutionWebhookResponse, handle_evolution_webhook_post
from .media import FakeSpeechToTextProvider, MediaProcessor
from .providers import build_whatsapp_provider


def build_default_adapter(config: EvolutionWhatsAppConfig) -> WhatsAppChannelAdapter:
    provider = build_whatsapp_provider("evolution", evolution_config=config)
    instance = config.instance_name or "missing-evolution-instance"
    resolver = OrganizationResolver({instance: config.organization_id})
    return WhatsAppChannelAdapter(
        provider=provider,
        store=InMemoryWhatsAppStore(),
        organization_resolver=resolver,
        media_processor=MediaProcessor(provider=provider, speech_to_text=FakeSpeechToTextProvider()),
    )


class EvolutionWebhookRequestHandler(BaseHTTPRequestHandler):
    adapter: WhatsAppChannelAdapter | None = None
    config: EvolutionWhatsAppConfig | None = None

    def do_POST(self) -> None:
        if parse.urlparse(self.path).path != WEBHOOK_PATH:
            self._write(EvolutionWebhookResponse(status_code=404, body="Not Found"))
            return
        length = int(self.headers.get("content-length", "0") or "0")
        raw_body = self.rfile.read(length)
        response, _records = handle_evolution_webhook_post(
            raw_body=raw_body,
            headers={key: value for key, value in self.headers.items()},
            config=self.config or EvolutionWhatsAppConfig.from_env(),
            adapter=self.adapter or build_default_adapter(self.config or EvolutionWhatsAppConfig.from_env()),
        )
        self._write(response)

    def log_message(self, format: str, *args) -> None:
        return

    def _write(self, response: EvolutionWebhookResponse) -> None:
        self.send_response(response.status_code)
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(response.body.encode("utf-8"))


def run_server(host: str = "127.0.0.1", port: int | None = None) -> None:
    config = EvolutionWhatsAppConfig.from_env()
    EvolutionWebhookRequestHandler.config = config
    EvolutionWebhookRequestHandler.adapter = build_default_adapter(config)
    selected_port = port or int(environ.get("EVOLUTION_WEBHOOK_PORT", "8081"))
    server = ThreadingHTTPServer((host, selected_port), EvolutionWebhookRequestHandler)
    print(json.dumps({
        "status": "READY",
        "provider": "evolution",
        "path": WEBHOOK_PATH,
        "url": f"http://{host}:{selected_port}{WEBHOOK_PATH}",
        "instanceConfigured": bool(config.instance_name),
    }))
    server.serve_forever()


if __name__ == "__main__":
    run_server()
