from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ai_agent_runtime.integrations.google_calendar import GoogleCalendarHttpTransport, GoogleCalendarProvider
from ai_agent_runtime.scheduling import CalendarTools, can_get_availability, update_scheduling_context
from ai_agent_runtime.state import AgentState

from .config import SandboxConfig


def build_google_calendar_plan(config: SandboxConfig) -> dict:
    outside = update_scheduling_context(AgentState("sandbox-conv-price", "sandbox-org-aurora", "Quanto custa a consulta?"))
    generic = update_scheduling_context(AgentState("sandbox-conv-interest", "sandbox-org-aurora", "Estou pensando em marcar semana que vem."))
    explicit = update_scheduling_context(AgentState("sandbox-conv-schedule", "sandbox-org-aurora", "Quero marcar uma consulta."))
    return {
        "service": "google_calendar",
        "status": "IMPLEMENTED",
        "calendarIdConfigured": bool(config.integrations.google_calendar_id),
        "timezone": config.google_calendar_timezone,
        "requiresSandboxCalendar": True,
        "guardChecks": {
            "priceQuestionCanCallCalendar": can_get_availability(outside),
            "genericInterestCanCallCalendar": can_get_availability(generic),
            "explicitSchedulingCanCallCalendar": can_get_availability(explicit),
        },
        "expectedProviderSlots": ["10:00", "14:00"],
        "forbiddenInventedSlots": ["16:00"],
        "testEvent": {
            "summary": "[SANDBOX] Paciente ficticio - AI Agent Live Sandbox",
            "cleanupRequired": True,
        },
    }


def run_google_calendar_smoke(config: SandboxConfig) -> dict:
    missing = []
    if not config.integrations.google_calendar_id:
        missing.append("GOOGLE_CALENDAR_ID")
    if not (config.integrations.google_calendar_access_token or config.integrations.google_calendar_refresh_token):
        missing.append("GOOGLE_CALENDAR_ACCESS_TOKEN_OR_REFRESH_TOKEN")
    if missing:
        return {**build_google_calendar_plan(config), "status": "BLOCKED_MISSING_CREDENTIALS", "missing": missing}
    transport = GoogleCalendarHttpTransport(config.integrations)
    provider = GoogleCalendarProvider(calendar_id=config.integrations.google_calendar_id, transport=transport)

    price = update_scheduling_context(AgentState("sandbox-conv-price", "sandbox-org-aurora", "Quanto custa a consulta?"))
    generic = update_scheduling_context(AgentState("sandbox-conv-interest", "sandbox-org-aurora", "Estou pensando em marcar semana que vem."))
    external_calls_before = 0
    blocked_calls = int(can_get_availability(price)) + int(can_get_availability(generic))

    now = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=7)
    time_min = now.isoformat().replace("+00:00", "Z")
    time_max = (now + timedelta(hours=4)).isoformat().replace("+00:00", "Z")
    active = update_scheduling_context(AgentState("sandbox-conv-schedule", "sandbox-org-aurora", "Tem horario sexta?"))
    tools = CalendarTools(provider)
    freebusy = tools.consultar_agenda(active, {"timeMin": time_min, "timeMax": time_max, "timeZone": config.google_calendar_timezone})

    created_id = None
    deleted = False
    try:
        created = provider.create_appointment(
            organization_id="sandbox-org-aurora",
            payload={
                "summary": "[SANDBOX] Paciente ficticio - AI Agent Live Sandbox",
                "description": "Evento ficticio criado por smoke test sandbox. Pode ser removido.",
                "start": {"dateTime": time_min, "timeZone": config.google_calendar_timezone},
                "end": {"dateTime": (now + timedelta(minutes=30)).isoformat().replace("+00:00", "Z"), "timeZone": config.google_calendar_timezone},
            },
        )
        created_id = created["id"]
        confirmed = transport.get(f"/calendars/{config.integrations.google_calendar_id}/events/{created_id}")
        rescheduled = provider.reschedule_appointment(
            organization_id="sandbox-org-aurora",
            appointment_id=created_id,
            payload={
                "start": {"dateTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"), "timeZone": config.google_calendar_timezone},
                "end": {"dateTime": (now + timedelta(hours=1, minutes=30)).isoformat().replace("+00:00", "Z"), "timeZone": config.google_calendar_timezone},
            },
        )
    finally:
        if created_id:
            provider.cancel_appointment(organization_id="sandbox-org-aurora", appointment_id=created_id, reason="sandbox cleanup")
            deleted = True

    if blocked_calls != 0:
        raise RuntimeError("Google Calendar guard allowed external calls outside scheduling context")
    return {
        **build_google_calendar_plan(config),
        "status": "LIVE_VERIFIED",
        "calendarAccessValidated": True,
        "externalCallsBeforeScheduling": external_calls_before,
        "freeBusyReturned": isinstance(freebusy, list),
        "createdEventId": created_id,
        "confirmedEventId": confirmed.get("id"),
        "rescheduledEventId": rescheduled.get("id"),
        "cleanupDeleted": deleted,
        "refreshCount": transport.refresh_count,
    }
