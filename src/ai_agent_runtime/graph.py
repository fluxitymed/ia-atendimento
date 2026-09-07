from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .commercial import CommercialPlaybook, organization_config_from_context
from .state import AgentDecision, AgentIntent, AgentStage, AgentState


RUNTIME_NODE_NAMES = (
    "interpret_message",
    "decide_route",
    "execute_tool",
    "grounding",
    "handoff",
)


class RuntimeResponseError(RuntimeError):
    pass


class ResponseGenerator(Protocol):
    def generate(self, state: AgentState, *, emit: Callable[[str, dict[str, Any] | None], None]) -> str:
        ...


@dataclass(frozen=True)
class StaticResponseGenerator:
    prefix: str = "Resposta"

    def generate(self, state: AgentState, *, emit: Callable[[str, dict[str, Any] | None], None]) -> str:
        emit("retrieval_completed", {"mode": "test-double", "hitCount": 0})
        emit("model_called", {"mode": "test-double"})
        emit("grounding_result", {"passed": True, "mode": "test-double"})
        turn = len([message for message in state.messages if message.get("direction") == "inbound"])
        return f"{self.prefix} {turn}: {state.current_message}"


class AgentRuntimeGraph:
    def __init__(
        self,
        *,
        response_generator: ResponseGenerator | None = None,
        stage_logger: Callable[[str, dict[str, Any] | None], None] | None = None,
        commercial_playbook: CommercialPlaybook | None = None,
    ):
        self.node_names = RUNTIME_NODE_NAMES
        self.langgraph_available = self._detect_langgraph()
        self.response_generator = response_generator
        self.stage_logger = stage_logger
        self.commercial_playbook = commercial_playbook or CommercialPlaybook()

    @staticmethod
    def _detect_langgraph() -> bool:
        try:
            import langgraph  # noqa: F401
        except Exception:
            return False
        return True

    def topology(self) -> tuple[str, ...]:
        return self.node_names

    def emit(self, stage: str, details: dict[str, Any] | None = None) -> None:
        self._append_runtime_event(stage, details)
        if self.stage_logger is not None:
            self.stage_logger(stage, details)

    def interpret_message(self, state: AgentState) -> AgentState:
        message = (state.current_message or "").lower()
        if "humano" in message or "atendente" in message:
            state.intent = AgentIntent.HUMAN_HANDOFF_REQUIRED
        return state

    def decide_route(
        self,
        state: AgentState,
        inherited_decision: AgentDecision | None = None,
    ) -> AgentState:
        if inherited_decision == AgentDecision.HUMAN_HANDOFF_REQUIRED:
            state.decision = AgentDecision.HUMAN_HANDOFF_REQUIRED
            state.stage = AgentStage.HANDOFF
            state.handoff_context = {
                "conversationId": state.conversation_id,
                "organizationId": state.organization_id,
                "messages": list(state.messages),
                "currentMessage": state.current_message,
                "reason": "HUMAN_HANDOFF_REQUIRED",
            }
            return state

        if state.intent == AgentIntent.HUMAN_HANDOFF_REQUIRED:
            state.decision = AgentDecision.HUMAN_HANDOFF_REQUIRED
            state.stage = AgentStage.HANDOFF
            state.handoff_context = {
                "conversationId": state.conversation_id,
                "organizationId": state.organization_id,
                "messages": list(state.messages),
                "currentMessage": state.current_message,
                "reason": "PATIENT_REQUESTED_HUMAN",
            }
        return state

    def run(
        self,
        state: AgentState,
        inherited_decision: AgentDecision | None = None,
        scheduler: Callable[[AgentState], AgentState] | None = None,
    ) -> AgentState:
        self._active_state = state
        try:
            self.emit("runtime_started", {"conversationId": state.conversation_id, "organizationId": state.organization_id})
            state.append_message("inbound", state.current_message, metadata=state.context.get("currentMessageMetadata"))
            commercial_state = self.commercial_playbook.evaluate(
                state.messages,
                current_message=state.current_message,
                organization_config=organization_config_from_context(state.context),
                scheduling_context_active=state.scheduling_context_active,
                previous_assistant_question=str(state.context.get("previousAssistantQuestion") or ""),
                channel_contact_external_id=state.context.get("channelContactExternalId"),
                scheduling_status=state.context.get("schedulingStatus"),
                assistant_introduced=state.context.get("assistantIntroduced"),
                answered_facts=state.context.get("answeredFacts"),
                current_message_at=state.context.get("currentMessageAt"),
                previous_assistant_message_at=state.context.get("previousAssistantMessageAt"),
            )
            state.context["commercialState"] = commercial_state.as_dict()
            self.emit("commercial_state_updated", commercial_state.as_dict())
            state = self.interpret_message(state)
            if scheduler is not None:
                state = scheduler(state)
            state = self.decide_route(state, inherited_decision=inherited_decision)
            self._active_state = state
            if state.decision != AgentDecision.HUMAN_HANDOFF_REQUIRED and self.response_generator is not None:
                generated_text = self.response_generator.generate(state, emit=self.emit).strip()
                if state.decision == AgentDecision.HUMAN_HANDOFF_REQUIRED:
                    if state.stage != AgentStage.HANDOFF:
                        state.stage = AgentStage.HANDOFF
                    return state
                state.response_text = generated_text
                if not state.response_text:
                    raise RuntimeResponseError("RUNTIME_RESPONSE_EMPTY")
                self.emit("response_generated", {"hasText": True, "decision": state.decision.value})
            return state
        finally:
            self._active_state = None

    def _append_runtime_event(self, stage: str, details: dict[str, Any] | None) -> None:
        state = getattr(self, "_active_state", None)
        if state is None:
            return
        events = state.context.setdefault("runtimeEvents", [])
        events.append({"stage": stage, "details": dict(details or {})})
