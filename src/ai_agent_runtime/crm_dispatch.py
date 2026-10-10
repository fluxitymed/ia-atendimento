"""Authenticated CRM dispatch boundary for the existing commercial agent."""

from __future__ import annotations

import hmac
import json
import logging
from dataclasses import asdict, replace
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
    SupabaseVaultCredentialProvider,
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
_V2_EVENT_FIELDS = _EVENT_FIELDS | {
    "logicalTurnId", "constituentMessageIds", "latestInboundCreatedAt",
}


def _safe_crm_log(event: str, fields: dict[str, Any]) -> None:
    log = logging.getLogger("ai_agent_runtime.crm_dispatch")
    level = logging.WARNING if event == "crm_dispatch_decision" else logging.INFO
    log.log(level, "%s %s", event, json.dumps(fields, sort_keys=True))


def _uuid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


_SAFE_RETRIEVAL_STATUSES = {"EXECUTED", "SKIPPED_NOT_REQUIRED", "NOT_CONFIGURED", "FAILED_TRANSIENT_EXHAUSTED"}
_SAFE_TURN_INTENTS = {"ATTRIBUTE_QUERY", "FACTUAL_QUERY", "NEED_DISCOVERY", "PROCEDURE_INTEREST",
                      "CONVERSATIONAL_RESPONSE", "CLINICAL_URGENCY", "SCHEDULING_CONFIRMATION"}
_SAFE_TURN_TOPICS = {"PRICE", "SCHEDULING", "PAYMENT", "EVALUATION"}
_SAFE_DECISION_CODES = {
    "UNSUPPORTED_FACTUAL_CLAIM", "INTERNAL_KNOWLEDGE_GAP_EXPOSED", "STALE_FREE_EVALUATION_AMBIGUITY",
    "REDUNDANT_PHONE_REQUEST", "REPEATED_KNOWN_OPERATIONAL_QUESTION", "PREMATURE_BOOKING_CONFIRMATION",
    "CORRECTION_REPETITION", "POST_PROCEDURE_BLEEDING", "SCHEDULING_TIME_CONFIRMATION_REQUIRED",
    "UNSUPPORTED_ATTRIBUTE", "ATTRIBUTE_WITHOUT_AUTHORIZED_EVIDENCE",
    "RETRIEVAL_UNAVAILABLE_FOR_FACTUAL_QUERY", "PATIENT_REQUESTED_HUMAN", "HUMAN_HANDOFF_REQUIRED",
    "MEDICATION_GUIDANCE_REQUIRED", "RESCHEDULING_REQUEST", "CANCELLATION_REQUEST",
    "CONFIG_LOOKUP_FAILED", "CONFIG_UNAVAILABLE", "MODEL_FAILURE", "RETRIEVAL_FAILURE", "RUNTIME_ERROR",
    "EVIDENCE_GROUNDED_REGENERATION_ACCEPTED",
}
_SAFE_REGENERATION_MODES = {"EVIDENCE_GROUNDED", "CONVERSATIONAL_NO_FACTS"}
_SAFE_GROUNDING_ORIGINS = {"USER_REQUESTED_UNSUPPORTED_FACT", "MODEL_INTRODUCED_UNSUPPORTED_FACT",
                           "RESPOND_ONLY_UNSUPPORTED_FACT", "UNDETERMINED_UNSUPPORTED_FACT"}
_SAFE_PROMPT_COVERAGE = {"COMPLETE", "PARTIAL", "NONE", "NOT_EVALUATED"}


def _safe_dispatch_diagnostic(event: dict[str, Any], state: AgentState | None, action: str,
                              reason_override: str | None = None) -> dict[str, Any]:
    """Project internal runtime events onto a strict, content-free terminal record."""
    raw_events = state.context.get("runtimeEvents") if state is not None else None
    events = [item for item in raw_events if isinstance(item, dict)] if isinstance(raw_events, list) else []

    def latest(stage: str) -> dict[str, Any]:
        for item in reversed(events):
            if item.get("stage") == stage and isinstance(item.get("details"), dict):
                return item["details"]
        return {}

    def count(stage: str) -> int:
        return sum(item.get("stage") == stage for item in events)

    def safe_code(value: Any) -> str | None:
        return value if isinstance(value, str) and value in _SAFE_DECISION_CODES else None

    def safe_ids(value: Any) -> list[str]:
        return list(dict.fromkeys(item for item in value[:6] if _uuid(item))) if isinstance(value, list) else []

    retrieval = latest("retrieval_completed")
    grounding = latest("grounding_result")
    failure = latest("grounding_failed")
    initial_failure = next((item.get("details", {}) for item in events
                            if item.get("stage") == "grounding_failed" and isinstance(item.get("details"), dict)), {})
    classified = latest("turn_classified")
    raw_topics = classified.get("requested_topics")
    raw_candidate_topics = retrieval.get("promptCandidateTopics")
    raw_missing_topics = retrieval.get("missingPromptTopics")
    handoff = state.handoff_context if state is not None and isinstance(state.handoff_context, dict) else {}
    retrieval_status = retrieval.get("status")
    turn_intent = classified.get("interpreted_intent")
    grounding_passed = grounding.get("passed")
    grounding_origin = failure.get("grounding_failure_origin")
    model_started = count("model_call_started")
    model_completed = count("model_called")
    regeneration_used = bool(count("response_regeneration_started"))
    raw_regeneration_mode = latest("response_regeneration_started").get("response_regeneration_mode")
    regeneration_mode = (raw_regeneration_mode if isinstance(raw_regeneration_mode, str)
                         and raw_regeneration_mode in _SAFE_REGENERATION_MODES else "NONE")
    decision_code = (
        safe_code(handoff.get("reason")) or safe_code(failure.get("reason"))
        or safe_code(latest("unsupported_factual_question").get("reason"))
    )
    if action == "HANDOFF":
        origin = ("GROUNDING" if failure else "ERROR_POLICY" if count("controlled_retrieval_failure")
                  else "DETERMINISTIC_RULE" if count("unsupported_factual_question") or decision_code == "PATIENT_REQUESTED_HUMAN"
                  else "UNKNOWN")
        reason_code = decision_code or "UNKNOWN"
    elif action == "NO_ACTION":
        origin, reason_code = "DETERMINISTIC_RULE", "EXPLICIT_NO_ACTION"
    elif action == "SEND_MESSAGE":
        origin = ("FALLBACK" if regeneration_used and grounding_passed is True
                  else "MODEL" if model_completed and grounding_passed is True
                  else "DETERMINISTIC_RULE" if not model_started and grounding_passed is True
                  else "UNKNOWN")
        reason_code = (("EVIDENCE_GROUNDED_REGENERATION_ACCEPTED" if regeneration_mode == "EVIDENCE_GROUNDED"
                        else "CONVERSATIONAL_REGENERATION_ACCEPTED") if origin == "FALLBACK"
                       else "GROUNDED_MODEL_RESPONSE" if origin == "MODEL"
                       else "GROUNDED_DETERMINISTIC_RESPONSE" if origin == "DETERMINISTIC_RULE"
                       else "UNKNOWN")
    else:
        origin = "ERROR_POLICY"
        reason_code = (safe_code(reason_override) or
                       ("MODEL_FAILURE" if count("model_call_failed") else
                        "RETRIEVAL_FAILURE" if count("retrieval_failed") else "RUNTIME_ERROR"))
    hits = retrieval.get("hitCount")
    valid_retrieval_status = retrieval_status if isinstance(retrieval_status, str) and retrieval_status in _SAFE_RETRIEVAL_STATUSES else "UNKNOWN"
    if valid_retrieval_status in {"EXECUTED", "FAILED_TRANSIENT_EXHAUSTED"} or count("retrieval_started"):
        retrieval_executed: bool | None = True
    elif valid_retrieval_status in {"SKIPPED_NOT_REQUIRED", "NOT_CONFIGURED"}:
        retrieval_executed = False
    else:
        retrieval_executed = None
    model_invoked: bool | None = True if model_completed else None if model_started else False
    policy_handoff = bool(count("unsupported_factual_question") or count("controlled_retrieval_failure"))
    grounding_validated = not policy_handoff and (type(grounding_passed) is bool or bool(failure))
    grounding_status = ("PASSED" if grounding_validated and grounding_passed is True
                        else "FAILED" if grounding_validated else "NOT_RUN" if events else "UNKNOWN")
    return {
        "correlationId": event["correlationId"],
        "organizationId": event["organizationId"],
        "conversationId": event["conversationId"],
        "action": action,
        "decisionOrigin": origin,
        "reasonCode": reason_code,
        "turnIntent": turn_intent if isinstance(turn_intent, str) and turn_intent in _SAFE_TURN_INTENTS else "UNKNOWN",
        "turnTopics": list(dict.fromkeys(topic for topic in raw_topics[:4]
                                          if isinstance(topic, str) and topic in _SAFE_TURN_TOPICS)) if isinstance(raw_topics, list) else [],
        "retrievalStatus": valid_retrieval_status,
        "retrievalExecuted": retrieval_executed,
        "retrievalHitCount": hits if type(hits) is int and 0 <= hits <= 1000 else 0,
        "commercialEvidencePresent": (bool(hits) if valid_retrieval_status == "EXECUTED" and type(hits) is int
                                      else None) if turn_intent == "ATTRIBUTE_QUERY" else None,
        "documentIds": safe_ids(retrieval.get("documentIds")),
        "documentVersionIds": safe_ids(retrieval.get("documentVersionIds")),
        "chunkIds": safe_ids(retrieval.get("chunkIds")),
        "promptChunkIds": safe_ids(retrieval.get("promptChunkIds")),
        "promptTopicCoverage": (retrieval.get("promptTopicCoverage")
                                if isinstance(retrieval.get("promptTopicCoverage"), str)
                                and retrieval.get("promptTopicCoverage") in _SAFE_PROMPT_COVERAGE else "NOT_EVALUATED"),
        "promptCandidateTopics": list(dict.fromkeys(topic for topic in raw_candidate_topics[:4]
                                                if isinstance(topic, str) and topic in _SAFE_TURN_TOPICS)) if isinstance(raw_candidate_topics, list) else [],
        "missingPromptTopics": list(dict.fromkeys(topic for topic in raw_missing_topics[:4]
                                              if isinstance(topic, str) and topic in _SAFE_TURN_TOPICS)) if isinstance(raw_missing_topics, list) else [],
        "budgetPolicyCandidate": retrieval.get("budgetPolicyCandidate") if type(retrieval.get("budgetPolicyCandidate")) is bool else None,
        "modelInvoked": model_invoked,
        "modelCallsStarted": model_started,
        "modelCallsCompleted": model_completed,
        "modelCallsFailed": count("model_call_failed"),
        "groundingStatus": grounding_status,
        "groundingPassed": grounding_passed if grounding_validated and type(grounding_passed) is bool else None,
        "groundingReason": (safe_code(grounding.get("reason")) or safe_code(failure.get("reason")) or "NONE") if grounding_validated else "NONE",
        "groundingFailureOrigin": grounding_origin if isinstance(grounding_origin, str) and grounding_origin in _SAFE_GROUNDING_ORIGINS else "NONE",
        "initialGroundingFailureOrigin": (initial_failure.get("grounding_failure_origin")
                                           if isinstance(initial_failure.get("grounding_failure_origin"), str)
                                           and initial_failure.get("grounding_failure_origin") in _SAFE_GROUNDING_ORIGINS
                                           else "NONE"),
        "regenerationUsed": regeneration_used,
        "regenerationMode": regeneration_mode,
    }


def _timestamp(value: Any) -> bool:
    if not isinstance(value, str) or len(value) > 40:
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def validate_dispatch_event(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ValueError("INVALID_REQUEST")
    fields = _EVENT_FIELDS if event.get("version") == "1" else _V2_EVENT_FIELDS
    if set(event) not in (fields, fields | {"history"}):
        raise ValueError("INVALID_REQUEST")
    if event["version"] not in {"1", "2"} or event["mode"] != "AI" or not isinstance(event["modeVersion"], int) or \
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
    if event["version"] == "2":
        members = event["constituentMessageIds"]
        if not _uuid(event["logicalTurnId"]) or not isinstance(members, list) or \
                not members or any(not _uuid(item) for item in members) or \
                len(set(members)) != len(members) or members[0] != event["inboundMessageId"] or \
                not _timestamp(event["latestInboundCreatedAt"]) or \
                event["latestInboundCreatedAt"] != message["timestamp"]:
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

    def __init__(self, *, environment_json: str | None = None, transport=None, source: str = "supabase"):
        self.environment = EnvironmentOrganizationConfigRepository(environment_json)
        self.transport = transport
        if source not in {"supabase", "env", "hybrid"}:
            raise ValueError("INVALID_ORGANIZATION_CONFIG_SOURCE")
        self.source = source

    @classmethod
    def from_environment(cls) -> "StrictCrmOrganizationConfigRepository":
        url, key = environ.get("SUPABASE_URL"), environ.get("SUPABASE_SERVICE_ROLE_KEY")
        transport = SupabaseOrganizationTransport(supabase_url=url, service_role_key=key) if url and key else None
        return cls(environment_json=environ.get("ORGANIZATION_RUNTIME_CONFIG_JSON"), transport=transport,
                   source=environ.get("ORGANIZATION_CONFIG_SOURCE", "supabase"))

    def get_by_organization_id(self, organization_id: str) -> OrganizationRuntimeConfig | None:
        if self.source == "env":
            config = self.environment.get_by_organization_id(organization_id)
            return replace(config, source="env") if config else None
        if self.transport is None:
            raise RuntimeError("ORGANIZATION_CONFIG_TRANSPORT_UNAVAILABLE")
        organizations = self.transport.get("organizations", {
            "select": "id,name,status", "id": f"eq.{organization_id}", "limit": "1",
        })
        if not organizations and self.source == "hybrid":
            config = self.environment.get_by_organization_id(organization_id)
            return replace(config, source="env") if config else None
        if len(organizations) != 1 or organizations[0].get("id") != organization_id or \
                organizations[0].get("status") not in {"active", "ACTIVE"}:
            return None
        configs = self.transport.get("organization_ai_configs", {
            "select": "*", "organization_id": f"eq.{organization_id}", "limit": "1",
        })
        if len(configs) != 1 or configs[0].get("organization_id") != organization_id or \
                configs[0].get("status") not in {"active", "ACTIVE"} or \
                not isinstance(configs[0].get("assistant_name"), str) or \
                not configs[0]["assistant_name"].strip():
            return None
        row = {**organizations[0], **configs[0], "status": organizations[0]["status"]}
        config = organization_runtime_config_from_mapping(organization_id, row)
        return replace(config, source="supabase")


def _default_graph(config: OrganizationRuntimeConfig, *, logger) -> AgentRuntimeGraph:
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
    if config.source == "supabase":
        credential_provider = SupabaseVaultCredentialProvider(transport=SupabaseOrganizationTransport(
            supabase_url=environ.get("SUPABASE_URL", ""),
            service_role_key=environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        ))
        preloaded_credential = credential_provider.get_credential(config.organization_id, "OPENAI")
        if preloaded_credential is None:
            raise RuntimeError("ORGANIZATION_CREDENTIAL_NOT_FOUND")
        logger("organization_credential_resolved", {
            "organizationId": config.organization_id, "source": "supabase",
            "credentialRef": preloaded_credential.credential_ref,
        })
    else:
        credential_provider = EnvironmentCredentialProvider(environ.get("ORGANIZATION_CREDENTIALS_JSON"))
        preloaded_credential = None

    class LoggingCredentialProvider:
        def get_credential(self, organization_id: str, provider: str):
            if preloaded_credential is not None:
                credential = preloaded_credential if organization_id == config.organization_id and \
                    provider.upper() == "OPENAI" else None
            else:
                credential = credential_provider.get_credential(organization_id, provider)
            if credential and preloaded_credential is None:
                logger("organization_credential_resolved", {
                    "organizationId": organization_id, "source": config.source,
                    "credentialRef": credential.credential_ref,
                })
            return credential

    generator = OpenAIWhatsAppResponseGenerator(
        OpenAIResponsesProvider(integrations),
        retrieval=retrieval,
        organization_config=config.to_commercial_config(),
        credential_provider=LoggingCredentialProvider(),
    )
    return AgentRuntimeGraph(response_generator=generator)


class CrmDispatchProcessor:
    def __init__(self, *, config_repository=None, graph_factory=None, logger=None):
        self.config_repository = config_repository or StrictCrmOrganizationConfigRepository.from_environment()
        self.graph_factory = graph_factory
        self.logger = logger or _safe_crm_log

    def _log_terminal(self, event: dict[str, Any], state: AgentState | None, action: str,
                      reason_code: str | None = None) -> None:
        # Observability must never change the CRM action or reveal an exception body.
        try:
            self.logger("crm_dispatch_decision", _safe_dispatch_diagnostic(event, state, action, reason_code))
        except Exception:
            pass

    def process(self, event: dict[str, Any]) -> dict[str, Any]:
        event = validate_dispatch_event(event)
        try:
            config = self.config_repository.get_by_organization_id(event["organizationId"])
        except Exception:
            self._log_terminal(event, None, "ERROR", "CONFIG_LOOKUP_FAILED")
            self.logger("organization_runtime_rejected", {"organizationId": event["organizationId"],
                         "reason": "CONFIG_LOOKUP_FAILED"})
            raise
        if not config or config.organization_id != event["organizationId"] or not config.is_active():
            self._log_terminal(event, None, "ERROR", "CONFIG_UNAVAILABLE")
            self.logger("organization_runtime_rejected", {"organizationId": event["organizationId"],
                         "reason": "CONFIG_UNAVAILABLE"})
            raise RuntimeError("RUNTIME_UNAVAILABLE")
        self.logger("organization_config_source_resolved", {"organizationId": config.organization_id,
                    "source": config.source})
        self.logger("organization_runtime_config_loaded", {"organizationId": config.organization_id,
                    "source": config.source, "configStatus": config.status})
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
        try:
            graph = self.graph_factory(config) if self.graph_factory else _default_graph(config, logger=self.logger)
            outcome = graph.run(state)
        except Exception:
            self._log_terminal(event, state, "ERROR")
            self.logger("organization_runtime_rejected", {"organizationId": config.organization_id,
                         "reason": "EXECUTION_FAILED"})
            raise
        base = {key: event[key] for key in (
            "version", "correlationId", "organizationId", "conversationId", "inboundMessageId", "modeVersion"
        )}
        if outcome.decision == AgentDecision.HUMAN_HANDOFF_REQUIRED:
            self._log_terminal(event, outcome, "HANDOFF")
            return {**base, "action": "HANDOFF", "metadata": {}}
        if outcome.context.get("noAction") is True and not outcome.response_text:
            self._log_terminal(event, outcome, "NO_ACTION")
            return {**base, "action": "NO_ACTION", "metadata": {}}
        if not isinstance(outcome.response_text, str) or not outcome.response_text.strip() or \
                len(outcome.response_text) > 4096 or "\x00" in outcome.response_text:
            self._log_terminal(event, outcome, "ERROR")
            raise RuntimeError("RUNTIME_UNAVAILABLE")
        self._log_terminal(event, outcome, "SEND_MESSAGE")
        return {**base, "action": "SEND_MESSAGE", "message": outcome.response_text, "metadata": {}}


def handle_crm_dispatch(raw_body: bytes, authorization: str | None, *, token: str | None,
                        processor: CrmDispatchProcessor | None = None) -> tuple[int, dict[str, Any]]:
    if not service_bearer_authorized(authorization, token):
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


def service_bearer_authorized(authorization: str | None, token: str | None) -> bool:
    """Private CRM→IA Bearer boundary, shared by dispatch and knowledge."""
    return bool(token and len(token) >= 32 and isinstance(authorization, str)
                and authorization.startswith("Bearer ")
                and hmac.compare_digest(authorization[7:], token))


class CrmDispatchRequestHandler(BaseHTTPRequestHandler):
    processor: CrmDispatchProcessor | None = None

    def do_GET(self) -> None:
        if not self.path.startswith("/internal/knowledge/"):
            self._write(404, {"error": "NOT_FOUND"})
            return
        self._knowledge("GET")

    def do_POST(self) -> None:
        if self.path.startswith("/internal/knowledge/"):
            self._knowledge("POST")
            return
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

    def _knowledge(self, method: str) -> None:
        from ai_agent_runtime.admin.knowledge_api import handle_knowledge_request, MAX_HTTP_BODY_BYTES
        authorization = self.headers.get("Authorization")
        token = environ.get("CRM_KNOWLEDGE_SERVICE_TOKEN")
        if not service_bearer_authorized(authorization, token):
            self._write(401, {"error": "UNAUTHORIZED"})
            return
        length = 0
        if method == "POST":
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if length < 0 or length > MAX_HTTP_BODY_BYTES:
                self._write(413, {"error": "INVALID_REQUEST"})
                return
        status, body = handle_knowledge_request(
            method, self.path, self.rfile.read(length) if length else b"", authorization,
            token=token, content_type=self.headers.get("Content-Type"))
        self._write(status, body)

    def log_message(self, format: str, *args) -> None:
        return

    def _write(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run_server(host: str = "127.0.0.1", port: int = 8083) -> None:
    server = ThreadingHTTPServer((host, port), CrmDispatchRequestHandler)
    server.serve_forever()


if __name__ == "__main__":
    run_server()
