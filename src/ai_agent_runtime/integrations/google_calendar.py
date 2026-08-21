from __future__ import annotations

import json
from typing import Any, Protocol
from urllib import error, parse, request

from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.providers import CalendarProvider


class GoogleCalendarTransport(Protocol):
    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    def patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    def delete(self, path: str) -> dict[str, Any]:
        ...


class GoogleCalendarAuthError(RuntimeError):
    pass


class GoogleCalendarApiError(RuntimeError):
    pass


class GoogleCalendarHttpTransport:
    base_url = "https://www.googleapis.com/calendar/v3"

    def __init__(self, config: IntegrationConfig):
        self.config = config
        self.access_token = config.google_calendar_access_token
        self.refresh_count = 0

    def get(self, path: str) -> dict[str, Any]:
        return self._request("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, payload)

    def patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", path, payload)

    def delete(self, path: str) -> dict[str, Any]:
        return self._request("DELETE", path)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None, *, retry: bool = True) -> dict[str, Any]:
        if not self.access_token:
            self.refresh_access_token()
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with request.urlopen(req, timeout=30) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except error.HTTPError as exc:
            if retry and _is_unauthorized(exc):
                self.refresh_access_token()
                return self._request(method, path, payload, retry=False)
            body = exc.read().decode("utf-8", errors="replace")
            raise GoogleCalendarApiError(f"Google Calendar HTTP {exc.code}: {body}") from exc
        except Exception as exc:
            if retry and _is_unauthorized(exc):
                self.refresh_access_token()
                return self._request(method, path, payload, retry=False)
            raise

    def refresh_access_token(self) -> str:
        if not self.config.google_calendar_refresh_token:
            raise GoogleCalendarAuthError("GOOGLE_CALENDAR_REFRESH_TOKEN is required to refresh Google Calendar access")
        if not self.config.google_oauth_client_id:
            raise GoogleCalendarAuthError("GOOGLE_OAUTH_CLIENT_ID is required to refresh Google Calendar access")
        if not self.config.google_oauth_client_secret:
            raise GoogleCalendarAuthError("GOOGLE_OAUTH_CLIENT_SECRET is required to refresh Google Calendar access")
        payload = parse.urlencode({
            "client_id": self.config.google_oauth_client_id,
            "client_secret": self.config.google_oauth_client_secret,
            "refresh_token": self.config.google_calendar_refresh_token,
            "grant_type": "refresh_token",
        }).encode("utf-8")
        req = request.Request(
            self.config.google_oauth_token_uri,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with request.urlopen(req, timeout=30) as response:
            token_response = json.loads(response.read().decode("utf-8"))
        self.access_token = token_response["access_token"]
        self.refresh_count += 1
        return self.access_token


def _is_unauthorized(exc: Exception) -> bool:
    return getattr(exc, "code", None) in {401, 403}


class GoogleCalendarProvider(CalendarProvider):
    def __init__(self, *, calendar_id: str, transport: GoogleCalendarTransport):
        self.calendar_id = calendar_id
        self.transport = transport

    def get_availability(self, *, organization_id: str, criteria: dict[str, Any]) -> list[dict[str, Any]]:
        response = self.transport.post(
            "/freeBusy",
            {
                "timeMin": criteria["timeMin"],
                "timeMax": criteria["timeMax"],
                "timeZone": criteria.get("timeZone", "America/Bahia"),
                "items": [{"id": self.calendar_id}],
            },
        )
        busy = response.get("calendars", {}).get(self.calendar_id, {}).get("busy", [])
        if "availableSlots" in response:
            return list(response["availableSlots"])
        return [{"busy": item} for item in busy]

    def create_appointment(self, *, organization_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.transport.post(
            f"/calendars/{self.calendar_id}/events",
            _with_private_organization(payload, organization_id),
        )

    def reschedule_appointment(self, *, organization_id: str, appointment_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.transport.patch(
            f"/calendars/{self.calendar_id}/events/{appointment_id}",
            _with_private_organization(payload, organization_id),
        )

    def cancel_appointment(self, *, organization_id: str, appointment_id: str, reason: str | None = None) -> dict[str, Any]:
        return self.transport.delete(f"/calendars/{self.calendar_id}/events/{appointment_id}")


def _with_private_organization(payload: dict[str, Any], organization_id: str) -> dict[str, Any]:
    extended = dict(payload.get("extendedProperties", {}))
    private = dict(extended.get("private", {}))
    private["organizationId"] = organization_id
    extended["private"] = private
    return {**payload, "extendedProperties": extended}
