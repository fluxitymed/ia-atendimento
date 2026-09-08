from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5


class WhatsAppMessageType(str, Enum):
    TEXT = "TEXT"
    AUDIO = "AUDIO"
    IMAGE = "IMAGE"
    DOCUMENT = "DOCUMENT"


class ChannelDecision(str, Enum):
    PROCESSED = "PROCESSED"
    BATCH_QUEUED = "BATCH_QUEUED"
    INBOUND_DISABLED = "INBOUND_DISABLED"
    DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"
    SELF_MESSAGE_IGNORED = "SELF_MESSAGE_IGNORED"
    ORDERING_REJECTED = "ORDERING_REJECTED"
    MEDIA_RETRY_REQUIRED = "MEDIA_RETRY_REQUIRED"
    HUMAN_HANDOFF_REQUIRED = "HUMAN_HANDOFF_REQUIRED"
    CRM_AUTOMATION_SUPPRESSED = "CRM_AUTOMATION_SUPPRESSED"
    CRM_MONITORING_BLOCKED = "CRM_MONITORING_BLOCKED"


@dataclass(frozen=True)
class MediaReference:
    provider_media_id: str
    url: str | None = None
    storage_reference: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InboundMessage:
    id: str
    provider_message_id: str
    organization_id: str
    conversation_id: str
    contact_external_id: str
    type: WhatsAppMessageType
    text: str | None = None
    media_reference: MediaReference | None = None
    mime_type: str | None = None
    file_name: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def operational_text(self) -> str:
        return self.text or ""


@dataclass(frozen=True)
class OutboundMessage:
    id: str
    conversation_id: str
    organization_id: str
    text: str
    provider_message_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChannelRecord:
    inbound: InboundMessage
    decision: ChannelDecision
    outbound: OutboundMessage | None = None
    agent_decision: str | None = None
    handoff_context: dict[str, Any] | None = None
    transcript: str | None = None
    extracted_text: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


class WhatsAppProvider(ABC):
    @abstractmethod
    def send_text(self, *, organization_id: str, contact_external_id: str, text: str, conversation_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def send_media(self, *, organization_id: str, contact_external_id: str, media: MediaReference, caption: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def download_media(self, *, organization_id: str, media: MediaReference) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def mark_as_read(self, *, organization_id: str, provider_message_id: str) -> dict[str, Any]:
        raise NotImplementedError


class InMemoryWhatsAppStore:
    def __init__(self):
        self.records_by_provider_message_id: dict[str, ChannelRecord] = {}
        self.reserved_provider_message_ids: set[str] = set()
        self.contact_aliases: dict[tuple[str, str], str] = {}
        self.conversation_ids: dict[tuple[str, str, str], str] = {}
        self.messages_by_conversation: dict[str, list[InboundMessage]] = {}
        self.outbound_messages: list[OutboundMessage] = []
        self.last_order_by_conversation: dict[str, tuple[int, str]] = {}
        self.handoff_conversations: dict[str, dict[str, Any]] = {}

    def conversation_id_for(self, *, organization_id: str, channel: str, contact_external_id: str) -> str:
        key = (organization_id, channel, contact_external_id)
        if key not in self.conversation_ids:
            self.conversation_ids[key] = str(uuid5(NAMESPACE_URL, ":".join(key)))
        return self.conversation_ids[key]

    def has_processed(self, provider_message_id: str) -> bool:
        return provider_message_id in self.records_by_provider_message_id

    def has_seen_provider_message_key(self, provider_message_id: str) -> bool:
        return provider_message_id in self.records_by_provider_message_id or provider_message_id in self.reserved_provider_message_ids

    def reserve_provider_message_key(self, provider_message_id: str) -> bool:
        if self.has_seen_provider_message_key(provider_message_id):
            return False
        self.reserved_provider_message_ids.add(provider_message_id)
        return True

    def release_provider_message_key(self, provider_message_id: str) -> None:
        self.reserved_provider_message_ids.discard(provider_message_id)

    def resolve_contact_alias(
        self,
        *,
        provider_account_id: str,
        preferred_contact_external_id: str,
        aliases: list[str] | tuple[str, ...],
    ) -> tuple[str, list[str]]:
        candidates = _unique_non_empty([preferred_contact_external_id, *aliases])
        if not candidates:
            return preferred_contact_external_id, []
        known = {
            self.contact_aliases[(provider_account_id, candidate)]
            for candidate in candidates
            if (provider_account_id, candidate) in self.contact_aliases
        }
        if len(known) > 1:
            raise ValueError("CONTACT_ALIAS_CONFLICT")
        canonical = next(iter(known), preferred_contact_external_id or candidates[0])
        persisted: list[str] = []
        for candidate in candidates:
            key = (provider_account_id, candidate)
            if key not in self.contact_aliases:
                self.contact_aliases[key] = canonical
                persisted.append(candidate)
        return canonical, persisted

    def record(self, record: ChannelRecord) -> ChannelRecord:
        provider_message_key = record.inbound.metadata.get("providerMessageKey") or record.inbound.provider_message_id
        self.records_by_provider_message_id[str(provider_message_key)] = record
        self.reserved_provider_message_ids.add(str(provider_message_key))
        for batch_key in record.inbound.metadata.get("batchProviderMessageKeys", ()):
            self.records_by_provider_message_id[str(batch_key)] = record
            self.reserved_provider_message_ids.add(str(batch_key))
        if record.decision not in {ChannelDecision.SELF_MESSAGE_IGNORED, ChannelDecision.ORDERING_REJECTED}:
            self.messages_by_conversation.setdefault(record.inbound.conversation_id, []).append(record.inbound)
            order_key = _message_order_key(record.inbound.timestamp)
            if order_key is not None:
                self.last_order_by_conversation[record.inbound.conversation_id] = (order_key, record.inbound.provider_message_id)
        if record.outbound is not None:
            self.outbound_messages.append(record.outbound)
        if record.decision == ChannelDecision.HUMAN_HANDOFF_REQUIRED:
            self.handoff_conversations[record.inbound.conversation_id] = {
                "reason": (record.handoff_context or {}).get("reason", "HUMAN_HANDOFF_REQUIRED"),
                "organizationId": record.inbound.organization_id,
                "providerMessageId": record.inbound.provider_message_id,
            }
        return record

    def history_for(self, conversation_id: str) -> list[InboundMessage]:
        return list(self.messages_by_conversation.get(conversation_id, ()))

    def last_outbound_for(self, conversation_id: str) -> OutboundMessage | None:
        for outbound in reversed(self.outbound_messages):
            if outbound.conversation_id == conversation_id:
                return outbound
        return None

    def is_handoff_active(self, conversation_id: str) -> bool:
        return conversation_id in self.handoff_conversations

    def release_handoff(self, conversation_id: str) -> None:
        self.handoff_conversations.pop(conversation_id, None)

    def is_out_of_order(self, inbound: InboundMessage) -> bool:
        order_key = _message_order_key(inbound.timestamp)
        if order_key is None:
            return False
        previous = self.last_order_by_conversation.get(inbound.conversation_id)
        if previous is None:
            return False
        return order_key < previous[0]

    def metrics(self) -> dict[str, int]:
        inbound = list(self.records_by_provider_message_id.values())
        return {
            "inboundMessages": len(inbound),
            "outboundMessages": len(self.outbound_messages),
            "textCount": sum(1 for record in inbound if record.inbound.type == WhatsAppMessageType.TEXT),
            "audioCount": sum(1 for record in inbound if record.inbound.type == WhatsAppMessageType.AUDIO),
            "imageCount": sum(1 for record in inbound if record.inbound.type == WhatsAppMessageType.IMAGE),
            "documentCount": sum(1 for record in inbound if record.inbound.type == WhatsAppMessageType.DOCUMENT),
            "duplicateSuppression": sum(1 for record in inbound if record.decision == ChannelDecision.DUPLICATE_SUPPRESSED),
            "mediaRetry": sum(1 for record in inbound if record.decision == ChannelDecision.MEDIA_RETRY_REQUIRED),
            "handoff": sum(1 for record in inbound if record.decision == ChannelDecision.HUMAN_HANDOFF_REQUIRED),
        }


class JsonFileWhatsAppStore(InMemoryWhatsAppStore):
    def __init__(self, path: str | Path):
        self.path = Path(path)
        super().__init__()
        self._load()

    def conversation_id_for(self, *, organization_id: str, channel: str, contact_external_id: str) -> str:
        before = len(self.conversation_ids)
        conversation_id = super().conversation_id_for(
            organization_id=organization_id,
            channel=channel,
            contact_external_id=contact_external_id,
        )
        if len(self.conversation_ids) != before:
            self._save()
        return conversation_id

    def record(self, record: ChannelRecord) -> ChannelRecord:
        saved = super().record(record)
        self._save()
        return saved

    def reserve_provider_message_key(self, provider_message_id: str) -> bool:
        reserved = super().reserve_provider_message_key(provider_message_id)
        if reserved:
            self._save()
        return reserved

    def release_provider_message_key(self, provider_message_id: str) -> None:
        before = len(self.reserved_provider_message_ids)
        super().release_provider_message_key(provider_message_id)
        if len(self.reserved_provider_message_ids) != before:
            self._save()

    def resolve_contact_alias(
        self,
        *,
        provider_account_id: str,
        preferred_contact_external_id: str,
        aliases: list[str] | tuple[str, ...],
    ) -> tuple[str, list[str]]:
        before = dict(self.contact_aliases)
        resolved = super().resolve_contact_alias(
            provider_account_id=provider_account_id,
            preferred_contact_external_id=preferred_contact_external_id,
            aliases=aliases,
        )
        if self.contact_aliases != before:
            self._save()
        return resolved

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError):
            return
        self.conversation_ids = {
            (str(item["organization_id"]), str(item["channel"]), str(item["contact_external_id"])): str(item["conversation_id"])
            for item in payload.get("conversation_ids", [])
            if isinstance(item, dict)
            and item.get("organization_id")
            and item.get("channel")
            and item.get("contact_external_id")
            and item.get("conversation_id")
        }
        self.messages_by_conversation = {
            str(conversation_id): [_inbound_from_dict(message) for message in messages if isinstance(message, dict)]
            for conversation_id, messages in (payload.get("messages_by_conversation") or {}).items()
            if isinstance(messages, list)
        }
        self.outbound_messages = [
            _outbound_from_dict(message)
            for message in payload.get("outbound_messages", [])
            if isinstance(message, dict)
        ]
        self.last_order_by_conversation = {
            str(conversation_id): (int(order["order_key"]), str(order["provider_message_id"]))
            for conversation_id, order in (payload.get("last_order_by_conversation") or {}).items()
            if isinstance(order, dict) and order.get("order_key") is not None and order.get("provider_message_id")
        }
        self.records_by_provider_message_id = {
            str(provider_message_id): _record_from_dict(record)
            for provider_message_id, record in (payload.get("records_by_provider_message_id") or {}).items()
            if isinstance(record, dict)
        }
        self.reserved_provider_message_ids = {
            str(provider_message_id)
            for provider_message_id in payload.get("reserved_provider_message_ids", [])
            if provider_message_id
        }
        self.contact_aliases = {
            (str(item["provider_account_id"]), str(item["alias"])): str(item["canonical_contact_external_id"])
            for item in payload.get("contact_aliases", [])
            if isinstance(item, dict)
            and item.get("provider_account_id")
            and item.get("alias")
            and item.get("canonical_contact_external_id")
        }
        self.handoff_conversations = dict(payload.get("handoff_conversations") or {})

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "conversation_ids": [
                {
                    "organization_id": organization_id,
                    "channel": channel,
                    "contact_external_id": contact_external_id,
                    "conversation_id": conversation_id,
                }
                for (organization_id, channel, contact_external_id), conversation_id in sorted(self.conversation_ids.items())
            ],
            "messages_by_conversation": {
                conversation_id: [_inbound_to_dict(message) for message in messages]
                for conversation_id, messages in self.messages_by_conversation.items()
            },
            "outbound_messages": [_outbound_to_dict(message) for message in self.outbound_messages],
            "last_order_by_conversation": {
                conversation_id: {"order_key": order_key, "provider_message_id": provider_message_id}
                for conversation_id, (order_key, provider_message_id) in self.last_order_by_conversation.items()
            },
            "records_by_provider_message_id": {
                provider_message_id: _record_to_dict(record)
                for provider_message_id, record in self.records_by_provider_message_id.items()
            },
            "reserved_provider_message_ids": sorted(self.reserved_provider_message_ids),
            "contact_aliases": [
                {
                    "provider_account_id": provider_account_id,
                    "alias": alias,
                    "canonical_contact_external_id": canonical_contact_external_id,
                }
                for (provider_account_id, alias), canonical_contact_external_id in sorted(self.contact_aliases.items())
            ],
            "handoff_conversations": self.handoff_conversations,
        }
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        tmp_path.replace(self.path)


def _media_to_dict(media: MediaReference | None) -> dict[str, Any] | None:
    if media is None:
        return None
    return {
        "provider_media_id": media.provider_media_id,
        "url": media.url,
        "storage_reference": media.storage_reference,
        "sha256": media.sha256,
        "size_bytes": media.size_bytes,
        "metadata": media.metadata,
    }


def _media_from_dict(payload: dict[str, Any] | None) -> MediaReference | None:
    if not payload:
        return None
    return MediaReference(
        provider_media_id=str(payload.get("provider_media_id") or ""),
        url=payload.get("url"),
        storage_reference=payload.get("storage_reference"),
        sha256=payload.get("sha256"),
        size_bytes=payload.get("size_bytes"),
        metadata=dict(payload.get("metadata") or {}),
    )


def _inbound_to_dict(message: InboundMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "provider_message_id": message.provider_message_id,
        "organization_id": message.organization_id,
        "conversation_id": message.conversation_id,
        "contact_external_id": message.contact_external_id,
        "type": message.type.value,
        "text": message.text,
        "media_reference": _media_to_dict(message.media_reference),
        "mime_type": message.mime_type,
        "file_name": message.file_name,
        "timestamp": message.timestamp,
        "metadata": message.metadata,
    }


def _inbound_from_dict(payload: dict[str, Any]) -> InboundMessage:
    return InboundMessage(
        id=str(payload.get("id") or ""),
        provider_message_id=str(payload.get("provider_message_id") or ""),
        organization_id=str(payload.get("organization_id") or ""),
        conversation_id=str(payload.get("conversation_id") or ""),
        contact_external_id=str(payload.get("contact_external_id") or ""),
        type=WhatsAppMessageType(str(payload.get("type") or WhatsAppMessageType.TEXT.value)),
        text=payload.get("text"),
        media_reference=_media_from_dict(payload.get("media_reference")),
        mime_type=payload.get("mime_type"),
        file_name=payload.get("file_name"),
        timestamp=str(payload.get("timestamp") or datetime.now(timezone.utc).isoformat()),
        metadata=dict(payload.get("metadata") or {}),
    )


def _outbound_to_dict(message: OutboundMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "organization_id": message.organization_id,
        "text": message.text,
        "provider_message_id": message.provider_message_id,
        "timestamp": message.timestamp,
        "metadata": message.metadata,
    }


def _outbound_from_dict(payload: dict[str, Any]) -> OutboundMessage:
    return OutboundMessage(
        id=str(payload.get("id") or ""),
        conversation_id=str(payload.get("conversation_id") or ""),
        organization_id=str(payload.get("organization_id") or ""),
        text=str(payload.get("text") or ""),
        provider_message_id=payload.get("provider_message_id"),
        timestamp=str(payload.get("timestamp") or datetime.now(timezone.utc).isoformat()),
        metadata=dict(payload.get("metadata") or {}),
    )


def _record_to_dict(record: ChannelRecord) -> dict[str, Any]:
    return {
        "inbound": _inbound_to_dict(record.inbound),
        "decision": record.decision.value,
        "outbound": _outbound_to_dict(record.outbound) if record.outbound else None,
        "agent_decision": record.agent_decision,
        "handoff_context": record.handoff_context,
        "transcript": record.transcript,
        "extracted_text": record.extracted_text,
        "metrics": record.metrics,
    }


def _record_from_dict(payload: dict[str, Any]) -> ChannelRecord:
    return ChannelRecord(
        inbound=_inbound_from_dict(dict(payload.get("inbound") or {})),
        decision=ChannelDecision(str(payload.get("decision") or ChannelDecision.PROCESSED.value)),
        outbound=_outbound_from_dict(payload["outbound"]) if isinstance(payload.get("outbound"), dict) else None,
        agent_decision=payload.get("agent_decision"),
        handoff_context=payload.get("handoff_context"),
        transcript=payload.get("transcript"),
        extracted_text=payload.get("extracted_text"),
        metrics=dict(payload.get("metrics") or {}),
    )


def _unique_non_empty(values: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
    return unique


def _message_order_key(timestamp: str) -> int | None:
    if not timestamp:
        return None
    value = str(timestamp).strip()
    if value.isdigit():
        return int(value)
    try:
        normalized = value.replace("Z", "+00:00")
        return int(datetime.fromisoformat(normalized).timestamp() * 1000)
    except ValueError:
        return None


class FakeWhatsAppProvider(WhatsAppProvider):
    def __init__(self, media: dict[str, bytes] | None = None):
        self.media = media or {}
        self.sent_texts: list[dict[str, Any]] = []
        self.sent_media: list[dict[str, Any]] = []
        self.read_messages: list[dict[str, Any]] = []
        self.downloaded_media: list[dict[str, Any]] = []

    def send_text(self, *, organization_id: str, contact_external_id: str, text: str, conversation_id: str) -> dict[str, Any]:
        payload = {
            "providerMessageId": f"fake-out-{len(self.sent_texts) + 1}",
            "organizationId": organization_id,
            "contactExternalId": contact_external_id,
            "conversationId": conversation_id,
            "text": text,
        }
        self.sent_texts.append(payload)
        return payload

    def send_media(self, *, organization_id: str, contact_external_id: str, media: MediaReference, caption: str | None = None) -> dict[str, Any]:
        payload = {
            "providerMessageId": f"fake-media-{len(self.sent_media) + 1}",
            "organizationId": organization_id,
            "contactExternalId": contact_external_id,
            "mediaReference": media.provider_media_id,
            "caption": caption,
        }
        self.sent_media.append(payload)
        return payload

    def download_media(self, *, organization_id: str, media: MediaReference) -> bytes:
        self.downloaded_media.append({"organizationId": organization_id, "providerMediaId": media.provider_media_id})
        return self.media.get(media.provider_media_id, b"")

    def mark_as_read(self, *, organization_id: str, provider_message_id: str) -> dict[str, Any]:
        payload = {"organizationId": organization_id, "providerMessageId": provider_message_id, "read": True}
        self.read_messages.append(payload)
        return payload
