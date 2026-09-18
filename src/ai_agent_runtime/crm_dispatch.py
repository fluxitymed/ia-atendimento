"""Authenticated CRM dispatch boundary for the existing commercial agent."""

from __future__ import annotations

import hmac
import json
from dataclasses import asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from os import environ
from typing import Any
from uuid import UUID

from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.organization_config import (
    EnvironmentCredentialProvider,
    EnvironmentOrganizationConfigRepository,
    OrganizationRuntimeConfig,
    SupabaseOrganizationTransport,
    organization_runtime_config_from_mapping,
)
from ai_agent_runtime.state import AgentDecision, AgentState
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator, ZApiRuntimeRetrieval


DISPATCH_PATH = "/internal/crm/whatsapp-dispatch"
MAX_BODY_BYTES = 16384
MAX_HISTORY = 8
_EVENT_FIELDS = {
    "version", "correlationId", "organizationId", "conversationId",
    "providerConnectionId", "contactId", "inboundMessageId", "mode",
    "modeVersion", "message",
}


def _uuid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def _timestamp(value: Any) -> bool:
    if not isinstance(value, str) or len(value) > 40:
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def validate_dispatch_event(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict) or set(event) not in (_EVENT_FIELDS, _EVENT_FIELDS | {"history"}):
        raise ValueError("INVALID_REQUEST")
    if event["version"] != "1" or event["mode"] != "AI" or not isinstance(event["modeVersion"], int) or \
            isinstance(event["modeVersion"], bool) or event["modeVersion"] < 0 or \
            any(not _uuid(event[key]) for key in (
                "correlationId", "organizationId", "conversationId", "providerConnectionId", "inboundMessageId"
            )) or (event["contactId"] is not None and not _uuid(event["contactId"])):
        raise ValueError("INVALID_REQUEST")
    message = event["message"]
    if not isinstance(message, dict) or set(message) != {"type", "text", "timestamp"} or \
            message["type"] != "text" or not isinstance(message["text"], str) or \
            not message["text"].strip() or len(message["text"]) > 4096 or "\x00" in message["text"] or \
            not _timestamp(message["timestamp"]):
        raise ValueError("INVALID_REQUEST")
    history = event.get("history", [])
    if not isinstance(history, list) or len(history) > MAX_HISTORY:
        raise ValueError("INVALID_REQUEST")
    for item in history:
        if not isinstance(item, dict) or set(item) != {"role", "text", "timestamp"} or \
                item["role"] not in {"contact", "human", "ai", "external"} or \
                not isinstance(item["text"], str) or not item["text"].strip() or \
                len(item["text"]) > 1000 or "\x00" in item["text"] or not _timestamp(item["timestamp"]):
            raise ValueError("INVALID_REQUEST")
    return event


class StrictCrmOrganizationConfigRepository:
    """No legacy/default tenant fallback on the CRM dispatch path."""

    def __init__(self, *, environment_json: str | None = None, transport=None):
        self.environment = EnvironmentOrganizationConfigRepository(environment_json)
        self.transport = transport

    @classmethod
    def from_environment(cls) -> "StrictCrmOrganizationConfigRepository":
        url, key = environ.get("SUPABASE_URL"), environ.get("SUPABASE_SERVICE_ROLE_KEY")
        transport = SupabaseOrganizationTransport(supabase_url=url, service_role_key=key) if url and key else None
        return cls(environment_json=environ.get("ORGANIZATION_RUNTIME_CONFIG_JSON"), transport=transport)

    def get_by_organization_id(self, organization_id: str) -> OrganizationRuntimeConfig | None:
        if self.transport is None:
            return self.environment.get_by_organization_id(organization_id)
        organizations = self.transport.get("organizations", {
            "select": "id,name,status", "id": f"eq.{organization_id}", "limit": "1",
        })
        if len(organizations) != 1 or organizations[0].get("id") != organization_id or \
                organizations[0].get("status") not in {"active", "ACTIVE"}:
            return None
        configs = self.transport.get("organization_ai_configs", {
            "select": "*", "organization_id": f"eq.{organization_id}", "limit": "1",
        })
        if len(configs) != 1 or configs[0].get("organization_id") != organization_id:
            return None
        row = {**organizations[0], **configs[0], "status": organizations[0]["status"]}
        return organization_runtime_config_from_mapping(organization_id, row)


def _default_graph(config: OrganizationRuntimeConfig) -> AgentRuntimeGraph:
    # Reuse the existing commercial generator, without constructing a WhatsApp provider.
    integrations = IntegrationConfig(
        openai_api_key="organization-scoped-openai-key",
        openai_responses_model=environ.get("OPENAI_RESPONSES_MODEL", "gpt-5.6-luna"),
        openai_reasoning_effort=environ.get("OPENAI_REASONING_EFFORT", "low"),
    )
    retrieval = None
    if environ.get("SUPABASE_URL") and environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        retrieval = ZApiRuntimeRetrieval(
            supabase_url=environ["SUPABASE_URL"],
            service_role_key=environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
    generator = OpenAIWhatsAppResponseGenerator(
        OpenAIResponsesProvider(integrations),
        retrieval=retrieval,
        organization_config=config.to_commercial_config(),
        credential_provider=EnvironmentCredentialProvider(environ.get("ORGANIZATION_CREDENTIALS_JSON")),
    )
    return AgentRuntimeGraph(response_generator=generator)


class CrmDispatchProcessor:
    def __init__(self, *, config_repository=None, graph_factory=None):
        self.config_repository = config_repository or StrictCrmOrganizationConfigRepository.from_environment()
        self.graph_factory = graph_factory or _default_graph

    def process(self, event: dict[str, Any]) -> dict[str, Any]:
        event = validate_dispatch_event(event)
        config = self.config_repository.get_by_organization_id(event["organizationId"])
        if not config or config.organization_id != event["organizationId"] or not config.is_active():
            raise RuntimeError("RUNTIME_UNAVAILABLE")
        history = [{
            "direction": "inbound" if item["role"] == "contact" else "outbound",
            "senderType": item["role"], "text": item["text"], "timestamp": item["timestamp"],
        } for item in event.get("history", [])]
        state = AgentState(
            conversation_id=event["conversationId"], organization_id=event["organizationId"],
            current_message=event["message"]["text"], messages=history,
            context={"currentMessageAt": event["message"]["timestamp"],
                     "organizationConfig": asdict(config.to_commercial_config())},
        )
        outcome = self.graph_factory(config).run(state)
        base = {key: event[key] for key in (
            "version", "correlationId", "organizationId", "conversationId", "inboundMessageId", "modeVersion"
        )}
        if outcome.decision == AgentDecision.HUMAN_HANDOFF_REQUIRED:
            return {**base, "action": "HANDOFF", "metadata": {}}
        if outcome.context.get("noAction") is True and not outcome.response_text:
            return {**base, "action": "NO_ACTION", "metadata": {}}
        if not isinstance(outcome.response_text, str) or not outcome.response_text.strip() or \
                len(outcome.response_text) > 4096 or "\x00" in outcome.response_text:
            raise RuntimeError("RUNTIME_UNAVAILABLE")
        return {**base, "action": "SEND_MESSAGE", "message": outcome.response_text, "metadata": {}}


def handle_crm_dispatch(raw_body: bytes, authorization: str | None, *, token: str | None,
                        processor: CrmDispatchProcessor | None = None) -> tuple[int, dict[str, Any]]:
    if not token or len(token) < 32 or not isinstance(authorization, str) or \
            not authorization.startswith("Bearer ") or \
            not hmac.compare_digest(authorization[7:], token):
        return 401, {"error": "UNAUTHORIZED"}
    if len(raw_body) > MAX_BODY_BYTES:
        return 413, {"error": "INVALID_REQUEST"}
    try:
        event = validate_dispatch_event(json.loads(raw_body))
    except (ValueError, UnicodeDecodeError, TypeError):
        return 400, {"error": "INVALID_REQUEST"}
    try:
        return 200, (processor or CrmDispatchProcessor()).process(event)
    except Exception:
        return 503, {"error": "RUNTIME_UNAVAILABLE"}


class CrmDispatchRequestHandler(BaseHTTPRequestHandler):
    processor: CrmDispatchProcessor | None = None

    def do_POST(self) -> None:
        if self.path != DISPATCH_PATH:
            self._write(404, {"error": "NOT_FOUND"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            self._write(413, {"error": "INVALID_REQUEST"})
            return
        status, body = handle_crm_dispatch(
            self.rfile.read(length), self.headers.get("Authorization"),
            token=environ.get("CRM_DISPATCH_SERVICE_TOKEN"),
            processor=self.processor,
        )
        self._write(status, body)

    def log_message(self, format: str, *args) -> None:
        return

    def _write(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run_server(host: str = "127.0.0.1", port: int = 8083) -> None:
    server = ThreadingHTTPServer((host, port), CrmDispatchRequestHandler)
    server.serve_forever()


if __name__ == "__main__":
    run_server()
