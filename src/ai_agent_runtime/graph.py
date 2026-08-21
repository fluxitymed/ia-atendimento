from __future__ import annotations

from typing import Callable

from .state import AgentDecision, AgentIntent, AgentStage, AgentState


RUNTIME_NODE_NAMES = (
    "interpret_message",
    "decide_route",
    "execute_tool",
    "grounding",
    "handoff",
)


class AgentRuntimeGraph:
    def __init__(self):
        self.node_names = RUNTIME_NODE_NAMES
        self.langgraph_available = self._detect_langgraph()

    @staticmethod
    def _detect_langgraph() -> bool:
        try:
            import langgraph  # noqa: F401
        except Exception:
            return False
        return True

    def topology(self) -> tuple[str, ...]:
        return self.node_names

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
        state.append_message("inbound", state.current_message)
        state = self.interpret_message(state)
        if scheduler is not None:
            state = scheduler(state)
        return self.decide_route(state, inherited_decision=inherited_decision)
