from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.state import AgentDecision, AgentState

from .channel import (
    ChannelDecision,
    ChannelRecord,
    InMemoryWhatsAppStore,
    InboundMessage,
    MediaReference,
    OutboundMessage,
    WhatsAppMessageType,
    WhatsAppProvider,
)
from .media import MediaDecision, MediaProcessor


DEFAULT_HANDOFF_MESSAGE = "Vou encaminhar isso para nossa equipe para conseguirem te orientar corretamente."
DEFAULT_ACK_MESSAGE = "Certo, vou seguir com seu atendimento."


class WhatsAppRuntimeError(RuntimeError):
    pass


class OrganizationResolver:
    def __init__(self, provider_accounts: dict[str, str]):
        self.provider_accounts = dict(provider_accounts)

    def resolve(self, provider_account_id: str) -> str:
        if provider_account_id not in self.provider_accounts:
            raise ValueError("UNKNOWN_PROVIDER_ACCOUNT")
        return self.provider_accounts[provider_account_id]


class WhatsAppChannelAdapter:
    channel_name = "whatsapp"

    def __init__(
        self,
        *,
        provider: WhatsAppProvider,
        store: InMemoryWhatsAppStore,
        organization_resolver: OrganizationResolver,
        runtime_graph: AgentRuntimeGraph | None = None,
        media_processor: MediaProcessor | None = None,
        handoff_message: str = DEFAULT_HANDOFF_MESSAGE,
        allow_placeholder_ack: bool = True,
        reject_out_of_order: bool = False,
        inbound_enabled: bool = True,
        stage_logger: Any | None = None,
    ):
        self.provider = provider
        self.store = store
        self.organization_resolver = organization_resolver
        self.runtime_graph = runtime_graph or AgentRuntimeGraph()
        self.media_processor = media_processor
        self.handoff_message = handoff_message
        self.allow_placeholder_ack = allow_placeholder_ack
        self.reject_out_of_order = reject_out_of_order
        self.inbound_enabled = inbound_enabled
        self.stage_logger = stage_logger
        self.runtime_calls = 0
        self._runtime_invocation_sequence = 0

    def process_event(self, raw_event: dict[str, Any]) -> ChannelRecord:
        self._log("webhook_received", {"providerAccountId": raw_event.get("providerAccountId"), "providerMessageId": raw_event.get("providerMessageId")})
        self._log("inbound_received", {"providerAccountId": raw_event.get("providerAccountId"), "providerMessageId": raw_event.get("providerMessageId"), "fromSelf": bool(raw_event.get("fromSelf"))})
        provider_message_key = _provider_message_key(raw_event)
        if self.store.has_processed(provider_message_key):
            original = self.store.records_by_provider_message_id[provider_message_key]
            self._log("duplicate_detected", {"providerMessageId": raw_event["providerMessageId"], "conversationId": original.inbound.conversation_id})
            return ChannelRecord(
                inbound=original.inbound,
                decision=ChannelDecision.DUPLICATE_SUPPRESSED,
                agent_decision=original.agent_decision,
                handoff_context=original.handoff_context,
                transcript=original.transcript,
                extracted_text=original.extracted_text,
                metrics={"duplicate": True},
            )

        inbound = self.normalize_event(raw_event)
        self._log("message_normalized", {"messageType": inbound.type.value, "providerMessageId": inbound.provider_message_id})
        if raw_event.get("fromSelf"):
            self._log("self_message_ignored", {"providerMessageId": inbound.provider_message_id, "conversationId": inbound.conversation_id})
            record = ChannelRecord(inbound=inbound, decision=ChannelDecision.SELF_MESSAGE_IGNORED)
            return self.store.record(record)
        if self.reject_out_of_order and self.store.is_out_of_order(inbound):
            self._log("ordering_rejected", {"providerMessageId": inbound.provider_message_id, "conversationId": inbound.conversation_id, "timestamp": inbound.timestamp})
            record = ChannelRecord(inbound=inbound, decision=ChannelDecision.ORDERING_REJECTED)
            return self.store.record(record)
        if not self.inbound_enabled:
            self._log("ai_inbound_disabled", {"providerMessageId": inbound.provider_message_id, "conversationId": inbound.conversation_id})
            record = ChannelRecord(
                inbound=inbound,
                decision=ChannelDecision.INBOUND_DISABLED,
                metrics={"aiInboundDisabled": True, "suppressOutbound": True, "runtimeCalls": 0},
            )
            return self.store.record(record)
        if self.store.is_handoff_active(inbound.conversation_id):
            return self._handoff(
                inbound,
                reason="ACTIVE_HUMAN_HANDOFF",
                transcript=None,
                extracted_text=None,
            )

        self.provider.mark_as_read(organization_id=inbound.organization_id, provider_message_id=inbound.provider_message_id)
        if inbound.type == WhatsAppMessageType.TEXT:
            return self._run_text(inbound, inbound.operational_text(), transcript=None, extracted_text=None)
        return self._run_media(inbound)

    def normalize_event(self, raw_event: dict[str, Any]) -> InboundMessage:
        provider_account_id = str(raw_event["providerAccountId"])
        organization_id = self.organization_resolver.resolve(provider_account_id)
        self._log("organization_resolved", {"providerAccountId": provider_account_id, "organizationId": organization_id})
        metadata = dict(raw_event.get("metadata", {}))
        raw_contact_external_id = str(raw_event["contactExternalId"])
        aliases = [str(item) for item in metadata.get("contactAliases", []) if item]
        preferred_contact_external_id = str(metadata.get("canonicalContactExternalId") or raw_contact_external_id)
        self._log(
            "contact_identifiers_extracted",
            {
                "providerAccountId": provider_account_id,
                "identifierCount": len({raw_contact_external_id, preferred_contact_external_id, *aliases} - {""}),
                "identifierTypes": _contact_identifier_types([raw_contact_external_id, preferred_contact_external_id, *aliases]),
            },
        )
        contact_external_id, persisted_aliases = self.store.resolve_contact_alias(
            provider_account_id=provider_account_id,
            preferred_contact_external_id=preferred_contact_external_id,
            aliases=aliases,
        )
        contact_ref = _contact_ref(provider_account_id, contact_external_id)
        self._log("contact_alias_resolved", {"providerAccountId": provider_account_id, "canonicalContactRef": contact_ref, "aliasCount": len(aliases)})
        self._log("canonical_contact_resolved", {"providerAccountId": provider_account_id, "canonicalContactRef": contact_ref})
        if persisted_aliases:
            self._log("contact_alias_persisted", {"providerAccountId": provider_account_id, "canonicalContactRef": contact_ref, "persistedAliasCount": len(persisted_aliases)})
        conversation_id = self.store.conversation_id_for(
            organization_id=organization_id,
            channel=self.channel_name,
            contact_external_id=contact_external_id,
        )
        self._log("conversation_resolved", {"conversationId": conversation_id, "contactExternalId": contact_external_id})
        message_type = WhatsAppMessageType(str(raw_event["type"]).upper())
        media_reference = None
        if raw_event.get("media"):
            media = raw_event["media"]
            media_reference = MediaReference(
                provider_media_id=str(media.get("providerMediaId", "")),
                url=media.get("url"),
                storage_reference=media.get("storageReference"),
                sha256=media.get("sha256"),
                size_bytes=media.get("sizeBytes"),
                metadata=dict(media.get("metadata", {})),
            )
        return InboundMessage(
            id=str(uuid5(NAMESPACE_URL, f"whatsapp:{organization_id}:{raw_event['providerMessageId']}")),
            provider_message_id=str(raw_event["providerMessageId"]),
            organization_id=organization_id,
            conversation_id=conversation_id,
            contact_external_id=contact_external_id,
            type=message_type,
            text=raw_event.get("text"),
            media_reference=media_reference,
            mime_type=raw_event.get("mimeType"),
            file_name=raw_event.get("fileName"),
            timestamp=str(raw_event.get("timestamp") or ""),
            metadata={
                "providerAccountId": provider_account_id,
                "providerMessageKey": _provider_message_key(raw_event),
                "rawOrganizationIgnored": raw_event.get("organizationId"),
                "rawContactExternalId": raw_contact_external_id,
                "canonicalContactExternalId": contact_external_id,
                **metadata,
            },
        )

    def _run_media(self, inbound: InboundMessage) -> ChannelRecord:
        if inbound.metadata.get("mediaAlreadyProcessed") and inbound.operational_text():
            return self._run_text(
                inbound,
                inbound.operational_text(),
                transcript=inbound.metadata.get("transcript"),
                extracted_text=inbound.metadata.get("extractedText"),
            )
        if self.media_processor is None or inbound.media_reference is None:
            return self._handoff(inbound, reason="MEDIA_PROCESSOR_UNAVAILABLE", transcript=None, extracted_text=None)
        media_result = self.media_processor.process(
            organization_id=inbound.organization_id,
            message_type=inbound.type,
            media_reference=inbound.media_reference,
            mime_type=inbound.mime_type,
            file_name=inbound.file_name,
            metadata={**inbound.media_reference.metadata, **inbound.metadata},
        )
        if media_result.decision == MediaDecision.MEDIA_RETRY_REQUIRED:
            text = media_result.retry_message or "Nao consegui entender bem esse arquivo. Pode me enviar novamente?"
            outbound = self._send_text(inbound, text, metadata={"mediaDecision": media_result.decision.value})
            record = ChannelRecord(
                inbound=inbound,
                decision=ChannelDecision.MEDIA_RETRY_REQUIRED,
                outbound=outbound,
                transcript=media_result.transcript,
                extracted_text=media_result.extracted_text,
                metrics={"mediaRetry": True},
            )
            return self.store.record(record)
        if media_result.decision == MediaDecision.HUMAN_HANDOFF_REQUIRED:
            return self._handoff(
                inbound,
                reason=media_result.handoff_reason or "MEDIA_REQUIRES_HUMAN_REVIEW",
                transcript=media_result.transcript,
                extracted_text=media_result.extracted_text,
            )
        understood = replace(inbound, text=media_result.operational_text)
        return self._run_text(understood, media_result.operational_text or "", transcript=media_result.transcript, extracted_text=media_result.extracted_text)

    def _run_text(self, inbound: InboundMessage, text: str, *, transcript: str | None, extracted_text: str | None) -> ChannelRecord:
        history = self.store.history_for(inbound.conversation_id)
        last_outbound = self.store.last_outbound_for(inbound.conversation_id)
        self._log("conversation_history_loaded", {"conversationId": inbound.conversation_id, "historyTurnCount": len(history)})
        self._log("history_turn_count", {"conversationId": inbound.conversation_id, "count": len(history)})
        self._runtime_invocation_sequence += 1
        runtime_invocation_id = str(uuid5(NAMESPACE_URL, f"runtime:{inbound.organization_id}:{inbound.provider_message_id}:{self._runtime_invocation_sequence}"))
        runtime_context = {
            "channel": self.channel_name,
            "mediaReference": _media_context(inbound),
            "runtimeInvocationId": runtime_invocation_id,
            "currentMessageMetadata": dict(inbound.metadata),
            "currentMessageAt": inbound.timestamp,
            "channelContactExternalId": inbound.contact_external_id,
        }
        if last_outbound and last_outbound.text:
            runtime_context["previousAssistantQuestion"] = last_outbound.text
            runtime_context["previousAssistantMessageAt"] = last_outbound.timestamp
        if last_outbound and last_outbound.metadata.get("conversationEvidence"):
            runtime_context["conversationEvidence"] = last_outbound.metadata["conversationEvidence"]
        runtime_context["assistantIntroduced"] = bool(last_outbound.metadata.get("assistantIntroduced")) if last_outbound and "assistantIntroduced" in last_outbound.metadata else False
        if last_outbound and isinstance(last_outbound.metadata.get("answeredFacts"), dict):
            runtime_context["answeredFacts"] = dict(last_outbound.metadata["answeredFacts"])
        state = AgentState(
            conversation_id=inbound.conversation_id,
            organization_id=inbound.organization_id,
            current_message=text,
            messages=[{"direction": "inbound", "text": item.operational_text(), "type": item.type.value, "metadata": dict(item.metadata)} for item in history],
            context=runtime_context,
        )
        self.runtime_calls += 1
        self._log("runtime_invocation_id", {"runtimeInvocationId": runtime_invocation_id, "providerMessageId": inbound.provider_message_id})
        try:
            result = self.runtime_graph.run(state)
        except Exception as exc:
            self._log("runtime_failed", {"stage": "runtime", "errorType": exc.__class__.__name__, "error": _sanitize_error(str(exc))})
            raise WhatsAppRuntimeError(_sanitize_error(str(exc))) from exc
        if result.decision == AgentDecision.HUMAN_HANDOFF_REQUIRED:
            return self._handoff(inbound, reason=result.handoff_context.get("reason", "HUMAN_HANDOFF_REQUIRED") if result.handoff_context else "HUMAN_HANDOFF_REQUIRED", transcript=transcript, extracted_text=extracted_text, state=result)
        response_text = (result.response_text or "").strip()
        if not response_text:
            if not self.allow_placeholder_ack:
                self._log("runtime_failed", {"stage": "response_generation", "error": "RUNTIME_RESPONSE_MISSING"})
                raise WhatsAppRuntimeError("RUNTIME_RESPONSE_MISSING")
            response_text = DEFAULT_ACK_MESSAGE
        outbound_metadata = {"agentDecision": result.decision.value}
        if result.context.get("conversationEvidence"):
            outbound_metadata["conversationEvidence"] = result.context["conversationEvidence"]
        if "assistantIntroduced" in result.context:
            outbound_metadata["assistantIntroduced"] = bool(result.context["assistantIntroduced"])
        elif last_outbound and "assistantIntroduced" in last_outbound.metadata:
            outbound_metadata["assistantIntroduced"] = bool(last_outbound.metadata.get("assistantIntroduced"))
        if isinstance(result.context.get("answeredFacts"), dict):
            outbound_metadata["answeredFacts"] = dict(result.context["answeredFacts"])
        elif last_outbound and isinstance(last_outbound.metadata.get("answeredFacts"), dict):
            outbound_metadata["answeredFacts"] = dict(last_outbound.metadata["answeredFacts"])
        outbound = self._send_text(inbound, response_text, metadata=outbound_metadata)
        record = ChannelRecord(
            inbound=inbound,
            decision=ChannelDecision.PROCESSED,
            outbound=outbound,
            agent_decision=result.decision.value,
            transcript=transcript,
            extracted_text=extracted_text,
            metrics={"runtimeCalls": 1},
        )
        return self.store.record(record)

    def _handoff(
        self,
        inbound: InboundMessage,
        *,
        reason: str,
        transcript: str | None,
        extracted_text: str | None,
        state: AgentState | None = None,
    ) -> ChannelRecord:
        handoff_context = {
            "reason": reason,
            "conversationId": inbound.conversation_id,
            "organizationId": inbound.organization_id,
            "messageType": inbound.type.value,
            "providerMessageId": inbound.provider_message_id,
            "mediaReference": _media_context(inbound),
            "mimeType": inbound.mime_type,
            "fileName": inbound.file_name,
            "transcript": transcript,
            "extractedText": extracted_text,
            "previousMessages": [item.operational_text() for item in self.store.history_for(inbound.conversation_id)],
            "autonomyInterrupted": True,
        }
        if state and state.handoff_context:
            handoff_context["runtimeHandoffContext"] = state.handoff_context
        self._log("human_handoff_required", {"conversationId": inbound.conversation_id, "providerMessageId": inbound.provider_message_id})
        self._log("handoff_reason", {"conversationId": inbound.conversation_id, "reason": reason})
        self._log("outbound_suppressed", {"conversationId": inbound.conversation_id, "suppressOutbound": True})
        record = ChannelRecord(
            inbound=inbound,
            decision=ChannelDecision.HUMAN_HANDOFF_REQUIRED,
            outbound=None,
            agent_decision=AgentDecision.HUMAN_HANDOFF_REQUIRED.value,
            handoff_context=handoff_context,
            transcript=transcript,
            extracted_text=extracted_text,
            metrics={"handoff": True, "suppressOutbound": True},
        )
        return self.store.record(record)

    def _send_text(self, inbound: InboundMessage, text: str, *, metadata: dict[str, Any] | None = None) -> OutboundMessage:
        sent = self.provider.send_text(
            organization_id=inbound.organization_id,
            contact_external_id=inbound.contact_external_id,
            text=text,
            conversation_id=inbound.conversation_id,
        )
        self._log("outbound_sent", {"providerMessageId": sent.get("providerMessageId"), "conversationId": inbound.conversation_id})
        return OutboundMessage(
            id=str(uuid5(NAMESPACE_URL, f"whatsapp:out:{inbound.provider_message_id}:{text}")),
            conversation_id=inbound.conversation_id,
            organization_id=inbound.organization_id,
            text=text,
            provider_message_id=sent.get("providerMessageId"),
            metadata=metadata or {},
        )

    def _log(self, stage: str, details: dict[str, Any] | None = None) -> None:
        if self.stage_logger is not None:
            self.stage_logger(stage, _sanitize_details(details or {}))


def _media_context(inbound: InboundMessage) -> dict[str, Any] | None:
    if inbound.media_reference is None:
        return None
    return {
        "providerMediaId": inbound.media_reference.provider_media_id,
        "storageReference": inbound.media_reference.storage_reference,
        "sha256": inbound.media_reference.sha256,
        "sizeBytes": inbound.media_reference.size_bytes,
    }


def _provider_message_key(raw_event: dict[str, Any]) -> str:
    return f"{raw_event.get('providerAccountId')}:{raw_event.get('providerMessageId')}"


def _sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
    sanitized = {}
    for key, value in details.items():
        lowered = str(key).lower()
        if "token" in lowered or "secret" in lowered or "key" in lowered:
            sanitized[key] = "[REDACTED_SECRET]"
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_details(value)
        else:
            sanitized[key] = value
    return sanitized


def _sanitize_error(text: str) -> str:
    lowered = text.lower()
    if "token" in lowered or "secret" in lowered or "api key" in lowered or "authorization" in lowered:
        return "runtime error"
    return text


def _contact_identifier_types(values: list[str]) -> list[str]:
    types = set()
    for value in values:
        text = str(value or "")
        if not text:
            continue
        if "@lid" in text.lower():
            types.add("lid")
        elif any(char.isdigit() for char in text):
            types.add("phone")
        else:
            types.add("opaque")
    return sorted(types)


def _contact_ref(provider_account_id: str, contact_external_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"whatsapp-contact:{provider_account_id}:{contact_external_id}"))
