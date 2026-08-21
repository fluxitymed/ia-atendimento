from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


@dataclass(frozen=True)
class AuditEvent:
    conversation_id: str
    organization_id: str
    intent: str | None = None
    decision: str | None = None
    tool_called: str | None = None
    document_versions_used: list[str] = field(default_factory=list)
    grounding_result: str | None = None
    handoff_reason: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AuditStore:
    def __init__(self):
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> AuditEvent:
        self.events.append(event)
        return event


class OptionalObserver(Protocol):
    def trace(self, event: AuditEvent) -> None:
        ...


class RuntimeObservability:
    def __init__(self, audit_store: AuditStore, observer: OptionalObserver | None = None):
        self.audit_store = audit_store
        self.observer = observer

    def record_event(self, event: AuditEvent) -> AuditEvent:
        recorded = self.audit_store.record(event)
        if self.observer is not None:
            try:
                self.observer.trace(recorded)
            except Exception:
                pass
        return recorded
