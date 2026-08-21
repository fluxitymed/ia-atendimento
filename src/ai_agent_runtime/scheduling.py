from __future__ import annotations

from typing import Any

from .providers import CalendarProvider
from .state import AgentIntent, AgentStage, AgentState


class SchedulingGuardError(RuntimeError):
    pass


SCHEDULING_KEYWORDS = (
    "quero marcar",
    "quero agendar",
    "marcar consulta",
    "agendar consulta",
    "tem horario",
    "tem horário",
    "horario sexta",
    "horário sexta",
    "semana que vem",
    "pode ser amanha",
    "pode ser amanhã",
)

GENERAL_INTEREST_KEYWORDS = (
    "quais procedimentos",
    "quanto custa",
    "mais informacoes",
    "mais informações",
    "como funciona",
    "estou pensando",
    "depois eu vejo",
)


def classify_scheduling_intent(message: str) -> AgentIntent:
    text = (message or "").lower()
    if any(keyword in text for keyword in GENERAL_INTEREST_KEYWORDS):
        return AgentIntent.GENERAL_INFORMATION
    if any(keyword in text for keyword in SCHEDULING_KEYWORDS):
        if "horario" in text or "horário" in text or "semana que vem" in text:
            return AgentIntent.AVAILABILITY_REQUEST
        return AgentIntent.SCHEDULING_REQUEST
    return AgentIntent.UNKNOWN


def update_scheduling_context(state: AgentState) -> AgentState:
    state.intent = classify_scheduling_intent(state.current_message)
    if state.intent in {AgentIntent.SCHEDULING_REQUEST, AgentIntent.AVAILABILITY_REQUEST}:
        state.stage = AgentStage.SCHEDULING_CONTEXT_ACTIVE
    return state


def can_get_availability(state: AgentState) -> bool:
    return state.scheduling_context_active and state.intent in {
        AgentIntent.SCHEDULING_REQUEST,
        AgentIntent.AVAILABILITY_REQUEST,
    }


def assert_can_get_availability(state: AgentState) -> None:
    if not can_get_availability(state):
        raise SchedulingGuardError("get_availability requires active scheduling context and availability intent")


class CalendarTools:
    def __init__(self, provider: CalendarProvider):
        self.provider = provider

    def consultar_agenda(self, state: AgentState, criteria: dict[str, Any]) -> list[dict[str, Any]]:
        assert_can_get_availability(state)
        return self.provider.get_availability(
            organization_id=state.organization_id,
            criteria=criteria,
        )

    def criar_agendamento(self, state: AgentState, payload: dict[str, Any]) -> dict[str, Any]:
        if not state.scheduling_context_active:
            raise SchedulingGuardError("create_appointment requires active scheduling context")
        return self.provider.create_appointment(organization_id=state.organization_id, payload=payload)

    def reagendar_agendamento(self, state: AgentState, appointment_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not state.scheduling_context_active:
            raise SchedulingGuardError("reschedule_appointment requires active scheduling context")
        return self.provider.reschedule_appointment(
            organization_id=state.organization_id,
            appointment_id=appointment_id,
            payload=payload,
        )

    def cancelar_agendamento(self, state: AgentState, appointment_id: str, reason: str | None = None) -> dict[str, Any]:
        return self.provider.cancel_appointment(
            organization_id=state.organization_id,
            appointment_id=appointment_id,
            reason=reason,
        )
