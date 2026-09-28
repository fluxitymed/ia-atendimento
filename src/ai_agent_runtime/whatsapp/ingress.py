"""Bounded HTTP ingress: durable admission before acknowledgement, no network on HTTP threads."""
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from .channel import ChannelDecision, ChannelRecord
from .latency import stamp
from .batching import _duplicate_record, _provider_message_key


class IngressBusy(RuntimeError):
    pass


class AsyncWhatsAppIngress:
    def __init__(self, adapter, *, workers=8, capacity=128):
        self.adapter = adapter
        self.base = getattr(adapter, 'adapter', adapter)
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='whatsapp-ingress')
        self.slots = BoundedSemaphore(capacity)

    def process_event(self, event):
        event = {**event, 'metadata': dict(event.get('metadata') or {})}
        event['metadata'].setdefault('latencyPoints', {'webhook_ingress_received': stamp()})
        # Reject duplicate IDs before alias/conversation mutation.
        self.base.organization_resolver.resolve(str(event.get("providerAccountId") or ""))
        key = _provider_message_key(event)
        if self.base.store.has_seen_provider_message_key(key):
            return _duplicate_record(event, key)
        if not self.slots.acquire(blocking=False):
            self.base._log('webhook_capacity_exceeded', {'providerMessageId': event.get('providerMessageId')})
            raise IngressBusy('INGRESS_CAPACITY_EXCEEDED')
        try:
            if not self.base.store.reserve_provider_message_key(key):
                self.slots.release()
                return _duplicate_record(event, key)
            try:
                inbound = self.base.normalize_event(event)
                self.executor.submit(self._run, event)
            except Exception:
                self.base.store.release_provider_message_key(key)
                raise
        except Exception:
            self.slots.release()
            raise
        self.base._log('webhook_accepted', {'organizationId': inbound.organization_id, 'conversationId': inbound.conversation_id, 'providerMessageId': inbound.provider_message_id})
        return ChannelRecord(inbound, ChannelDecision.BATCH_QUEUED, metrics={'accepted': True})

    def _run(self, event):
        try:
            self.adapter.process_event(event, _reserved=True)
        except Exception as exc:
            # Claims intentionally survive failure/restart; do not auto-replay.
            self.base._log('ingress_processing_failed', {'providerMessageId': event.get('providerMessageId'), 'errorType': type(exc).__name__})
        finally:
            self.slots.release()

    def close(self):
        self.executor.shutdown(wait=True)
