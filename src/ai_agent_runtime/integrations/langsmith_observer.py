from __future__ import annotations

import re
from typing import Any

from ai_agent_runtime.observability import AuditEvent, AuditStore, RuntimeObservability


EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?<![\w-])(?:\+\d{1,3}[\s().-]?)?(?:\(?\d{2,3}\)?[\s.-]?)?\d{4,5}[\s.-]?\d{4}(?![\w-])")


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        value = EMAIL_RE.sub("[REDACTED_EMAIL]", value)
        value = PHONE_RE.sub("[REDACTED_PHONE]", value)
        return value
    if isinstance(value, dict):
        return {key: redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    return value


class LangSmithObserver:
    def __init__(self, *, api_key: str | None, project: str, transport=None):
        self.api_key = api_key
        self.project = project
        self.transport = transport

    def prepare_payload(self, event: AuditEvent) -> dict[str, Any]:
        return redact_value({
            "project": self.project,
            "conversationId": event.conversation_id,
            "organizationId": event.organization_id,
            "intent": event.intent,
            "decision": event.decision,
            "toolCalled": event.tool_called,
            "documentVersionsUsed": event.document_versions_used,
            "groundingResult": event.grounding_result,
            "handoffReason": event.handoff_reason,
            "timestamp": event.timestamp,
        })

    def trace(self, event: AuditEvent) -> None:
        if not self.api_key or self.transport is None:
            return
        self.transport.send(self.prepare_payload(event))


def create_observable_runtime(audit_store: AuditStore, observer: LangSmithObserver | None) -> RuntimeObservability:
    return RuntimeObservability(audit_store, observer)
