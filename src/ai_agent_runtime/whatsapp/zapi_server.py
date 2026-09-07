from __future__ import annotations

import json
import re
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from os import environ
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from ai_agent_runtime.commercial import CommercialPlaybook, OrganizationCommercialConfig, organization_config_from_context
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.sandbox_ids import AURORA_ORG_ID, BOREAL_ORG_ID, DATASET_VERSION, LEONARDO_ORG_ID, deterministic_sandbox_uuid
from ai_agent_runtime.state import AgentDecision, AgentStage

from .adapter import OrganizationResolver, WhatsAppChannelAdapter
from .batching import MessageBatchingConfig, MessageBatchingWhatsAppChannelAdapter
from .channel import JsonFileWhatsAppStore
from .media import MediaProcessor, OpenAISpeechToTextProvider
from .providers import build_whatsapp_provider
from .zapi import ZApiWhatsAppConfig
from .zapi_webhook import WEBHOOK_PATH, ZApiWebhookResponse, handle_zapi_webhook_post


HEALTH_PATH = "/health"
DEFAULT_RENDER_STORE_PATH = Path("/var/data/zapi-whatsapp-store.json")
DEFAULT_LOCAL_STORE_PATH = Path(".sandbox") / "zapi-whatsapp-store.json"


class JsonStageLogger:
    def __call__(self, stage: str, details: dict[str, Any] | None = None) -> None:
        print(json.dumps({"event": stage, "details": _safe(details or {})}, sort_keys=True), flush=True)


class LiveRuntimeHttpError(RuntimeError):
    def __init__(self, *, stage: str, provider: str, status: int | None, endpoint: str, body: Any = None, code: str | None = None):
        self.stage = stage
        self.provider = provider
        self.status = status
        self.endpoint = endpoint
        self.body = _safe_provider_body(body)
        self.code = code
        super().__init__(self._message())

    def details(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "endpoint": self.endpoint,
            "code": self.code,
            "body": self.body,
        }

    def _message(self) -> str:
        return json.dumps(
            {
                "stage": self.stage,
                "provider": self.provider,
                "status": self.status,
                "endpoint": self.endpoint,
                "code": self.code,
                "body": self.body,
            },
            sort_keys=True,
        )


class LiveRuntimeGenerationError(RuntimeError):
    pass


RETRIEVAL_MAX_ATTEMPTS = 3
RETRIEVAL_BACKOFF_SECONDS = (0.15, 0.35)


class OpenAIWhatsAppResponseGenerator:
    def __init__(
        self,
        provider: OpenAIResponsesProvider,
        *,
        retrieval: "ZApiRuntimeRetrieval | None" = None,
        commercial_playbook: CommercialPlaybook | None = None,
        organization_config: OrganizationCommercialConfig | None = None,
    ):
        self.provider = provider
        self.retrieval = retrieval
        self.commercial_playbook = commercial_playbook or CommercialPlaybook()
        self.organization_config = organization_config

    def generate(self, state, *, emit):
        evidence = []
        catalog_decision = None
        conversation_text = "\n".join(
            [str(item.get("text") or "") for item in state.messages if item.get("text")]
        )
        previous_assistant_question = str(state.context.get("previousAssistantQuestion") or "")
        organization_config = self.organization_config or organization_config_from_context(state.context)
        commercial_state = self.commercial_playbook.evaluate(
            state.messages,
            current_message=state.current_message,
            organization_config=organization_config,
            scheduling_context_active=state.scheduling_context_active,
            previous_assistant_question=previous_assistant_question,
            channel_contact_external_id=state.context.get("channelContactExternalId"),
            scheduling_status=state.context.get("schedulingStatus"),
            assistant_introduced=state.context.get("assistantIntroduced"),
            answered_facts=state.context.get("answeredFacts"),
            current_message_at=state.context.get("currentMessageAt"),
            previous_assistant_message_at=state.context.get("previousAssistantMessageAt"),
        )
        state.context["commercialState"] = commercial_state.as_dict()
        state.context["assistantIntroduced"] = bool(commercial_state.assistant_introduced)
        state.context["answeredFacts"] = dict(commercial_state.answered_facts)
        emit(
            "operational_memory_updated",
            {
                "fieldCount": len(commercial_state.operational_memory),
                "registrationComplete": commercial_state.registration_complete,
                "missingRequiredFields": list(commercial_state.missing_required_fields),
            },
        )
        retrieval_query = _contextual_retrieval_query(
            state.current_message,
            commercial_state.as_dict(),
            history_text=conversation_text,
            previous_assistant_question=previous_assistant_question,
        )
        evidence_requirement = _turn_evidence_requirement(
            state.current_message,
            commercial_state.as_dict(),
            history_text=conversation_text,
            previous_assistant_question=previous_assistant_question,
            stage=state.stage.value,
        )
        emit("TURN_EVIDENCE_REQUIREMENT", evidence_requirement)
        emit("turn_evidence_requirement", evidence_requirement)
        retrieval_status = "NOT_CONFIGURED"
        retrieval_failure: LiveRuntimeHttpError | None = None
        if self.retrieval and evidence_requirement["requires_retrieval"]:
            emit(
                "retrieval_started",
                {
                    "provider": "supabase",
                    "endpoint": "rest/v1/chunks",
                    "queryMode": "CONTEXTUAL",
                    "termCount": len(_retrieval_terms(retrieval_query)),
                },
            )
            emit(
                "contextual_retrieval_query",
                {
                    "query": retrieval_query,
                    "currentMessageOnly": retrieval_query.strip() == str(state.current_message or "").strip(),
                    "contextualShortAnswerResolved": commercial_state.contextual_short_answer_resolved,
                },
            )
            try:
                evidence, catalog_decision = _run_retrieval_with_retry(
                    lambda: (
                        self.retrieval.search(state.organization_id, retrieval_query),
                        self.retrieval.closed_world_procedure_decision(state.organization_id, state.current_message),
                    ),
                    emit=emit,
                )
                retrieval_status = "EXECUTED"
            except LiveRuntimeHttpError as exc:
                emit("retrieval_failed", exc.details())
                if not _is_retryable_retrieval_error(exc):
                    raise
                retrieval_failure = exc
                retrieval_status = "FAILED_TRANSIENT_EXHAUSTED"
        elif self.retrieval:
            retrieval_status = "SKIPPED_NOT_REQUIRED"
            emit(
                "retrieval_skipped",
                {
                    "provider": "supabase",
                    "reason": evidence_requirement["reason"],
                    "requiresEvidence": evidence_requirement["requires_evidence"],
                },
            )
        current_evidence_count = len(evidence)
        reused_evidence = _reusable_conversation_evidence(
            state.context.get("conversationEvidence"),
            organization_id=state.organization_id,
            query=retrieval_query,
        )
        if reused_evidence:
            emit(
                "conversation_evidence_reused",
                {"count": len(reused_evidence), "scope": "same_conversation_same_organization"},
            )
        evidence = _dedupe_evidence([*evidence, *reused_evidence])
        state.context["conversationEvidence"] = _conversation_evidence_snapshot(
            evidence,
            organization_id=state.organization_id,
            query=retrieval_query,
        )
        emit(
            "retrieval_completed",
            {
                "status": retrieval_status,
                "hitCount": current_evidence_count,
                "conversationEvidenceCount": len(reused_evidence),
                "totalEvidenceCount": len(evidence),
            },
        )
        respond_only = _deterministic_respond_only_response(
            state.current_message,
            commercial_state.as_dict(),
            organization_config=organization_config,
        )
        if respond_only:
            emit(
                "current_turn_response_only",
                {
                    "current_turn_intent": commercial_state.current_turn_intent.value,
                    "context_continuity": commercial_state.context_continuity.value,
                    "cta_policy": commercial_state.cta_policy,
                },
            )
            grounding = validate_live_grounding(
                respond_only,
                evidence_count=len(evidence),
                evidence=evidence,
                organization_config=organization_config,
                commercial_state=commercial_state.as_dict(),
            )
            emit("grounding_result", grounding)
            if not grounding["passed"]:
                emit("grounding_failed", {"reason": grounding["reason"], "grounding_failure_origin": "RESPOND_ONLY_UNSUPPORTED_FACT"})
                raise LiveRuntimeGenerationError("RESPOND_ONLY_UNGROUNDED")
            state.decision = AgentDecision.ANSWER_GROUNDED
            state.context["answeredFacts"] = _updated_answered_facts(
                state.context.get("answeredFacts"),
                respond_only,
                evidence=evidence,
            )
            state.context["assistantIntroduced"] = _assistant_introduced_after_response(
                state.context.get("assistantIntroduced"),
                respond_only,
                commercial_state.as_dict(),
            )
            return respond_only
        if catalog_decision and catalog_decision["decision"] == "NOT_OFFERED":
            emit("closed_world_procedure_decision", {"decision": "NOT_OFFERED", "procedure": catalog_decision["procedure"]})
            state.decision = AgentDecision.ANSWER_GROUNDED
            return f"Nao, nao trabalhamos com {catalog_decision['procedure']}."
        turn_context = _classify_turn_context(
            state.current_message,
            evidence,
            history_text=conversation_text,
            previous_assistant_question=previous_assistant_question,
            stage=state.stage.value,
        )
        emit(
            "turn_classified",
            {
                "turn_relation": turn_context["turn_relation"],
                "interpreted_intent": turn_context["interpreted_intent"],
                "conversation_stage": turn_context["conversation_stage"],
                "requires_evidence": turn_context["requires_evidence"],
                "handoff_decision": turn_context["handoff_decision"],
            },
        )
        emit(
            "turn_requires_evidence",
            {
                "user_requires_evidence": turn_context["requires_evidence"],
                "turn_relation": turn_context["turn_relation"],
                "interpreted_intent": turn_context["interpreted_intent"],
            },
        )
        if turn_context["unsupported_attribute_reason"]:
            emit("unsupported_attribute_reason", {"reason": turn_context["unsupported_attribute_reason"]})
        if turn_context["handoff_decision"] == "HUMAN_HANDOFF_REQUIRED":
            handoff_reason = "CLINICAL_URGENCY_OR_SENSITIVE_TOPIC" if turn_context["interpreted_intent"] == "CLINICAL_URGENCY" else "UNSUPPORTED_ATTRIBUTE"
            emit("unsupported_factual_question", {"decision": "HUMAN_HANDOFF_REQUIRED", "reason": handoff_reason})
            emit("grounding_result", {"passed": False, "mode": "HUMAN_HANDOFF_REQUIRED", "reason": handoff_reason, "requiresEvidence": True})
            state.decision = AgentDecision.HUMAN_HANDOFF_REQUIRED
            state.stage = AgentStage.HANDOFF
            state.handoff_context = {
                "conversationId": state.conversation_id,
                "organizationId": state.organization_id,
                "messages": list(state.messages),
                "currentMessage": state.current_message,
                "reason": handoff_reason,
                "suppressOutbound": True,
                "turnRelation": turn_context["turn_relation"],
                "interpretedIntent": turn_context["interpreted_intent"],
            }
            return ""
        if _unclear_procedure_price_query(state.current_message):
            response = "Nao consegui identificar qual procedimento no audio. Pode me dizer por texto qual tratamento voce quer saber o valor?"
            grounding = validate_live_grounding(
                response,
                evidence_count=len(evidence),
                evidence=evidence,
                organization_config=organization_config,
                commercial_state=commercial_state.as_dict(),
            )
            emit("grounding_result", grounding)
            state.decision = AgentDecision.ANSWER_GROUNDED
            return response
        if retrieval_failure and turn_context["requires_evidence"]:
            emit(
                "controlled_retrieval_failure",
                {
                    "decision": "HUMAN_HANDOFF_REQUIRED",
                    "reason": "RETRIEVAL_UNAVAILABLE_FOR_FACTUAL_QUERY",
                    "provider": "supabase",
                },
            )
            emit("grounding_result", {"passed": False, "mode": "HUMAN_HANDOFF_REQUIRED", "reason": "RETRIEVAL_UNAVAILABLE_FOR_FACTUAL_QUERY", "requiresEvidence": True})
            state.decision = AgentDecision.HUMAN_HANDOFF_REQUIRED
            state.stage = AgentStage.HANDOFF
            state.handoff_context = {
                "conversationId": state.conversation_id,
                "organizationId": state.organization_id,
                "messages": list(state.messages),
                "currentMessage": state.current_message,
                "reason": "RETRIEVAL_UNAVAILABLE_FOR_FACTUAL_QUERY",
                "retrievalError": retrieval_failure.details(),
                "suppressOutbound": True,
            }
            return ""
        deterministic_scheduling = _deterministic_scheduling_response(
            state.current_message,
            commercial_state.as_dict(),
            previous_assistant_question=previous_assistant_question,
            organization_config=organization_config,
        )
        if deterministic_scheduling:
            emit(
                "scheduling_transition_resolved",
                {
                    "previousAssistantAction": "PROPOSE_APPOINTMENT",
                    "appointment_intent": True,
                    "next_best_action": "SCHEDULE",
                    "scheduling_state": "COLLECTING_REQUIRED_DATA",
                },
            )
            state.context["commercialState"] = {
                **commercial_state.as_dict(),
                "next_best_action": "SCHEDULE",
                "scheduling_state": "COLLECTING_REQUIRED_DATA",
                "operational_memory": {**dict(commercial_state.operational_memory), "appointment_intent": "true"},
            }
            grounding = validate_live_grounding(
                deterministic_scheduling,
                evidence_count=len(evidence),
                evidence=evidence,
                organization_config=organization_config,
                commercial_state=state.context["commercialState"],
            )
            emit("grounding_result", grounding)
            if grounding["passed"]:
                state.context["assistantIntroduced"] = _assistant_introduced_after_response(
                    state.context.get("assistantIntroduced"),
                    deterministic_scheduling,
                    commercial_state.as_dict(),
                )
                state.context["answeredFacts"] = _updated_answered_facts(
                    state.context.get("answeredFacts"),
                    deterministic_scheduling,
                    evidence=evidence,
                )
                return deterministic_scheduling
        evidence_text = "\n".join(f"- {item['content']}" for item in evidence[:4])
        emit("commercial_state_updated", commercial_state.as_dict())
        system_prompt = self.commercial_playbook.prompt_sections(
            commercial_state,
            organization_config=organization_config,
            authorized_evidence=evidence_text,
        )
        input_messages = [
            {
                "role": "system",
                "content": system_prompt + _sales_turn_instruction(turn_context),
            },
            *[
                {"role": "user" if item.get("direction") == "inbound" else "assistant", "content": str(item.get("text") or "")}
                for item in state.messages
                if item.get("text")
            ],
        ]
        emit("model_call_started", {"provider": "openai", "endpoint": "responses", "model": self.provider.config.openai_responses_model})
        try:
            response = self.provider.create_response(input_messages=input_messages)
        except LiveRuntimeHttpError as exc:
            emit("model_call_failed", exc.details())
            raise
        except Exception as exc:
            converted = _provider_exception(
                exc,
                stage="model_call",
                provider="openai",
                endpoint="responses",
            )
            emit("model_call_failed", converted.details())
            raise converted from exc
        emit("model_called", {"provider": "openai", "model": self.provider.config.openai_responses_model})
        text = _extract_response_text(response)
        grounding = validate_live_grounding(
            text,
            evidence_count=len(evidence),
            evidence=evidence,
            organization_config=organization_config,
            commercial_state=commercial_state.as_dict(),
        )
        emit("grounding_result", grounding)
        emit(
            "response_requires_evidence",
            {
                "attempt": 1,
                "response_contains_factual_claims": grounding["requiresEvidence"],
                "evidenceCount": len(evidence),
            },
        )
        if not grounding["passed"]:
            failure_origin = (
                "MODEL_INTRODUCED_UNSUPPORTED_FACT"
                if grounding.get("reason") == "INTERNAL_KNOWLEDGE_GAP_EXPOSED"
                else "USER_REQUESTED_UNSUPPORTED_FACT"
                if turn_context["requires_evidence"]
                else "MODEL_INTRODUCED_UNSUPPORTED_FACT"
            )
            emit(
                "grounding_failed",
                {
                    "reason": grounding["reason"],
                    "grounding_failure_origin": failure_origin,
                    "user_requires_evidence": turn_context["requires_evidence"],
                    "response_contains_factual_claims": grounding["requiresEvidence"],
                    "evidenceCount": len(evidence),
                },
            )
            emit("grounding_failure_origin", {"origin": failure_origin})
            if failure_origin == "USER_REQUESTED_UNSUPPORTED_FACT":
                state.decision = AgentDecision.HUMAN_HANDOFF_REQUIRED
                state.stage = AgentStage.HANDOFF
                state.handoff_context = {
                    "conversationId": state.conversation_id,
                    "organizationId": state.organization_id,
                    "messages": list(state.messages),
                    "currentMessage": state.current_message,
                    "reason": grounding["reason"],
                    "grounding": grounding,
                    "groundingFailureOrigin": failure_origin,
                }
                return ""
            retry_text = self._regenerate_conversational_response(
                input_messages,
                evidence_count=len(evidence),
                evidence=evidence,
                organization_config=organization_config,
                commercial_state=commercial_state.as_dict(),
                emit=emit,
            )
            state.context["assistantIntroduced"] = _assistant_introduced_after_response(
                state.context.get("assistantIntroduced"),
                retry_text,
                commercial_state.as_dict(),
            )
            state.context["answeredFacts"] = _updated_answered_facts(
                state.context.get("answeredFacts"),
                retry_text,
                evidence=evidence,
            )
            return retry_text
        state.context["assistantIntroduced"] = _assistant_introduced_after_response(
            state.context.get("assistantIntroduced"),
            text,
            commercial_state.as_dict(),
        )
        state.context["answeredFacts"] = _updated_answered_facts(
            state.context.get("answeredFacts"),
            text,
            evidence=evidence,
        )
        return text

    def _regenerate_conversational_response(
        self,
        input_messages: list[dict[str, str]],
        *,
        evidence_count: int,
        organization_config: OrganizationCommercialConfig | None,
        emit,
        evidence: list[dict[str, Any]] | None = None,
        commercial_state: dict[str, Any] | None = None,
    ) -> str:
        emit("response_regeneration_started", {"response_regeneration_mode": "CONVERSATIONAL_NO_FACTS", "maxRetries": 1})
        retry_messages = _conversational_no_facts_messages(input_messages)
        emit("model_call_started", {"provider": "openai", "endpoint": "responses", "model": self.provider.config.openai_responses_model, "mode": "CONVERSATIONAL_NO_FACTS"})
        try:
            response = self.provider.create_response(input_messages=retry_messages)
        except LiveRuntimeHttpError as exc:
            emit("model_call_failed", exc.details())
            raise
        except Exception as exc:
            converted = _provider_exception(
                exc,
                stage="model_call",
                provider="openai",
                endpoint="responses",
            )
            emit("model_call_failed", converted.details())
            raise converted from exc
        emit("model_called", {"provider": "openai", "model": self.provider.config.openai_responses_model, "mode": "CONVERSATIONAL_NO_FACTS"})
        retry_text = _extract_response_text(response)
        emit("response_regeneration_completed", {"response_regeneration_mode": "CONVERSATIONAL_NO_FACTS", "hasText": bool(retry_text)})
        retry_grounding = validate_live_grounding(
            retry_text,
            evidence_count=evidence_count,
            evidence=evidence,
            organization_config=organization_config,
            commercial_state=commercial_state,
        )
        emit("grounding_result", retry_grounding)
        emit(
            "response_requires_evidence",
            {
                "attempt": 2,
                "response_contains_factual_claims": retry_grounding["requiresEvidence"],
                "evidenceCount": evidence_count,
            },
        )
        if not retry_grounding["passed"]:
            emit(
                "grounding_failed",
                {
                    "reason": retry_grounding["reason"],
                    "grounding_failure_origin": "MODEL_INTRODUCED_UNSUPPORTED_FACT",
                    "user_requires_evidence": False,
                    "response_contains_factual_claims": retry_grounding["requiresEvidence"],
                    "evidenceCount": evidence_count,
                },
            )
            emit("response_regeneration_failed", {"reason": retry_grounding["reason"], "maxRetriesReached": True})
            raise LiveRuntimeGenerationError("CONVERSATIONAL_REGENERATION_UNGROUNDED")
        return retry_text


class ZApiRuntimeRetrieval:
    def __init__(self, *, supabase_url: str, service_role_key: str):
        self.supabase_url = supabase_url
        self.service_role_key = service_role_key

    def search(self, organization_id: str, query: str, *, limit: int = 6) -> list[dict[str, Any]]:
        if not organization_id:
            return []
        version_ids = self._published_processed_version_ids(organization_id)
        if not version_ids:
            return []
        terms = _retrieval_terms(query)
        if not terms:
            return []
        rows_by_id: dict[str, dict[str, Any]] = {}
        remaining = limit
        for term in terms:
            rows = self._chunk_rows(organization_id=organization_id, version_ids=version_ids, term=term, limit=remaining)
            for row in rows:
                if row.get("organization_id") != organization_id:
                    continue
                if row.get("document_version_id") not in version_ids:
                    continue
                rows_by_id.setdefault(str(row.get("id")), row)
            remaining = max(limit - len(rows_by_id), 0)
            if remaining <= 0:
                break
        return list(rows_by_id.values())[:limit]

    def _published_processed_version_ids(self, organization_id: str) -> set[str]:
        params = {
            "select": "id,status,processing_valid,organization_id",
            "organization_id": f"eq.{organization_id}",
            "status": "eq.PUBLISHED",
            "processing_valid": "is.true",
            "limit": "100",
        }
        rows = self._get_json("document_versions", params, endpoint="rest/v1/document_versions")
        return {
            str(row.get("id"))
            for row in rows
            if row.get("organization_id") == organization_id
            and row.get("status") == "PUBLISHED"
            and row.get("processing_valid") is True
            and row.get("id")
        }

    def _chunk_rows(self, *, organization_id: str, version_ids: set[str], term: str, limit: int) -> list[dict[str, Any]]:
        params = {
            "select": "id,organization_id,document_version_id,content",
            "organization_id": f"eq.{organization_id}",
            "document_version_id": f"in.({','.join(sorted(version_ids))})",
            "content": f"ilike.*{_safe_like(term)}*",
            "limit": str(max(limit, 1)),
        }
        return self._get_json("chunks", params, endpoint="rest/v1/chunks")

    def _get_json(self, table: str, params: dict[str, str], *, endpoint: str) -> list[dict[str, Any]]:
        url = f"{self.supabase_url.rstrip('/')}/rest/v1/{table}?{parse.urlencode(params)}"
        req = request.Request(url, headers=self._headers(), method="GET")
        try:
            with request.urlopen(req, timeout=20) as response:
                rows = json.loads(response.read().decode("utf-8") or "[]")
        except Exception as exc:
            raise _provider_exception(exc, stage="retrieval", provider="supabase", endpoint=endpoint) from exc
        return rows if isinstance(rows, list) else []

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
        }

    def closed_world_procedure_decision(self, organization_id: str, query: str) -> dict[str, Any] | None:
        procedure = _requested_procedure(query)
        if not procedure:
            return None
        versions = self._closed_world_catalog_versions(organization_id)
        if not versions:
            return None
        catalog_text = "\n".join(
            row.get("content", "")
            for row in self._chunks_for_versions(organization_id=organization_id, version_ids=set(versions))
            if row.get("organization_id") == organization_id and row.get("document_version_id") in versions
        )
        offered = _catalog_procedure_names(catalog_text)
        normalized_procedure = _normalize_text(procedure)
        if normalized_procedure in offered:
            return {"decision": "OFFERED", "procedure": procedure}
        return {"decision": "NOT_OFFERED", "procedure": procedure}

    def _closed_world_catalog_versions(self, organization_id: str) -> set[str]:
        documents = self._get_json(
            "documents",
            {
                "select": "id,organization_id,document_type",
                "organization_id": f"eq.{organization_id}",
                "document_type": "eq.PROCEDURE_CATALOG",
                "limit": "32",
            },
            endpoint="rest/v1/documents",
        )
        document_ids = {str(row.get("id")) for row in documents if row.get("organization_id") == organization_id and row.get("id")}
        if not document_ids:
            return set()
        versions = self._get_json(
            "document_versions",
            {
                "select": "id,document_id,organization_id,status,processing_valid,knowledge_mode,closed_world_completeness_approved",
                "organization_id": f"eq.{organization_id}",
                "document_id": f"in.({','.join(sorted(document_ids))})",
                "status": "eq.PUBLISHED",
                "processing_valid": "is.true",
                "knowledge_mode": "eq.CLOSED_WORLD",
                "closed_world_completeness_approved": "is.true",
                "limit": "32",
            },
            endpoint="rest/v1/document_versions",
        )
        return {
            str(row.get("id"))
            for row in versions
            if row.get("organization_id") == organization_id
            and row.get("document_id") in document_ids
            and row.get("status") == "PUBLISHED"
            and row.get("processing_valid") is True
            and row.get("knowledge_mode") == "CLOSED_WORLD"
            and row.get("closed_world_completeness_approved") is True
            and row.get("id")
        }

    def _chunks_for_versions(self, *, organization_id: str, version_ids: set[str]) -> list[dict[str, Any]]:
        if not version_ids:
            return []
        return self._get_json(
            "chunks",
            {
                "select": "id,organization_id,document_version_id,content",
                "organization_id": f"eq.{organization_id}",
                "document_version_id": f"in.({','.join(sorted(version_ids))})",
                "limit": "100",
            },
            endpoint="rest/v1/chunks",
        )


def build_default_adapter(config: ZApiWhatsAppConfig) -> WhatsAppChannelAdapter:
    stage_logger = JsonStageLogger()
    provider = build_whatsapp_provider("zapi", zapi_config=config)
    instance = config.instance_id or "missing-zapi-instance"
    organization_id = _runtime_organization_id(config.organization_id)
    resolver = OrganizationResolver({instance: organization_id})
    integrations = IntegrationConfig.from_env()
    response_generator = None
    if integrations.openai_api_key:
        retrieval = None
        if integrations.supabase_url and integrations.supabase_service_role_key:
            retrieval = ZApiRuntimeRetrieval(
                supabase_url=integrations.supabase_url,
                service_role_key=integrations.supabase_service_role_key,
            )
        commercial_playbook = CommercialPlaybook()
        response_generator = OpenAIWhatsAppResponseGenerator(
            OpenAIResponsesProvider(integrations),
            retrieval=retrieval,
            commercial_playbook=commercial_playbook,
            organization_config=_organization_commercial_config_from_env(),
        )
    runtime_graph = AgentRuntimeGraph(response_generator=response_generator, stage_logger=stage_logger)
    media_processor = None
    if _audio_inbound_enabled() and integrations.openai_api_key:
        media_processor = MediaProcessor(
            provider=provider,
            speech_to_text=OpenAISpeechToTextProvider(integrations),
            stage_logger=stage_logger,
        )
    adapter = WhatsAppChannelAdapter(
        provider=provider,
        store=_build_zapi_store(),
        organization_resolver=resolver,
        runtime_graph=runtime_graph,
        media_processor=media_processor,
        allow_placeholder_ack=False,
        reject_out_of_order=True,
        inbound_enabled=_ai_inbound_enabled(),
        stage_logger=stage_logger,
    )
    if not _ai_inbound_enabled():
        return adapter
    batching_config = MessageBatchingConfig.from_env()
    if not batching_config.enabled:
        return adapter
    return MessageBatchingWhatsAppChannelAdapter(adapter, config=batching_config)


class ZApiWebhookRequestHandler(BaseHTTPRequestHandler):
    adapter: WhatsAppChannelAdapter | None = None
    config: ZApiWhatsAppConfig | None = None

    def do_GET(self) -> None:
        if parse.urlparse(self.path).path != HEALTH_PATH:
            self._write(ZApiWebhookResponse(status_code=404, body="Not Found"))
            return
        payload = {
            "status": "ok",
            "provider": "zapi",
            "webhookPath": WEBHOOK_PATH,
            "aiInboundEnabled": _ai_inbound_enabled(),
        }
        self._write(
            ZApiWebhookResponse(
                status_code=200,
                body=json.dumps(payload, sort_keys=True),
                headers={"Content-Type": "application/json"},
            )
        )

    def do_POST(self) -> None:
        if parse.urlparse(self.path).path != WEBHOOK_PATH:
            self._write(ZApiWebhookResponse(status_code=404, body="Not Found"))
            return
        length = int(self.headers.get("content-length", "0") or "0")
        raw_body = self.rfile.read(length)
        config = self.config or ZApiWhatsAppConfig.from_env()
        response, _records = handle_zapi_webhook_post(
            raw_body=raw_body,
            headers={key: value for key, value in self.headers.items()},
            config=config,
            adapter=self.adapter or build_default_adapter(config),
            stage_logger=JsonStageLogger(),
        )
        self._write(response)

    def log_message(self, format: str, *args) -> None:
        return

    def _write(self, response: ZApiWebhookResponse) -> None:
        self.send_response(response.status_code)
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(response.body.encode("utf-8"))


def run_server(host: str | None = None, port: int | None = None) -> None:
    config = ZApiWhatsAppConfig.from_env()
    ZApiWebhookRequestHandler.config = config
    ZApiWebhookRequestHandler.adapter = build_default_adapter(config)
    selected_host = _server_host(host)
    selected_port = _server_port(port)
    server = ThreadingHTTPServer((selected_host, selected_port), ZApiWebhookRequestHandler)
    print(
        json.dumps(
            {
                "status": "READY",
                "provider": "zapi",
                "path": WEBHOOK_PATH,
                "healthPath": HEALTH_PATH,
                "url": f"http://{selected_host}:{selected_port}{WEBHOOK_PATH}",
                "instanceConfigured": bool(config.instance_id),
                "aiInboundEnabled": _ai_inbound_enabled(),
                "storePath": str(_zapi_store_path()),
            }
        )
    )
    server.serve_forever()


def _server_host(host: str | None = None) -> str:
    return host or environ.get("HOST", "0.0.0.0")


def _server_port(port: int | None = None) -> int:
    if port is not None:
        return port
    return int(environ.get("PORT") or environ.get("ZAPI_WEBHOOK_PORT") or "8082")


def _ai_inbound_enabled() -> bool:
    return environ.get("AI_INBOUND_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


def _audio_inbound_enabled() -> bool:
    return environ.get("AUDIO_INBOUND_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}

def _extract_response_text(response: dict[str, Any]) -> str:
    if response.get("output_text"):
        return str(response["output_text"]).strip()
    fragments: list[str] = []
    for item in response.get("output", []) if isinstance(response.get("output"), list) else []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
            if isinstance(content, dict):
                text = content.get("text") or content.get("output_text")
                if text:
                    fragments.append(str(text))
    return "\n".join(fragment.strip() for fragment in fragments if fragment.strip()).strip()


def _sales_turn_instruction(turn_context: dict[str, Any]) -> str:
    if turn_context.get("requires_evidence"):
        return ""
    if turn_context.get("interpreted_intent") not in {"NEED_DISCOVERY", "PROCEDURE_INTEREST", "CONVERSATIONAL_RESPONSE"}:
        return ""
    return (
        "\n\nEstrategia deste turno: como a intencao predominante nao exige fato factual autorizado, "
        "priorize descoberta comercial e qualificacao. Reconheca o contexto do paciente, avance a conversa "
        "com uma pergunta comercial natural e evite iniciar por explicacao tecnica ou enciclopedica."
    )


def _deterministic_respond_only_response(
    query: str,
    commercial_state: dict[str, Any],
    *,
    organization_config: OrganizationCommercialConfig,
) -> str | None:
    if commercial_state.get("next_best_action") != "RESPOND_ONLY":
        return None
    intent = str(commercial_state.get("current_turn_intent") or "")
    if intent == "GREETING":
        return "Oi! Tudo bem? Como posso te ajudar?"
    if intent == "ACKNOWLEDGEMENT":
        return "Por nada! Fico por aqui se precisar."
    if intent == "IDENTITY_QUERY":
        identity = _current_turn_identity(organization_config)
        return f"Sou {identity}." if identity else "Sou do atendimento."
    if intent == "SMALL_TALK":
        return "Tudo bem por aqui. Como posso te ajudar?"
    if intent == "CORRECTION":
        return "Certo, obrigado por me corrigir."
    if intent == "OTHER" and commercial_state.get("context_continuity") == "NEW_NEUTRAL_TURN":
        return "Recebi sua mensagem. Como posso te ajudar?"
    return None


def _current_turn_identity(config: OrganizationCommercialConfig) -> str:
    if config.assistant_name and config.doctor_name:
        return f"a {config.assistant_name}, do atendimento do {config.doctor_name}"
    if config.assistant_name and config.clinic_name:
        return f"a {config.assistant_name}, do atendimento da {config.clinic_name}"
    if config.assistant_name and config.assistant_role:
        return f"a {config.assistant_name}, {config.assistant_role}"
    if config.assistant_name:
        return f"a {config.assistant_name}"
    if config.doctor_name:
        return f"do atendimento do {config.doctor_name}"
    if config.clinic_name:
        return f"do atendimento da {config.clinic_name}"
    return ""


def _run_retrieval_with_retry(operation, *, emit) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    retry_started = False
    last_error: LiveRuntimeHttpError | None = None
    for attempt in range(1, RETRIEVAL_MAX_ATTEMPTS + 1):
        try:
            result = operation()
        except LiveRuntimeHttpError as exc:
            if not _is_retryable_retrieval_error(exc):
                raise
            last_error = exc
            if attempt >= RETRIEVAL_MAX_ATTEMPTS:
                emit(
                    "retrieval_retry_exhausted",
                    {
                        "provider": exc.provider,
                        "attempts": attempt,
                        "status": exc.status,
                        "code": exc.code,
                        "endpoint": exc.endpoint,
                    },
                )
                raise
            if not retry_started:
                retry_started = True
                emit(
                    "retrieval_retry_started",
                    {
                        "provider": exc.provider,
                        "maxAttempts": RETRIEVAL_MAX_ATTEMPTS,
                        "retryableErrors": ["connection_reset", "timeout", "temporary_connection_error", "http_429", "http_5xx"],
                    },
                )
            emit(
                "retrieval_retry_attempt",
                {
                    "provider": exc.provider,
                    "attempt": attempt + 1,
                    "previousStatus": exc.status,
                    "previousCode": exc.code,
                    "endpoint": exc.endpoint,
                },
            )
            time.sleep(RETRIEVAL_BACKOFF_SECONDS[min(attempt - 1, len(RETRIEVAL_BACKOFF_SECONDS) - 1)])
            continue
        if retry_started:
            emit("retrieval_retry_succeeded", {"provider": "supabase", "attempt": attempt})
        return result
    if last_error:
        raise last_error
    return [], None


def _is_retryable_retrieval_error(exc: LiveRuntimeHttpError) -> bool:
    if exc.provider != "supabase":
        return False
    if exc.status == 429:
        return True
    if exc.status is not None:
        return 500 <= exc.status <= 599
    text = _normalize_text(json.dumps(exc.body, ensure_ascii=False) if not isinstance(exc.body, str) else exc.body)
    code = _normalize_text(exc.code or "")
    retryable_markers = (
        "urlerror",
        "timeouterror",
        "timeout",
        "timed out",
        "connectionreseterror",
        "connection reset",
        "connection reset by peer",
        "temporary failure",
        "temporarily unavailable",
        "network is unreachable",
        "remote end closed connection",
    )
    return any(marker in text or marker in code for marker in retryable_markers)


def _turn_evidence_requirement(
    query: str,
    commercial_state: dict[str, Any] | None,
    *,
    history_text: str = "",
    previous_assistant_question: str = "",
    stage: str = "QUALIFICATION",
) -> dict[str, Any]:
    initial = _classify_turn_context(
        query,
        [],
        history_text=history_text,
        previous_assistant_question=previous_assistant_question,
        stage=stage,
    )
    current_turn_intent = str((commercial_state or {}).get("current_turn_intent") or "")
    context_continuity = str((commercial_state or {}).get("context_continuity") or "")
    if _is_operational_scheduling_data(query, commercial_state):
        return {
            **initial,
            "requires_retrieval": False,
            "requires_evidence": False,
            "reason": "OPERATIONAL_NO_RAG" if _is_registration_data_turn(query, commercial_state) else "OPERATIONAL_SCHEDULING_DATA",
        }
    if current_turn_intent in {"GREETING", "IDENTITY_QUERY", "ACKNOWLEDGEMENT", "SMALL_TALK", "CORRECTION"} or (
        current_turn_intent == "OTHER" and context_continuity == "NEW_NEUTRAL_TURN"
    ):
        return {
            **initial,
            "interpreted_intent": current_turn_intent,
            "requires_retrieval": False,
            "requires_evidence": False,
            "reason": "CURRENT_TURN_RESPOND_ONLY",
        }
    if initial["interpreted_intent"] == "CLINICAL_URGENCY":
        return {
            **initial,
            "requires_retrieval": False,
            "requires_evidence": True,
            "reason": "CLINICAL_HANDOFF_BEFORE_RETRIEVAL",
        }
    if _is_affirmative_appointment_reply(query, previous_assistant_question):
        return {
            **initial,
            "requires_retrieval": False,
            "requires_evidence": False,
            "reason": "OPERATIONAL_SCHEDULING_CONFIRMATION",
        }
    return {
        **initial,
        "requires_retrieval": initial["interpreted_intent"] in {"ATTRIBUTE_QUERY", "FACTUAL_QUERY", "PROCEDURE_INTEREST", "NEED_DISCOVERY"},
        "requires_evidence": initial["requires_evidence"],
        "reason": "FACTUAL_PROCEDURE_OR_CONTEXTUAL_LOOKUP" if initial["interpreted_intent"] in {"ATTRIBUTE_QUERY", "FACTUAL_QUERY", "PROCEDURE_INTEREST", "NEED_DISCOVERY"} else "CONVERSATIONAL_NO_FACTUAL_LOOKUP",
    }


def _is_operational_scheduling_data(query: str, commercial_state: dict[str, Any] | None) -> bool:
    text = _normalize_text(query)
    memory = dict((commercial_state or {}).get("operational_memory") or {})
    if memory.get("appointment_intent") and (_preferred_date_like(text) or _preferred_time_like(text)):
        return True
    if _is_registration_data_turn(query, commercial_state):
        return True
    return False


def _is_registration_data_turn(query: str, commercial_state: dict[str, Any] | None) -> bool:
    if _direct_factual_question_present(query):
        return False
    registration = dict((commercial_state or {}).get("registration_memory") or {})
    missing = list((commercial_state or {}).get("missing_required_fields") or [])
    text = _normalize_text(query)
    has_registration_signal = bool(registration) or bool(re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", str(query or ""), re.IGNORECASE))
    has_registration_signal = has_registration_signal or bool(re.search(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", str(query or "")))
    has_registration_signal = has_registration_signal or any(_contains_term(text, term) for term in ("cpf", "rg", "cep", "endereco", "endereço", "rua", "avenida", "bairro"))
    completion_signal = any(field in missing for field in ("address_number", "address_neighborhood", "address_city", "address_state")) and bool(re.search(r"\d", text)) and "," in str(query or "")
    return bool(has_registration_signal or completion_signal)


def _direct_factual_question_present(query: str) -> bool:
    text = _normalize_text(query)
    if not _is_direct_question(text):
        return False
    factual_terms = ("quanto", "custa", "valor", "preco", "gratuita", "gratis", "pagamento", "parcela", "onde", "horario", "funciona", "procedimento", "tratamento")
    return any(_contains_term(text, term) for term in factual_terms)


def _is_affirmative_appointment_reply(query: str, previous_assistant_question: str = "") -> bool:
    text = _normalize_text(query)
    previous = _normalize_text(previous_assistant_question)
    if not text or not previous:
        return False
    affirmative = {
        "sim",
        "quero",
        "pode",
        "vamos",
        "claro",
        "pode sim",
        "quero sim",
        "vamos sim",
        "isso",
        "isso mesmo",
        "por favor",
    }
    if text not in affirmative and not any(_contains_term(text, term) for term in ("quero agendar", "pode solicitar", "vamos marcar")):
        return False
    appointment_terms = ("solicitar horario", "solicite horario", "solicito horario", "marcar avaliacao", "agendar avaliacao", "horario para sua avaliacao", "horario para avaliacao", "quer agendar", "quer marcar")
    return any(term in previous for term in appointment_terms) or ("horario" in previous and any(term in previous for term in ("avaliacao", "consulta", "agendar", "marcar", "solicitar")))


def _explicit_scheduling_continuation(query: str) -> bool:
    text = _normalize_text(query)
    return any(
        phrase in text
        for phrase in (
            "pode marcar",
            "pode agendar",
            "quero marcar",
            "quero agendar",
            "marca para",
            "agendar para",
            "marcar para",
        )
    )


def _deterministic_scheduling_response(
    query: str,
    commercial_state: dict[str, Any],
    *,
    previous_assistant_question: str,
    organization_config: OrganizationCommercialConfig,
) -> str | None:
    memory = dict(commercial_state.get("operational_memory") or {})
    registration = dict(commercial_state.get("registration_memory") or {})
    missing = list(commercial_state.get("missing_required_fields") or [])
    if _is_registration_data_turn(query, commercial_state):
        if missing:
            return f"Para concluir seu cadastro, falta { _human_missing_fields(missing) }."
        if not memory.get("preferred_location") and len(organization_config.locations) > 1:
            return f"Cadastro recebido. Voce prefere {_human_options(organization_config.locations)}?"
        if not memory.get("preferred_date") or not memory.get("preferred_time"):
            return "Cadastro recebido. Qual dia e horario ficam melhores?"
        return "Cadastro recebido. Vou verificar esse horario para voce."
    if not _is_affirmative_appointment_reply(query, previous_assistant_question) and not _explicit_scheduling_continuation(query):
        return None
    if not memory.get("preferred_location") and len(organization_config.locations) > 1:
        return "Sim. Qual unidade voce prefere?"
    if not memory.get("preferred_date") or not memory.get("preferred_time"):
        return "Sim. Qual dia e horario voce prefere para sua avaliacao?"
    return None


def _human_missing_fields(missing: list[str]) -> str:
    labels = {
        "patient_name": "nome completo",
        "email": "e-mail",
        "cpf": "CPF",
        "rg": "RG",
        "cep": "CEP",
        "address_street": "rua",
        "address_number": "numero",
        "address_neighborhood": "bairro",
        "address_city": "cidade",
        "address_state": "estado",
    }
    names = [labels.get(field, field) for field in missing]
    if not names:
        return "nenhum dado"
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " e " + names[-1]


def _human_options(options: tuple[str, ...]) -> str:
    names = [str(item).strip() for item in options if str(item).strip()]
    if len(names) <= 1:
        return names[0] if names else "a unidade"
    return ", ".join(names[:-1]) + " ou " + names[-1]


def _assistant_introduced_after_response(previous: Any, response_text: str, commercial_state: dict[str, Any]) -> bool:
    if bool(previous):
        return True
    if not str(response_text or "").strip():
        return False
    return bool(commercial_state.get("should_introduce"))


def _updated_answered_facts(
    previous: Any,
    response_text: str,
    *,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    facts = dict(previous or {}) if isinstance(previous, dict) else {}
    text = _normalize_text(response_text)
    if not text:
        return facts
    evidence_version = _evidence_knowledge_version(evidence)
    detected: dict[str, str] = {}
    if any(term in text for term in ("avaliacao e gratuita", "avaliacao gratuita", "consulta e gratuita", "consulta gratuita", "gratis")):
        detected["evaluation_price"] = "free"
    if any(term in text for term in ("valor do procedimento", "valor dos procedimentos", "preco do procedimento", "quanto custa o procedimento")) and any(term in text for term in ("apos avaliacao", "apos a avaliacao", "depois da avaliacao")):
        detected["procedure_price_policy"] = "after_evaluation"
    if "pix" in text or "boleto" in text or "cartao" in text:
        detected["payment_methods"] = "mentioned"
    if any(term in text for term in ("brotas", "hospital da bahia", "matatu", "pituba")):
        detected["clinic_location"] = "mentioned"
    for key, value in detected.items():
        facts[key] = {"value": value, "knowledgeVersion": evidence_version}
    return facts


def _evidence_knowledge_version(evidence: list[dict[str, Any]]) -> str:
    versions = sorted({str(item.get("document_version_id") or "") for item in evidence if item.get("document_version_id")})
    return "|".join(versions) or DATASET_VERSION


def _preferred_date_like(text: str) -> bool:
    return any(_contains_term(text, term) for term in ("hoje", "amanha", "segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"))


def _preferred_time_like(text: str) -> bool:
    return bool(re.search(r"\b([01]?\d|2[0-3])\s*(?::|h)?\s*([0-5]\d)?\b", text))


def _contextual_retrieval_query(
    current_message: str,
    commercial_state: dict[str, Any] | None,
    *,
    history_text: str = "",
    previous_assistant_question: str = "",
) -> str:
    state = dict(commercial_state or {})
    summary = dict(state.get("patient_need_summary") or {})
    parts: list[str] = []
    current = str(current_message or "").strip()
    if current:
        parts.append(current)
    if state.get("context_continuity") == "NEW_NEUTRAL_TURN":
        return _unique_word_query(current) or current
    for key in ("procedure_interest", "situation", "main_objection", "fear_topics", "region_interest", "main_concern", "motivation"):
        value = str(summary.get(key) or "").strip()
        if value:
            parts.append(value.replace(",", " "))
    if state.get("contextual_short_answer_resolved"):
        previous_terms = [
            term
            for term in _retrieval_terms(previous_assistant_question)
            if term in {"procedimento", "recuperacao", "operatorio", "cirurgia", "medo", "receio"}
        ]
        parts.extend(previous_terms)
    if len(_retrieval_terms(" ".join(parts))) <= 1 and history_text:
        parts.extend(_retrieval_terms(history_text)[:4])
    return _unique_word_query(" ".join(parts)) or current


def _unique_word_query(text: str) -> str:
    words: list[str] = []
    for word in re.findall(r"[A-Za-zÀ-ÿ0-9]+", str(text or "")):
        normalized = _normalize_text(word)
        if len(normalized) < 2:
            continue
        if normalized not in {_normalize_text(existing) for existing in words}:
            words.append(word)
    return " ".join(words[:24])


def _dedupe_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = str(item.get("id") or item.get("document_version_id") or item.get("content") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _conversation_evidence_snapshot(
    evidence: list[dict[str, Any]],
    *,
    organization_id: str,
    query: str,
) -> list[dict[str, Any]]:
    scope_terms = _retrieval_terms(query)
    snapshot: list[dict[str, Any]] = []
    for item in evidence[:4]:
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        snapshot.append(
            {
                "id": str(item.get("id") or ""),
                "organization_id": organization_id,
                "document_version_id": str(item.get("document_version_id") or ""),
                "content": content[:1200],
                "scopeTerms": scope_terms,
                "source": "same_conversation_retrieval",
                "datasetVersion": DATASET_VERSION,
            }
        )
    return snapshot


def _reusable_conversation_evidence(
    stored: Any,
    *,
    organization_id: str,
    query: str,
) -> list[dict[str, Any]]:
    if not isinstance(stored, list):
        return []
    query_terms = set(_retrieval_terms(query))
    if not query_terms:
        return []
    reusable: list[dict[str, Any]] = []
    for item in stored[:4]:
        if not isinstance(item, dict):
            continue
        if str(item.get("organization_id") or "") != organization_id:
            continue
        if item.get("datasetVersion") != DATASET_VERSION:
            continue
        content = str(item.get("content") or "")
        scope_terms = set(str(term) for term in item.get("scopeTerms", []) if str(term))
        content_terms = set(_retrieval_terms(content))
        if not (query_terms & scope_terms or query_terms & content_terms):
            continue
        reusable.append(
            {
                "id": str(item.get("id") or ""),
                "organization_id": organization_id,
                "document_version_id": str(item.get("document_version_id") or ""),
                "content": content,
                "reused": True,
            }
        )
    return reusable


def _conversational_no_facts_messages(input_messages: list[dict[str, str]]) -> list[dict[str, str]]:
    retry_instruction = {
        "role": "system",
        "content": (
            "Modo CONVERSATIONAL_NO_FACTS / SALES_ONLY. A tentativa anterior deve ser descartada porque "
            "introduziu claim factual sem suporte. Gere uma nova resposta curta e natural. "
            "Nao forneca qualquer fato sobre clinica, medico, procedimento, preco, resultado, tecnica, "
            "duracao, agenda, disponibilidade, pagamento ou tratamento. Use apenas o contexto fornecido "
            "pelo proprio paciente e pelo historico da conversa. Reconheca o que o paciente disse, continue "
            "descoberta comercial e qualificacao; faca uma unica proxima pergunta comercial natural. Nao mencione falta "
            "de informacao, evidencia, base, documento, RAG, retrieval, grounding, equipe, humano ou handoff. "
            "Nao invente nada."
        ),
    }
    return [input_messages[0], retry_instruction, *input_messages[1:]]


def _safe_like(query: str) -> str:
    return " ".join(query.replace("*", " ").replace("%", " ").split())[:120]


def _retrieval_terms(query: str) -> list[str]:
    normalized = _normalize_text(query)
    stopwords = {
        "sobre",
        "gostaria",
        "saber",
        "mais",
        "quero",
        "queria",
        "oi",
        "ola",
        "tenho",
        "interesse",
        "quanto",
        "custa",
        "valor",
        "preco",
        "por",
        "para",
        "com",
        "uma",
        "uns",
        "das",
        "dos",
        "nas",
        "nos",
        "meu",
        "minha",
        "isso",
        "aquele",
        "aquela",
    }
    terms: list[str] = []
    for term in re.findall(r"[a-z0-9]+", normalized):
        if len(term) < 3 or term in stopwords:
            continue
        if term not in terms:
            terms.append(term)
    return terms[:8]


def _requested_procedure(query: str) -> str | None:
    text = _normalize_text(query)
    known = (
        "transplante capilar",
        "botox capilar",
        "rinoplastia",
        "botox",
        "toxina botulinica",
        "preenchimento labial",
        "preenchimento",
        "blefaroplastia",
        "implante",
        "implantes",
        "protese",
        "proteses",
        "endodontia",
        "ortodontia",
        "periodontia",
        "cirurgia bucomaxilofacial",
        "estetica dental",
        "dentistica",
        "harmonizacao facial",
        "radiografia panoramica",
        "tomografia cone beam",
        "odontologia digital",
        "lente",
        "lentes",
        "lente de contato",
        "lentes de contato",
        "faceta",
        "facetas",
        "resina",
        "ceramica",
        "cerâmica",
    )
    for procedure in known:
        if procedure in text:
            return "Botox" if procedure == "toxina botulinica" else procedure
    return None


def _catalog_procedure_names(catalog_text: str) -> set[str]:
    procedures = set()
    for line in str(catalog_text or "").splitlines():
        item = _normalize_text(line.strip(" -•\t"))
        if item:
            procedures.add(item)
    return procedures


def _classify_turn_context(
    query: str,
    evidence: list[dict[str, Any]],
    *,
    history_text: str = "",
    previous_assistant_question: str = "",
    stage: str = "QUALIFICATION",
) -> dict[str, Any]:
    relation = _turn_relation(query, previous_assistant_question)
    intent = _interpreted_intent(query, history_text=history_text, relation=relation)
    clinical_handoff = _requires_clinical_handoff(query)
    if clinical_handoff:
        intent = "CLINICAL_URGENCY"
    requires_evidence = intent in {"ATTRIBUTE_QUERY", "FACTUAL_QUERY"}
    unsupported_attribute = _unsupported_attribute_question(
        query,
        evidence,
        history_text=history_text,
        relation=relation,
        intent=intent,
    )
    return {
        "turn_relation": relation,
        "interpreted_intent": intent,
        "conversation_stage": stage,
        "requires_evidence": requires_evidence or clinical_handoff,
        "unsupported_attribute_reason": "CLINICAL_URGENCY_OR_SENSITIVE_TOPIC" if clinical_handoff else ("ATTRIBUTE_WITHOUT_AUTHORIZED_EVIDENCE" if unsupported_attribute else None),
        "handoff_decision": "HUMAN_HANDOFF_REQUIRED" if clinical_handoff or unsupported_attribute else "NONE",
    }


def _turn_relation(query: str, previous_assistant_question: str = "") -> str:
    text = _normalize_text(query)
    previous = _normalize_text(previous_assistant_question)
    if not text:
        return "EMPTY"
    if _is_direct_question(text):
        return "NEW_QUESTION"
    if previous and "?" in previous_assistant_question:
        answer_tokens = set(re.findall(r"[a-z0-9]+", text))
        option_tokens = set(re.findall(r"[a-z0-9]+", previous))
        if len(text) <= 80:
            return "ANSWER_TO_PREVIOUS_QUESTION"
        if answer_tokens & option_tokens and _looks_like_patient_description(text):
            return "ANSWER_TO_PREVIOUS_QUESTION"
    if _looks_like_patient_description(text):
        return "PATIENT_DESCRIPTION"
    return "NEW_STATEMENT"


def _interpreted_intent(query: str, *, history_text: str = "", relation: str = "NEW_STATEMENT") -> str:
    text = _normalize_text(query)
    if relation in {"ANSWER_TO_PREVIOUS_QUESTION", "PATIENT_DESCRIPTION"}:
        return "NEED_DISCOVERY"
    if _brand_attribute_terms(text) and (_requested_procedure(text) or _requested_procedure(history_text)):
        return "ATTRIBUTE_QUERY"
    if _attribute_terms(text) and (_requested_procedure(text) or _requested_procedure(history_text)):
        return "ATTRIBUTE_QUERY"
    if _is_direct_question(text):
        return "FACTUAL_QUERY"
    if _requested_procedure(text):
        return "PROCEDURE_INTEREST"
    return "CONVERSATIONAL_RESPONSE"


def _unsupported_attribute_question(
    query: str,
    evidence: list[dict[str, Any]],
    *,
    history_text: str = "",
    relation: str = "NEW_STATEMENT",
    intent: str | None = None,
) -> bool:
    text = _normalize_text(query)
    if relation in {"ANSWER_TO_PREVIOUS_QUESTION", "PATIENT_DESCRIPTION"}:
        return False
    if not _requested_procedure(text) and not _requested_procedure(history_text):
        return False
    attribute_patterns = {
        "marca": ("marca", "fabricante", "laboratorio"),
        "preco": ("preco", "valor", "valores", "custa", "quanto"),
        "parcelamento": ("parcela", "parcelado", "parcelamento", "vezes"),
        "duracao": ("duracao", "dura", "tempo"),
        "preparo": ("preparo", "preparacao", "antes"),
        "recuperacao": ("recuperacao", "repouso", "depois"),
        "risco": ("risco", "contraindicacao", "contraindicacoes"),
        "tecnica": ("tecnica", "técnica", "tipo", "diferenca", "diferença", "resina", "ceramica", "cerâmica"),
    }
    requested = [
        attribute
        for attribute, terms in attribute_patterns.items()
        if any(_contains_term(text, term) for term in terms)
    ]
    if "marca" in requested and not _brand_attribute_terms(text):
        requested.remove("marca")
    if intent and intent not in {"ATTRIBUTE_QUERY", "FACTUAL_QUERY"}:
        return False
    if not requested:
        return False
    evidence_text = _normalize_text("\n".join(str(item.get("content") or "") for item in evidence))
    unsupported = not all(any(_contains_term(evidence_text, term) for term in attribute_patterns[attribute]) for attribute in requested)
    if unsupported and _safe_commercial_gap_bridge_available(query, evidence):
        return False
    return unsupported


def _attribute_terms(text: str) -> bool:
    attribute_terms = (
        "preco",
        "valor",
        "valores",
        "custa",
        "quanto",
        "parcela",
        "parcelado",
        "parcelamento",
        "vezes",
        "duracao",
        "dura",
        "tempo",
        "preparo",
        "preparacao",
        "recuperacao",
        "repouso",
        "depois",
        "risco",
        "contraindicacao",
        "contraindicacoes",
        "gratuita",
        "gratuito",
        "gratis",
        "convênio",
        "convenio",
        "estacionamento",
        "localizacao",
        "localização",
        "endereco",
        "endereço",
        "onde",
        "hospital",
        "matatu",
        "bahia",
        "carga imediata",
    )
    return _brand_attribute_terms(text) or any(_contains_term(text, term) for term in attribute_terms)


def _safe_commercial_gap_bridge_available(query: str, evidence: list[dict[str, Any]]) -> bool:
    text = _normalize_text(query)
    if not any(_contains_term(text, term) for term in ("tipo", "diferenca", "diferença", "tecnica", "técnica", "resina", "ceramica", "cerâmica")):
        return False
    evidence_text = _normalize_text("\n".join(str(item.get("content") or "") for item in evidence))
    if not evidence_text:
        return False
    has_assessment_bridge = any(_contains_term(evidence_text, term) for term in ("avalia", "avaliacao", "avaliação", "planejamento", "personalizado", "personalizados"))
    has_related_interest = _requested_procedure(text) and any(_contains_term(evidence_text, term) for term in ("lente", "lentes", "faceta", "facetas", "estetica", "esteticos", "estética", "estéticos", "dentistica", "dentística", "tratamento", "tratamentos"))
    return bool(has_assessment_bridge and has_related_interest)


def _requires_clinical_handoff(query: str) -> bool:
    text = _normalize_text(query)
    urgent_terms = (
        "dor intensa",
        "muita dor",
        "sangramento",
        "sangrando",
        "inchaco",
        "inchaço",
        "inchado",
        "inchada",
        "trauma",
        "dente quebrado",
        "quebrou o dente",
        "medicacao",
        "medicação",
        "remedio",
        "remédio",
        "pos procedimento",
        "pós procedimento",
        "pos-procedimento",
        "pós-procedimento",
        "rejeicao",
        "rejeição",
        "carga imediata",
        "cirurgia sem corte",
    )
    return any(_contains_term(text, term) and not _is_negated_near(text, term) for term in urgent_terms)


def _is_negated_near(text: str, term: str) -> bool:
    index = text.find(_normalize_text(term))
    if index < 0:
        return False
    prefix = text[max(0, index - 30):index]
    tokens = prefix.split()[-5:]
    return any(token in {"nao", "não", "nem", "sem"} for token in tokens)


def _unclear_procedure_price_query(query: str) -> bool:
    text = _normalize_text(query)
    if not any(marker in text for marker in ("inaudivel", "inaudível", "[inaudivel]", "[inaudível]")):
        return False
    asks_price = any(_contains_term(text, term) for term in ("quanto custa", "valor", "preco", "preço"))
    return asks_price and _requested_procedure(text) is None


def _brand_attribute_terms(text: str) -> bool:
    if not any(_contains_term(text, term) for term in ("marca", "fabricante", "laboratorio")):
        return False
    brand_question_markers = ("qual", "quais", "usa", "usam", "utiliza", "utilizam", "fabricante", "laboratorio")
    return _is_direct_question(text) or any(_contains_term(text, term) for term in brand_question_markers)


def _is_direct_question(text: str) -> bool:
    question_terms = ("qual", "quais", "quanto", "quando", "onde", "quem", "como", "voces", "você", "fazem", "usa", "usam", "tem")
    return "?" in text or any(_contains_term(text, term) for term in question_terms)


def _looks_like_patient_description(text: str) -> bool:
    description_terms = (
        "testa",
        "sobrancelha",
        "sobrancelhas",
        "olhos",
        "rosto",
        "linha",
        "linhas",
        "marca",
        "marcas",
        "marcado",
        "marcadas",
        "visivel",
        "visiveis",
        "repouso",
        "movimenta",
        "incomoda",
        "incomodo",
        "sim",
        "nao",
        "não",
        "quero",
        "pesquisando",
        "breve",
        "anos",
        "meses",
        "dente",
        "perdi",
        "implante",
        "protese",
        "prótese",
        "medo",
    )
    tokens = set(re.findall(r"[a-z0-9]+", text))
    return bool(tokens & set(description_terms))


def _contains_term(text: str, term: str) -> bool:
    normalized_text = _normalize_text(text)
    normalized_term = _normalize_text(term)
    return re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", normalized_text) is not None


def _zapi_store_path() -> Path:
    configured = environ.get("ZAPI_STORE_PATH")
    if configured:
        return Path(configured)
    if environ.get("RENDER") or environ.get("APP_ENV", "").strip().lower() in {"production", "prod"}:
        return DEFAULT_RENDER_STORE_PATH
    return DEFAULT_LOCAL_STORE_PATH


def _build_zapi_store(path: str | Path | None = None) -> JsonFileWhatsAppStore:
    store_path = Path(path) if path is not None else _zapi_store_path()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    if not store_path.exists():
        store_path.write_text("{}", encoding="utf-8")
    return JsonFileWhatsAppStore(store_path)


def _runtime_organization_id(organization_id: str) -> str:
    if organization_id in {LEONARDO_ORG_ID, AURORA_ORG_ID, BOREAL_ORG_ID}:
        return deterministic_sandbox_uuid(organization_id)
    return organization_id


def _organization_commercial_config_from_env() -> OrganizationCommercialConfig:
    return OrganizationCommercialConfig(
        assistant_name=_env_optional("AI_ASSISTANT_NAME"),
        assistant_role=_env_optional("AI_ASSISTANT_ROLE"),
        clinic_name=_env_optional("AI_CLINIC_NAME"),
        doctor_name=_env_optional("AI_DOCTOR_NAME"),
        tone=environ.get("AI_ASSISTANT_TONE", OrganizationCommercialConfig.tone),
        sales_goal=environ.get("AI_SALES_GOAL", OrganizationCommercialConfig.sales_goal),
        primary_conversion_action=environ.get("AI_PRIMARY_CONVERSION_ACTION", OrganizationCommercialConfig.primary_conversion_action),
        max_discovery_depth=int(environ.get("AI_MAX_DISCOVERY_DEPTH", str(OrganizationCommercialConfig.max_discovery_depth))),
        cta_style=environ.get("AI_CTA_STYLE", OrganizationCommercialConfig.cta_style),
        appointment_flow=environ.get("AI_APPOINTMENT_FLOW", OrganizationCommercialConfig.appointment_flow),
        locations=tuple(item.strip() for item in environ.get("AI_LOCATIONS", "").split("|") if item.strip()),
        business_hours=_env_optional("AI_BUSINESS_HOURS"),
    )


def _env_optional(name: str) -> str | None:
    value = environ.get(name, "").strip()
    return value or None


def validate_live_grounding(
    response_text: str,
    *,
    evidence_count: int,
    evidence: list[dict[str, Any]] | None = None,
    organization_config: OrganizationCommercialConfig | None = None,
    commercial_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    internal_gap_terms = _internal_gap_terms_in_response(response_text)
    stale_free_evaluation_ambiguity = _stale_free_evaluation_ambiguity(response_text, evidence or [])
    commercial_policy_violation = _commercial_policy_violation(response_text, commercial_state)
    requires_evidence = _response_requires_authorized_evidence(response_text)
    config_authorized = False
    if evidence_count == 0 and organization_config:
        config_authorized = _organization_config_authorizes_response(response_text, organization_config)
    passed = (
        not internal_gap_terms
        and not stale_free_evaluation_ambiguity
        and not commercial_policy_violation
        and (evidence_count > 0 or not requires_evidence or config_authorized)
    )
    reason = None
    if internal_gap_terms:
        reason = "INTERNAL_KNOWLEDGE_GAP_EXPOSED"
    elif stale_free_evaluation_ambiguity:
        reason = "STALE_FREE_EVALUATION_AMBIGUITY"
    elif commercial_policy_violation:
        reason = commercial_policy_violation
    elif not passed:
        reason = "UNSUPPORTED_FACTUAL_CLAIM"
    return {
        "passed": passed,
        "mode": (
            "RESPONSE_CONSTRAINED_BY_AUTHORIZED_EVIDENCE"
            if passed and not config_authorized
            else "RESPONSE_CONSTRAINED_BY_AUTHORIZED_CONFIG"
            if passed
            else "HUMAN_HANDOFF_REQUIRED"
        ),
        "evidenceCount": evidence_count,
        "requiresEvidence": requires_evidence,
        "configAuthorized": config_authorized,
        "internalGapTerms": sorted(internal_gap_terms),
        "staleFreeEvaluationAmbiguity": stale_free_evaluation_ambiguity,
        "commercialPolicyViolation": commercial_policy_violation,
        **({"reason": reason} if reason else {}),
    }


def _response_requires_authorized_evidence(response_text: str) -> bool:
    text = _normalize_text(response_text)
    if not text:
        return False
    factual_subject = re.search(
        r"\b(clinica|medico|medica|doutor|doutora|dr|dra|procedimento|tratamento|transplante|capilar|botox|preenchimento|blefaroplastia|consulta|avaliacao|avaliação|gratuita|gratuito|gratis|preco|valor|agenda|horario|retorno|pagamento|lente|lentes|faceta|facetas|resina|ceramica|cerâmica)\b",
        text,
    )
    factual_assertion = re.search(
        r"\b(e|sao|consiste|funciona|realiza|oferece|inclui|custa|valor|preco|tem|possui|redistribui|remove|trata|corrige|indicado|recomendado|diferenca|diferente)\b",
        text,
    )
    return bool(factual_subject and factual_assertion)


def _stale_free_evaluation_ambiguity(response_text: str, evidence: list[dict[str, Any]]) -> bool:
    text = _normalize_text(response_text)
    if not any(_contains_term(text, term) for term in ("avaliacao", "consulta")):
        return False
    stale_phrases = (
        "precisa confirmar",
        "pode nao ser cobrada",
        "depende do caso",
        "clinica confirma antes",
        "confirmar com a clinica",
        "confirmada pela equipe",
    )
    if not any(phrase in text for phrase in stale_phrases):
        return False
    evidence_text = _normalize_text("\n".join(str(item.get("content") or "") for item in evidence))
    return "avaliacao gratuita" in evidence_text and "busca por procedimento" in evidence_text


def _organization_config_authorizes_response(response_text: str, config: OrganizationCommercialConfig) -> bool:
    text = _normalize_text(response_text)
    if not text:
        return False
    # Configuracao organizacional autoriza identidade e dados operacionais
    # explicitamente configurados. Ela nao substitui RAG para procedimento.
    procedure_or_policy_terms = (
        "procedimento",
        "tratamento",
        "implante",
        "implantes",
        "protese",
        "proteses",
        "periodontia",
        "endodontia",
        "ortodontia",
        "botox",
        "preenchimento",
        "blefaroplastia",
        "lente",
        "lentes",
        "faceta",
        "facetas",
        "resina",
        "ceramica",
        "preco",
        "valor",
        "custa",
        "pagamento",
        "parcelamento",
        "resultado",
        "tecnica",
        "diagnostico",
    )
    if any(_contains_term(text, term) for term in procedure_or_policy_terms):
        return False
    allowed_values = [
        config.assistant_name,
        config.assistant_role,
        config.clinic_name,
        config.doctor_name,
        config.business_hours,
        *config.locations,
    ]
    allowed_tokens: set[str] = set()
    for value in allowed_values:
        if not value:
            continue
        allowed_tokens.update(re.findall(r"[a-z0-9]+", _normalize_text(value)))
    meaningful_allowed = {token for token in allowed_tokens if len(token) >= 3}
    if not meaningful_allowed:
        return False
    factual_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", text)
        if token
        in {
            "bruna",
            "atendimento",
            "clinica",
            "carvalho",
            "tavares",
            "leonardo",
            "doutor",
            "doutora",
            "dr",
            "dra",
            "hospital",
            "bahia",
            "matatu",
            "brotas",
            "salvador",
            "pituba",
            "horario",
            "horarios",
            "segunda",
            "sexta",
            "sabado",
        }
    }
    return bool(factual_tokens) and factual_tokens.issubset(
        meaningful_allowed | {"doutor", "doutora", "dr", "dra", "clinica", "atendimento", "horario", "horarios"}
    )


def _internal_gap_terms_in_response(response_text: str) -> set[str]:
    text = _normalize_text(response_text)
    patterns = (
        "nao consigo confirmar",
        "nao tenho essa informacao",
        "nao encontrei",
        "minha base",
        "base de conhecimento",
        "nao consigo afirmar",
        "nao tenho acesso",
        "segundo os dados disponiveis",
        "falta de evidencia",
        "rag",
        "retrieval",
        "grounding",
        "score",
        "a equipe pode verificar",
    )
    return {pattern for pattern in patterns if pattern in text}


def _commercial_policy_violation(response_text: str, commercial_state: dict[str, Any] | None) -> str | None:
    if not commercial_state:
        return None
    text = _normalize_text(response_text)
    memory = dict(commercial_state.get("operational_memory") or {})
    if memory.get("patient_phone") and any(
        phrase in text
        for phrase in (
            "qual seu whatsapp",
            "qual e seu whatsapp",
            "qual o seu whatsapp",
            "numero devo cadastrar",
            "numero de whatsapp",
            "seu telefone",
        )
    ):
        return "REDUNDANT_PHONE_REQUEST"
    if memory.get("preferred_time") and any(
        phrase in text
        for phrase in (
            "manha ou tarde",
            "qual periodo",
            "que periodo",
            "qual horario voce prefere",
            "que horario voce prefere",
        )
    ):
        return "REPEATED_KNOWN_OPERATIONAL_QUESTION"
    if memory.get("preferred_location") and any(phrase in text for phrase in ("qual unidade", "qual local", "onde voce prefere")):
        return "REPEATED_KNOWN_OPERATIONAL_QUESTION"
    scheduling_state = str(commercial_state.get("scheduling_state") or "NONE")
    if scheduling_state != "BOOKED" and any(
        phrase in text
        for phrase in (
            "ficou agendado",
            "esta agendado",
            "está agendado",
            "ficou marcado",
            "esta marcado",
            "está marcado",
            "registrei sua avaliacao",
            "registrei sua avaliação",
            "confirmado seu horario",
            "confirmado seu horário",
        )
    ):
        return "PREMATURE_BOOKING_CONFIRMATION"
    correction_state = dict(commercial_state.get("correction_state") or {})
    if correction_state and correction_state.get("acknowledge_once") is False and any(phrase in text for phrase in ("corrigindo", "corrigido")):
        return "CORRECTION_REPETITION"
    return None


def _normalize_text(value: str) -> str:
    replacements = str.maketrans({"é": "e", "É": "e", "ã": "a", "Ã": "a", "ç": "c", "Ç": "c", "á": "a", "Á": "a", "í": "i", "Í": "i", "ó": "o", "Ó": "o", "ú": "u", "Ú": "u", "ê": "e", "Ê": "e", "ô": "o", "Ô": "o"})
    return response_spaces(str(value).translate(replacements).lower())


def response_spaces(value: str) -> str:
    return " ".join(value.split())


def _provider_exception(exc: Exception, *, stage: str, provider: str, endpoint: str) -> LiveRuntimeHttpError:
    if isinstance(exc, LiveRuntimeHttpError):
        return exc
    if isinstance(exc, error.HTTPError):
        body_text = exc.read().decode("utf-8", "replace")[:2000]
        body = _parse_provider_body(body_text)
        return LiveRuntimeHttpError(
            stage=stage,
            provider=provider,
            status=exc.code,
            endpoint=endpoint,
            body=body,
            code=body.get("code") if isinstance(body, dict) else None,
        )
    if isinstance(exc, error.URLError):
        reason = getattr(exc, "reason", None)
        code = type(reason).__name__ if reason is not None else type(exc).__name__
        return LiveRuntimeHttpError(stage=stage, provider=provider, status=None, endpoint=endpoint, body={"message": str(exc)}, code=code)
    if isinstance(exc, (TimeoutError, socket.timeout, ConnectionError, ConnectionResetError)):
        return LiveRuntimeHttpError(stage=stage, provider=provider, status=None, endpoint=endpoint, body={"message": str(exc)}, code=type(exc).__name__)
    return LiveRuntimeHttpError(stage=stage, provider=provider, status=None, endpoint=endpoint, body={"message": str(exc)}, code=type(exc).__name__)


def _parse_provider_body(body_text: str) -> Any:
    try:
        return json.loads(body_text)
    except Exception:
        return {"message": body_text}


def _safe_provider_body(body: Any) -> Any:
    if body is None:
        return None
    safe = _safe(body)
    if isinstance(safe, dict):
        return {key: value for key, value in safe.items() if str(key).lower() not in {"apikey", "authorization"}}
    return safe


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if "token" in lowered or "secret" in lowered or "key" in lowered or "authorization" in lowered:
                safe[key] = "[REDACTED_SECRET]"
            else:
                safe[key] = _safe(item)
        return safe
    if isinstance(value, list):
        return [_safe(item) for item in value]
    return value


if __name__ == "__main__":
    run_server()
