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
from .latency import TurnLatency, active_turn, observe, stamp
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
    generation: int = 0
    latency_started: dict = field(default_factory=stamp)


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

    def process_event(self, raw_event: dict[str, Any], *, _reserved: bool = False) -> ChannelRecord:
        if not self.config.enabled:
            return self.adapter.process_event(raw_event, _reserved=_reserved)
        self.adapter.organization_resolver.resolve(str(raw_event.get("providerAccountId") or ""))
        raw_event = {**raw_event, "metadata": dict(raw_event.get("metadata") or {})}
        raw_event["metadata"].setdefault("latencyPoints", {"webhook_ingress_received": stamp()})
        provider_message_key = _provider_message_key(raw_event)
        self.adapter._log("provider_message_idempotency_checked", {"providerMessageId": raw_event.get("providerMessageId"), "providerAccountId": raw_event.get("providerAccountId")})
        if not _reserved and not self.adapter.store.reserve_provider_message_key(provider_message_key):
            self.adapter._log("provider_message_duplicate_rejected", {"providerMessageId": raw_event.get("providerMessageId"), "providerAccountId": raw_event.get("providerAccountId")})
            self.adapter._log("duplicate_detected", {"providerMessageId": raw_event.get("providerMessageId"), "providerAccountId": raw_event.get("providerAccountId")})
            return _duplicate_record(raw_event, provider_message_key)
        try:
            inbound = self.adapter.normalize_event(raw_event)
        except Exception:
            self.adapter.store.release_provider_message_key(provider_message_key)
            raise
        if raw_event.get("fromSelf"):
            return self.adapter.process_event(raw_event, _reserved=True)
        # The monitored adapter must establish CRM context before media can
        # hand off or send a retry response. Bypass batching for those turns.
        if self.adapter.crm_monitor is not None and inbound.type != WhatsAppMessageType.TEXT:
            return self.adapter.process_event(raw_event, _reserved=True)
        if inbound.type == WhatsAppMessageType.AUDIO:
            trace = TurnLatency(self.adapter.stage_logger, {
                "organizationId": inbound.organization_id, "conversationId": inbound.conversation_id,
                "runtimeInvocationId": str(uuid5(NAMESPACE_URL, "media:" + provider_message_key)),
                "providerMessageId": inbound.provider_message_id,
            }, inbound.metadata)
            token = active_turn.set(trace)
            try:
                with self.adapter.store.conversation_lock(inbound.conversation_id):
                    observe("lock_acquired")
                    materialized = self._materialize_audio_for_batch(inbound)
                if isinstance(materialized, ChannelRecord):
                    trace.finish(materialized.decision.value)
                    return materialized
                inbound = materialized
            except Exception:
                trace.finish("OUTBOUND_UNKNOWN" if "outbound_started" in trace.points else "MEDIA_FAILED")
                raise
            finally:
                for stage in list(trace.timers):
                    trace.cancel(stage)
                active_turn.reset(token)
        elif inbound.type.value != "TEXT":
            return self.adapter.process_event(raw_event, _reserved=True)
        if self.adapter.reject_out_of_order and self.adapter.store.is_out_of_order(inbound):
            return self.adapter.process_event(raw_event, _reserved=True)
        if self.adapter.store.is_handoff_active(inbound.conversation_id):
            return self.adapter.process_event(raw_event, _reserved=True)
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
            self._schedule(inbound.conversation_id, batch)
            return ChannelRecord(
                inbound=inbound,
                decision=ChannelDecision.BATCH_QUEUED,
                metrics={"queued": True, "queuedInboundCount": len(batch.inbound)},
            )

    def flush(self, conversation_id: str, *, reason: str = "MANUAL", _batch=None, _generation=None) -> ChannelRecord | None:
        with self._lock:
            current = self._pending.get(conversation_id)
            if _batch is not None and (current is not _batch or current.generation != _generation):
                return None
            if conversation_id in self._running:
                # Completion will schedule the waiting batch. No polling timers.
                if current:
                    self._cancel(current)
                return None
            batch = self._pending.pop(conversation_id, None)
            if batch is None or not batch.raw_events:
                return None
            self._cancel(batch)
            self._running.add(conversation_id)
        failed = False
        try:
            if reason == "MAX_WAIT":
                self.adapter._log("message_batch_max_wait_reached", {"conversationId": conversation_id})
            age_ms = max(self.scheduler.now_ms() - batch.first_seen_ms, 0)
            self.adapter._log("message_batch_flushed", {"conversationId": conversation_id, "reason": reason})
            self.adapter._log("message_batch_size", {"conversationId": conversation_id, "count": len(batch.inbound)})
            self.adapter._log("message_batch_age_ms", {"conversationId": conversation_id, "ageMs": age_ms})
            logical_event = _logical_event(batch.raw_events, batch.inbound)
            logical_event["metadata"]["latencyPoints"] = {**dict(logical_event["metadata"].get("latencyPoints") or {}), "batch_started": batch.latency_started, "batch_flushed": stamp()}
            self.adapter._log("logical_patient_turn_created", {"conversationId": conversation_id, "providerMessageIds": [item.provider_message_id for item in batch.inbound]})
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
                    self._schedule(conversation_id, self._pending[conversation_id], immediate=True)

    def _process_logical_event(self, raw_event: dict[str, Any], *, conversation_id: str) -> ChannelRecord:
        return self.adapter.process_event(raw_event, _reserved=True)

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

    def _schedule(self, conversation_id, batch, *, immediate=False):
        self._cancel(batch)
        batch.generation += 1
        generation = batch.generation
        deadline = min(batch.last_seen_ms + self.config.debounce_ms, batch.first_seen_ms + self.config.max_wait_ms)
        reason = "MAX_WAIT" if deadline == batch.first_seen_ms + self.config.max_wait_ms else "DEBOUNCE"
        batch.debounce_handle = self.scheduler.call_later(
            0 if immediate else max(0, deadline - self.scheduler.now_ms()),
            lambda: self.flush(conversation_id, reason=reason, _batch=batch, _generation=generation),
        )

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
    # Keep all arrays index-aligned with provider_ids so the CRM monitor can
    # insert/idempotency-check every physical provider message independently.
    texts = [message.operational_text() for message in inbound]
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
