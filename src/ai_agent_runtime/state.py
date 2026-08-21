from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentIntent(str, Enum):
    UNKNOWN = "UNKNOWN"
    GENERAL_INFORMATION = "GENERAL_INFORMATION"
    FACTUAL_QUESTION = "FACTUAL_QUESTION"
    SCHEDULING_REQUEST = "SCHEDULING_REQUEST"
    AVAILABILITY_REQUEST = "AVAILABILITY_REQUEST"
    HUMAN_HANDOFF_REQUIRED = "HUMAN_HANDOFF_REQUIRED"


class AgentStage(str, Enum):
    QUALIFICATION = "QUALIFICATION"
    INFORMATION = "INFORMATION"
    SCHEDULING_CONTEXT_ACTIVE = "SCHEDULING_CONTEXT_ACTIVE"
    HANDOFF = "HANDOFF"


class AgentDecision(str, Enum):
    CONTINUE = "CONTINUE"
    ANSWER_GROUNDED = "ANSWER_GROUNDED"
    CALL_TOOL = "CALL_TOOL"
    HUMAN_HANDOFF_REQUIRED = "HUMAN_HANDOFF_REQUIRED"


@dataclass
class AgentState:
    conversation_id: str
    organization_id: str
    current_message: str
    intent: AgentIntent = AgentIntent.UNKNOWN
    stage: AgentStage = AgentStage.QUALIFICATION
    decision: AgentDecision = AgentDecision.CONTINUE
    messages: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    handoff_context: dict[str, Any] | None = None

    @property
    def scheduling_context_active(self) -> bool:
        return self.stage == AgentStage.SCHEDULING_CONTEXT_ACTIVE

    def append_message(self, direction: str, text: str) -> None:
        self.messages.append({"direction": direction, "text": text})

    def snapshot(self) -> dict[str, Any]:
        return {
            "conversationId": self.conversation_id,
            "organizationId": self.organization_id,
            "currentMessage": self.current_message,
            "intent": self.intent.value,
            "stage": self.stage.value,
            "decision": self.decision.value,
            "messages": list(self.messages),
            "context": dict(self.context),
            "handoffContext": self.handoff_context,
        }
