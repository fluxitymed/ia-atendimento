from __future__ import annotations

from dataclasses import dataclass, field
from os import environ
import threading
import time
from typing import Any, Callable, Protocol
from uuid import NAMESPACE_URL, uuid5

from .adapter import WhatsAppChannelAdapter
from dataclasses import replace

from .channel import ChannelDecision, ChannelRecord, InboundMessage, WhatsAppMessageType
from .media import MediaDecision


DEFAULT_MESSAGE_BATCH_DEBOUNCE_MS = 6000
DEFAULT_MESSAGE_BATCH_MAX_WAIT_MS = 12000


class ScheduledHandle(Protocol):
    def cancel(self) -> None:
        ...


class TimerScheduler:
    def now_ms(self) -> int:
        return int(time.monotonic() * 1000)

    def call_later(self, delay_ms: int, callback: Callable[[], None]) -> ScheduledHandle:
        timer = threading.Timer(max(delay_ms, 0) / 1000, callback)
        timer.daemon = True
        timer.start()
        return timer


@dataclass(frozen=True)
class MessageBatchingConfig:
    debounce_ms: int = DEFAULT_MESSAGE_BATCH_DEBOUNCE_MS
    max_wait_ms: int = DEFAULT_MESSAGE_BATCH_MAX_WAIT_MS
    enabled: bool = True

    @classmethod
    def from_env(cls) -> "MessageBatchingConfig":
        debounce_ms = int(environ.get("MESSAGE_BATCH_DEBOUNCE_MS", str(DEFAULT_MESSAGE_BATCH_DEBOUNCE_MS)))
        max_wait_ms = int(environ.get("MESSAGE_BATCH_MAX_WAIT_MS", str(DEFAULT_MESSAGE_BATCH_MAX_WAIT_MS)))
        enabled = environ.get("MESSAGE_BATCH_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
        return cls(debounce_ms=debounce_ms, max_wait_ms=max_wait_ms, enabled=enabled)

    def validate(self) -> None:
        if self.debounce_ms <= 0:
            raise ValueError("MESSAGE_BATCH_DEBOUNCE_MS must be positive")
        if self.max_wait_ms < self.debounce_ms:
            raise ValueError("MESSAGE_BATCH_MAX_WAIT_MS must be greater than or equal to MESSAGE_BATCH_DEBOUNCE_MS")


@dataclass
class _PendingBatch:
    inbound: list[InboundMessage] = field(default_factory=list)
    raw_events: list[dict[str, Any]] = field(default_factory=list)
    first_seen_ms: int = 0
    last_seen_ms: int = 0
    debounce_handle: ScheduledHandle | None = None
    max_wait_handle: ScheduledHandle | None = None


class MessageBatchingWhatsAppChannelAdapter:
    def __init__(
        self,
        adapter: WhatsAppChannelAdapter,
        *,
        config: MessageBatchingConfig | None = None,
        scheduler: Any | None = None,
    ):
        self.adapter = adapter
        self.config = config or MessageBatchingConfig()
        self.config.validate()
        self.scheduler = scheduler or TimerScheduler()
        self._lock = threading.RLock()
        self._pending: dict[str, _PendingBatch] = {}
        self._running: set[str] = set()
        self.flushed_records: list[ChannelRecord] = []

    @property
    def runtime_calls(self) -> int:
        return self.adapter.runtime_calls

    def process_event(self, raw_event: dict[str, Any]) -> ChannelRecord:
        if not self.config.enabled:
            return self.adapter.process_event(raw_event)
        provider_message_key = _provider_message_key(raw_event)
        self.adapter._log("provider_message_idempotency_checked", {"providerMessageId": raw_event.get("providerMessageId"), "providerAccountId": raw_event.get("providerAccountId")})
        if self.adapter.store.has_seen_provider_message_key(provider_message_key):
            self.adapter._log("provider_message_duplicate_rejected", {"providerMessageId": raw_event.get("providerMessageId"), "providerAccountId": raw_event.get("providerAccountId")})
            self.adapter._log("duplicate_detected", {"providerMessageId": raw_event.get("providerMessageId"), "providerAccountId": raw_event.get("providerAccountId")})
            return _duplicate_record(raw_event, provider_message_key)
        self.adapter.store.reserve_provider_message_key(provider_message_key)
        try:
            inbound = self.adapter.normalize_event(raw_event)
        except Exception:
            self.adapter.store.release_provider_message_key(provider_message_key)
            raise
        if raw_event.get("fromSelf"):
            return self.adapter.process_event(raw_event)
        if inbound.type == WhatsAppMessageType.AUDIO:
            materialized = self._materialize_audio_for_batch(inbound)
            if isinstance(materialized, ChannelRecord):
                return materialized
            inbound = materialized
        elif inbound.type.value != "TEXT":
            return self.adapter.process_event(raw_event)
        if self.adapter.reject_out_of_order and self.adapter.store.is_out_of_order(inbound):
            return self.adapter.process_event(raw_event)
        if self.adapter.store.is_handoff_active(inbound.conversation_id):
            return self.adapter.process_event(raw_event)
        if _should_early_flush(inbound.operational_text()):
            self.adapter._log("message_batch_started", {"conversationId": inbound.conversation_id, "reason": "EARLY_FLUSH"})
            self.adapter._log("message_batch_flushed", {"conversationId": inbound.conversation_id, "reason": "EARLY_FLUSH"})
            self.adapter._log("message_batch_size", {"conversationId": inbound.conversation_id, "count": 1})
            self.adapter._log("message_batch_age_ms", {"conversationId": inbound.conversation_id, "ageMs": 0})
            self.adapter._log("logical_patient_turn_created", {"conversationId": inbound.conversation_id, "providerMessageIds": [inbound.provider_message_id]})
            return self._process_logical_event(raw_event, conversation_id=inbound.conversation_id)
        with self._lock:
            batch = self._pending.get(inbound.conversation_id)
            now_ms = self.scheduler.now_ms()
            if batch is None:
                batch = _PendingBatch(first_seen_ms=now_ms, last_seen_ms=now_ms)
                self._pending[inbound.conversation_id] = batch
                self.adapter._log("message_batch_started", {"conversationId": inbound.conversation_id})
                batch.max_wait_handle = self.scheduler.call_later(
                    self.config.max_wait_ms,
                    lambda conversation_id=inbound.conversation_id: self.flush(conversation_id, reason="MAX_WAIT"),
                )
            else:
                batch.last_seen_ms = now_ms
                if batch.debounce_handle is not None:
                    batch.debounce_handle.cancel()
                self.adapter._log("message_batch_debounce_reset", {"conversationId": inbound.conversation_id})
            batch.inbound.append(inbound)
            batch.raw_events.append(dict(raw_event))
            batch.last_seen_ms = now_ms
            self.adapter._log("message_batch_message_added", {"conversationId": inbound.conversation_id, "providerMessageId": inbound.provider_message_id})
            if inbound.metadata.get("sourceMessageType") == "AUDIO" or inbound.type == WhatsAppMessageType.AUDIO:
                self.adapter._log("audio_added_to_batch", {"conversationId": inbound.conversation_id, "providerMessageId": inbound.provider_message_id})
            self.adapter._log("queued_inbound_count", {"conversationId": inbound.conversation_id, "count": len(batch.inbound)})
            batch.debounce_handle = self.scheduler.call_later(
                self.config.debounce_ms,
                lambda conversation_id=inbound.conversation_id: self.flush(conversation_id, reason="DEBOUNCE"),
            )
            return ChannelRecord(
                inbound=inbound,
                decision=ChannelDecision.BATCH_QUEUED,
                metrics={"queued": True, "queuedInboundCount": len(batch.inbound)},
            )

    def flush(self, conversation_id: str, *, reason: str = "MANUAL") -> ChannelRecord | None:
        with self._lock:
            if conversation_id in self._running:
                batch = self._pending.get(conversation_id)
                self.adapter._log("queued_inbound_count", {"conversationId": conversation_id, "count": len(batch.inbound) if batch else 0})
                if batch:
                    batch.debounce_handle = self.scheduler.call_later(
                        self.config.debounce_ms,
                        lambda conversation_id=conversation_id: self.flush(conversation_id, reason="DEBOUNCE"),
                    )
                return None
            batch = self._pending.pop(conversation_id, None)
            if batch is None or not batch.raw_events:
                return None
            self._cancel(batch)
            self._running.add(conversation_id)
        if reason == "MAX_WAIT":
            self.adapter._log("message_batch_max_wait_reached", {"conversationId": conversation_id})
        age_ms = max(self.scheduler.now_ms() - batch.first_seen_ms, 0)
        self.adapter._log("message_batch_flushed", {"conversationId": conversation_id, "reason": reason})
        self.adapter._log("message_batch_size", {"conversationId": conversation_id, "count": len(batch.inbound)})
        self.adapter._log("message_batch_age_ms", {"conversationId": conversation_id, "ageMs": age_ms})
        logical_event = _logical_event(batch.raw_events, batch.inbound)
        self.adapter._log("logical_patient_turn_created", {"conversationId": conversation_id, "providerMessageIds": [item.provider_message_id for item in batch.inbound]})
        failed = False
        try:
            record = self._process_logical_event(logical_event, conversation_id=conversation_id)
            self.flushed_records.append(record)
            return record
        except Exception as exc:
            failed = True
            self.adapter._log(
                "batch_processing_failed",
                {
                    "conversationId": conversation_id,
                    "errorType": exc.__class__.__name__,
                    "error": _sanitize_batch_error(str(exc)),
                },
            )
            return None
        finally:
            with self._lock:
                self._running.discard(conversation_id)
                self.adapter._log("conversation_lock_released", {"conversationId": conversation_id})
                if failed:
                    self.adapter._log("conversation_recovered_after_failure", {"conversationId": conversation_id})
                if conversation_id in self._pending:
                    self.scheduler.call_later(0, lambda conversation_id=conversation_id: self.flush(conversation_id, reason="LOCK_RELEASED"))

    def _process_logical_event(self, raw_event: dict[str, Any], *, conversation_id: str) -> ChannelRecord:
        self.adapter._log("conversation_lock_acquired", {"conversationId": conversation_id})
        return self.adapter.process_event(raw_event)

    def _materialize_audio_for_batch(self, inbound: InboundMessage) -> InboundMessage | ChannelRecord:
        self.adapter._log("audio_inbound_detected", {"providerMessageId": inbound.provider_message_id, "conversationId": inbound.conversation_id})
        if self.adapter.media_processor is None or inbound.media_reference is None:
            return self.adapter._handoff(inbound, reason="MEDIA_PROCESSOR_UNAVAILABLE", transcript=None, extracted_text=None)
        media_result = self.adapter.media_processor.process(
            organization_id=inbound.organization_id,
            message_type=inbound.type,
            media_reference=inbound.media_reference,
            mime_type=inbound.mime_type,
            file_name=inbound.file_name,
            metadata={**inbound.media_reference.metadata, **inbound.metadata},
        )
        if media_result.decision == MediaDecision.MEDIA_RETRY_REQUIRED:
            text = media_result.retry_message or "Nao consegui entender bem esse audio. Pode me mandar novamente ou escrever aqui?"
            outbound = self.adapter._send_text(inbound, text, metadata={"mediaDecision": media_result.decision.value, **media_result.metadata})
            record = ChannelRecord(
                inbound=inbound,
                decision=ChannelDecision.MEDIA_RETRY_REQUIRED,
                outbound=outbound,
                transcript=media_result.transcript,
                extracted_text=media_result.extracted_text,
                metrics={"mediaRetry": True},
            )
            return self.adapter.store.record(record)
        if media_result.decision == MediaDecision.HUMAN_HANDOFF_REQUIRED:
            return self.adapter._handoff(
                inbound,
                reason=media_result.handoff_reason or "MEDIA_REQUIRES_HUMAN_REVIEW",
                transcript=media_result.transcript,
                extracted_text=media_result.extracted_text,
            )
        metadata = {
            **dict(inbound.metadata),
            **media_result.metadata,
            "sourceMessageType": "AUDIO",
            "originalProviderMessageId": inbound.provider_message_id,
            "transcript": media_result.transcript or media_result.operational_text or "",
            "mediaAlreadyProcessed": True,
            "transcriptionProvider": "openai",
            "transcriptionModel": media_result.metadata.get("model"),
        }
        return replace(inbound, text=media_result.operational_text or "", metadata=metadata)

    def _cancel(self, batch: _PendingBatch) -> None:
        for handle in (batch.debounce_handle, batch.max_wait_handle):
            if handle is not None:
                handle.cancel()
        batch.debounce_handle = None
        batch.max_wait_handle = None


def _provider_message_key(raw_event: dict[str, Any]) -> str:
    return f"{raw_event.get('providerAccountId')}:{raw_event.get('providerMessageId')}"


def _duplicate_record(raw_event: dict[str, Any], provider_message_key: str) -> ChannelRecord:
    inbound = InboundMessage(
        id=str(uuid5(NAMESPACE_URL, f"whatsapp:duplicate:{provider_message_key}")),
        provider_message_id=str(raw_event.get("providerMessageId") or ""),
        organization_id="",
        conversation_id="",
        contact_external_id=str(raw_event.get("contactExternalId") or ""),
        type=WhatsAppMessageType(str(raw_event.get("type") or WhatsAppMessageType.TEXT.value).upper()),
        text=raw_event.get("text"),
        timestamp=str(raw_event.get("timestamp") or ""),
        metadata={
            "providerAccountId": raw_event.get("providerAccountId"),
            "providerMessageKey": provider_message_key,
            "duplicateRejectedBeforeConversation": True,
            **dict(raw_event.get("metadata") or {}),
        },
    )
    return ChannelRecord(inbound=inbound, decision=ChannelDecision.DUPLICATE_SUPPRESSED, metrics={"duplicate": True, "rejectedBeforeConversation": True})


def _logical_event(raw_events: list[dict[str, Any]], inbound: list[InboundMessage]) -> dict[str, Any]:
    first = dict(raw_events[0])
    texts = [message.operational_text() for message in inbound if message.operational_text()]
    provider_ids = [message.provider_message_id for message in inbound]
    provider_keys = [message.metadata.get("providerMessageKey") or _provider_message_key(raw) for raw, message in zip(raw_events, inbound)]
    timestamps = [message.timestamp for message in inbound]
    source_types = [message.metadata.get("sourceMessageType") or message.type.value for message in inbound]
    first["providerMessageId"] = "+".join(provider_ids)
    first["text"] = "\n".join(texts)
    first["timestamp"] = timestamps[0] if timestamps else first.get("timestamp")
    if any(source_type != "TEXT" for source_type in source_types):
        first["type"] = source_types[0]
    metadata = {**dict(first.get("metadata") or {}), **dict(inbound[0].metadata if inbound else {})}
    metadata.update(
        {
            "isMessageBatch": True,
            "batchProviderMessageIds": provider_ids,
            "batchProviderMessageKeys": provider_keys,
            "batchTimestamps": timestamps,
            "batchTexts": texts,
            "batchMessageTypes": source_types,
            "batchTranscripts": [message.metadata.get("transcript") for message in inbound],
            "batchSize": len(inbound),
            "mediaAlreadyProcessed": any(message.metadata.get("mediaAlreadyProcessed") for message in inbound),
            "sourceMessageType": source_types[0] if source_types else "TEXT",
        }
    )
    first["metadata"] = metadata
    return first


def _should_early_flush(text: str) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False
    urgent_phrases = (
        "sangramento intenso",
        "sangrando muito",
        "muita dor",
        "dor intensa",
        "trauma",
        "bati o dente",
        "quebrou o dente",
    )
    for phrase in urgent_phrases:
        if phrase in normalized and not _is_negated(normalized, phrase):
            return True
    return False


def _is_negated(text: str, phrase: str) -> bool:
    index = text.find(phrase)
    if index < 0:
        return False
    prefix = text[max(0, index - 24):index]
    return any(negation in prefix.split()[-4:] for negation in ("nao", "não", "nem", "sem"))


def _normalize(value: str) -> str:
    replacements = str.maketrans({"é": "e", "É": "e", "ã": "a", "Ã": "a", "ç": "c", "Ç": "c", "á": "a", "Á": "a", "í": "i", "Í": "i", "ó": "o", "Ó": "o", "ú": "u", "Ú": "u", "ê": "e", "Ê": "e", "ô": "o", "Ô": "o"})
    return " ".join(str(value or "").translate(replacements).lower().split())


def _sanitize_batch_error(text: str) -> str:
    lowered = str(text or "").lower()
    if "token" in lowered or "secret" in lowered or "authorization" in lowered or "api key" in lowered:
        return "batch processing error"
    return str(text or "")[:500]
