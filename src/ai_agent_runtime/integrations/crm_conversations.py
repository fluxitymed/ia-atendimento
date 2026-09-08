"""CRM conversation monitoring backed by the CRM Supabase PostgREST API.

The repository deliberately accepts a small REST transport protocol so runtime
code can use the network client while tests and host applications can inject a
transport with their own lifecycle and retry policy.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib import error, parse, request

from .config import IntegrationConfig


class CrmConfigurationError(RuntimeError):
    """Raised when the dedicated CRM integration is not configured."""


class CrmRestError(RuntimeError):
    """Raised for a REST/PostgREST request failure without exposing its body."""

    def __init__(self, message: str = "CRM REST request failed", *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class CrmRestConflictError(CrmRestError):
    """Raised for a PostgREST uniqueness conflict without retaining its body."""

    def __init__(self):
        super().__init__("CRM REST request conflicted", status_code=409)


class UnknownCrmInstanceError(LookupError):
    """Raised when an inbound Z-API instance has no explicit CRM mapping."""


class CrmRestTransport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str] | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        ...


class UrllibPostgrestTransport:
    """Minimal PostgREST transport used only when no transport is injected."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/") + "/rest/v1"

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str] | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        url = self.base_url + path
        if params:
            url += "?" + parse.urlencode(params)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = request.Request(url, data=body, headers=dict(headers), method=method)
        try:
            with request.urlopen(req, timeout=15) as response:
                text = response.read().decode("utf-8")
        except error.HTTPError as exc:
            if exc.code == 409:
                raise CrmRestConflictError() from exc
            raise CrmRestError(f"CRM REST request failed with status {exc.code}", status_code=exc.code) from exc
        except (error.URLError, OSError) as exc:
            raise CrmRestError("CRM REST request failed") from exc
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise CrmRestError("CRM REST response was not JSON") from exc


class CrmOrganizationResolver:
    def __init__(self, instance_organization_map: Mapping[str, str]):
        self._mapping = {str(instance): str(organization) for instance, organization in instance_organization_map.items()}

    @classmethod
    def from_config(cls, config: IntegrationConfig) -> "CrmOrganizationResolver":
        raw_mapping = config.crm_zapi_instance_organization_map_json
        if not raw_mapping:
            return cls({})
        try:
            parsed = json.loads(raw_mapping)
        except json.JSONDecodeError as exc:
            raise CrmConfigurationError("CRM Z-API instance mapping must be valid JSON") from exc
        if (
            not isinstance(parsed, dict)
            or not parsed
            or not all(isinstance(key, str) and key.strip() and isinstance(value, str) and value.strip() for key, value in parsed.items())
        ):
            raise CrmConfigurationError("CRM Z-API instance mapping must be a non-empty object of non-empty string pairs")
        return cls(parsed)

    def resolve(self, *, instance_id: str, payload: Mapping[str, Any] | None = None) -> str:
        # Payload is accepted only to make the boundary explicit: it must never
        # influence CRM organization selection.
        del payload
        try:
            return self._mapping[instance_id]
        except KeyError as exc:
            raise UnknownCrmInstanceError("Z-API instance is not mapped to a CRM organization") from exc

    @property
    def has_mappings(self) -> bool:
        return bool(self._mapping)


class InboundMessageResult(dict[str, Any]):
    """JSON-serializable inbound result while keeping convenient attributes."""

    def __init__(self, *, message_id: str | None, inserted: bool):
        super().__init__(message_id=message_id, inserted=inserted)

    @property
    def message_id(self) -> str | None:
        return self["message_id"]

    @property
    def inserted(self) -> bool:
        return bool(self["inserted"])


class CrmConversationRepository:
    def __init__(self, *, transport: CrmRestTransport, base_url: str | None = None, service_role_key: str | None = None):
        self.transport = transport
        self.base_url = (base_url or "").rstrip("/")
        self._service_role_key = service_role_key

    @classmethod
    def from_config(
        cls, config: IntegrationConfig, *, transport: CrmRestTransport | None = None
    ) -> "CrmConversationRepository":
        if not config.crm_supabase_url or not config.crm_supabase_service_role_key:
            raise CrmConfigurationError("CRM Supabase URL and service-role key are required")
        return cls(
            transport=transport or UrllibPostgrestTransport(config.crm_supabase_url),
            base_url=config.crm_supabase_url,
            service_role_key=config.crm_supabase_service_role_key,
        )

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self._service_role_key:
            headers.update({"apikey": self._service_role_key, "Authorization": f"Bearer {self._service_role_key}"})
        if prefer:
            headers["Prefer"] = prefer
        return headers

    @staticmethod
    def _first(response: Any) -> dict[str, Any] | None:
        if isinstance(response, list):
            return response[0] if response else None
        return response if isinstance(response, dict) else None

    def resolve_or_create_conversation(
        self,
        *,
        organization_id: str,
        channel: str,
        external_conversation_id: str,
        phone_number: str | None = None,
    ) -> dict[str, Any]:
        existing = self.find_conversation(
            organization_id=organization_id,
            channel=channel,
            external_conversation_id=external_conversation_id,
        )
        if existing:
            return existing

        try:
            response = self.transport.request(
                "POST",
                "/ai_conversations",
                headers=self._headers(prefer="return=representation"),
                payload={
                    "organization_id": organization_id,
                    "channel": channel,
                    "external_conversation_id": external_conversation_id,
                    # This is deliberately independent from the scoped
                    # provider identity. The CRM contract uses it to display
                    # the canonical WhatsApp number, not to find a row.
                    "phone_number": phone_number,
                    "mode": "ai",
                    "status": "AI_ACTIVE",
                },
            )
        except CrmRestConflictError:
            # The unique index is partial, so PostgREST cannot infer it from
            # on_conflict columns.  Re-read the row that won this insert race
            # without changing its persisted human/AI state.
            conversation = self.find_conversation(
                organization_id=organization_id,
                channel=channel,
                external_conversation_id=external_conversation_id,
            )
            if conversation and conversation.get("id"):
                return conversation
            raise CrmRestError("CRM conversation conflict could not be resolved")
        conversation = self._first(response)
        if conversation and conversation.get("id"):
            return conversation
        raise CrmRestError("CRM conversation insert did not return a conversation")

    def find_conversation(
        self, *, organization_id: str, channel: str, external_conversation_id: str
    ) -> dict[str, Any] | None:
        return self._first(
            self.transport.request(
                "GET",
                "/ai_conversations",
                headers=self._headers(),
                params={
                    "organization_id": f"eq.{organization_id}",
                    "channel": f"eq.{channel}",
                    "external_conversation_id": f"eq.{external_conversation_id}",
                    "select": "*",
                },
            )
        )

    def current_mode(self, *, organization_id: str, conversation_id: str) -> str | None:
        conversation = self._first(
            self.transport.request(
                "GET",
                "/ai_conversations",
                headers=self._headers(),
                params={"id": f"eq.{conversation_id}", "organization_id": f"eq.{organization_id}", "select": "mode"},
            )
        )
        return str(conversation["mode"]) if conversation and conversation.get("mode") else None

    def record_inbound_message(
        self,
        *,
        organization_id: str,
        conversation_id: str,
        external_message_id: str,
        content: str,
        occurred_at: str,
        message_type: str = "text",
    ) -> InboundMessageResult:
        try:
            response = self.transport.request(
                "POST",
                "/ai_messages",
                headers=self._headers(prefer="return=representation"),
                payload={
                    "organization_id": organization_id,
                    "conversation_id": conversation_id,
                    "external_message_id": external_message_id,
                    "direction": "inbound",
                    "sender_type": "customer",
                    "content": content,
                    "message_type": message_type,
                    "sent_at": occurred_at,
                },
            )
        except CrmRestConflictError:
            existing = self.find_inbound_message(
                organization_id=organization_id,
                external_message_id=external_message_id,
            )
            if existing and existing.get("id") and str(existing.get("conversation_id")) == str(conversation_id):
                return InboundMessageResult(message_id=str(existing["id"]), inserted=False)
            raise CrmRestError("CRM inbound message conflict could not be resolved")
        message = self._first(response)
        inserted = bool(message and message.get("id"))
        if not inserted:
            raise CrmRestError("CRM inbound message insert did not return a message")
        self.update_conversation(
            organization_id=organization_id,
            conversation_id=conversation_id,
            payload={
                "last_message_at": occurred_at,
                "last_customer_message_at": occurred_at,
                "updated_at": occurred_at,
            },
        )
        return InboundMessageResult(message_id=message.get("id") if message else None, inserted=True)

    def find_inbound_message(self, *, organization_id: str, external_message_id: str) -> dict[str, Any] | None:
        return self._first(
            self.transport.request(
                "GET",
                "/ai_messages",
                headers=self._headers(),
                params={
                    "organization_id": f"eq.{organization_id}",
                    "external_message_id": f"eq.{external_message_id}",
                    "select": "id,conversation_id",
                },
            )
        )

    def record_event(
        self,
        *,
        organization_id: str,
        conversation_id: str,
        event_type: str,
        occurred_at: str,
        severity: str = "info",
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        payload: dict[str, Any] = {
            "organization_id": organization_id,
            "conversation_id": conversation_id,
            "event_type": event_type,
            "severity": severity,
            "metadata_json": dict(metadata or {}),
            "created_at": occurred_at,
        }
        return self._first(self.transport.request("POST", "/ai_events", headers=self._headers(), payload=payload))

    def update_conversation(self, *, organization_id: str, conversation_id: str, payload: Mapping[str, Any]) -> Any:
        return self.transport.request(
            "PATCH",
            "/ai_conversations",
            headers=self._headers(),
            params={"id": f"eq.{conversation_id}", "organization_id": f"eq.{organization_id}"},
            payload=payload,
        )

    def create_outbound_message(self, *, organization_id: str, conversation_id: str, content: str) -> dict[str, Any] | None:
        return self._first(
            self.transport.request(
                "POST",
                "/ai_messages",
                headers=self._headers(prefer="return=representation"),
                payload={
                    "organization_id": organization_id,
                    "conversation_id": conversation_id,
                    "direction": "outbound",
                    "sender_type": "ai",
                    "content": content,
                    "message_type": "text",
                    "delivery_status": "pending_external_delivery",
                },
            )
        )

    def update_message(self, *, organization_id: str, message_id: str, payload: Mapping[str, Any]) -> Any:
        return self.transport.request(
            "PATCH",
            "/ai_messages",
            headers=self._headers(),
            params={"id": f"eq.{message_id}", "organization_id": f"eq.{organization_id}"},
            payload=payload,
        )


class CrmConversationMonitor:
    def __init__(self, *, repository: CrmConversationRepository, organization_resolver: CrmOrganizationResolver | None = None):
        self.repository = repository
        self.organization_resolver = organization_resolver

    def process_inbound(
        self,
        *,
        instance_id: str,
        external_conversation_id: str,
        external_message_id: str,
        content: str,
        occurred_at: str,
        phone_number: str | None = None,
        start_automation: Callable[[dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        if not self.organization_resolver:
            raise CrmConfigurationError("CRM organization resolver is required for inbound monitoring")
        organization_id = self.organization_resolver.resolve(instance_id=instance_id)
        conversation = self.repository.resolve_or_create_conversation(
            organization_id=organization_id,
            channel="whatsapp",
            external_conversation_id=scoped_crm_conversation_identity(instance_id, external_conversation_id),
            phone_number=phone_number,
        )
        inbound = self.repository.record_inbound_message(
            organization_id=organization_id,
            conversation_id=conversation["id"],
            external_message_id=external_message_id,
            content=content,
            occurred_at=occurred_at,
        )
        if not inbound.inserted:
            return {"accepted": True, "duplicate": True, "automation_started": False}
        self.repository.record_event(
            organization_id=organization_id,
            conversation_id=conversation["id"],
            event_type="MESSAGE_RECEIVED",
            occurred_at=occurred_at,
        )
        if conversation.get("mode") != "ai":
            return {"accepted": True, "duplicate": False, "automation_started": False}
        if start_automation:
            start_automation(conversation)
        return {"accepted": True, "duplicate": False, "automation_started": bool(start_automation)}

    def current_mode(self, *, organization_id: str, conversation_id: str) -> str | None:
        return self.repository.current_mode(organization_id=organization_id, conversation_id=conversation_id)

    def prepare_inbound(
        self,
        *,
        instance_id: str,
        external_conversation_id: str,
        external_message_id: str,
        content: str,
        occurred_at: str,
        message_type: str = "text",
        phone_number: str | None = None,
        batch_messages: list[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Persist one logical inbound and read the authoritative CRM mode.

        This deliberately does not invoke automation: the channel adapter owns
        that boundary so an error here can fail closed before its runtime or
        provider is touched.
        """
        if not self.organization_resolver:
            raise CrmConfigurationError("CRM organization resolver is required for inbound monitoring")
        organization_id = self.organization_resolver.resolve(instance_id=instance_id)
        conversation = self.repository.resolve_or_create_conversation(
            organization_id=organization_id,
            channel="whatsapp",
            external_conversation_id=scoped_crm_conversation_identity(instance_id, external_conversation_id),
            phone_number=phone_number,
        )
        constituents = batch_messages or [
            {
                "external_message_id": external_message_id,
                "content": content,
                "occurred_at": occurred_at,
                "message_type": message_type,
            }
        ]
        inserted_any = False
        for constituent in constituents:
            inbound = self.repository.record_inbound_message(
                organization_id=organization_id,
                conversation_id=conversation["id"],
                external_message_id=str(constituent["external_message_id"]),
                content=str(constituent.get("content") or ""),
                occurred_at=str(constituent.get("occurred_at") or occurred_at),
                message_type=str(constituent.get("message_type") or message_type),
            )
            if not inbound.inserted:
                continue
            inserted_any = True
            self.repository.record_event(
                organization_id=organization_id,
                conversation_id=conversation["id"],
                event_type="MESSAGE_RECEIVED",
                occurred_at=str(constituent.get("occurred_at") or occurred_at),
            )
        if not inserted_any:
            return {
                "organization_id": organization_id,
                "conversation_id": conversation["id"],
                "duplicate": True,
                "mode": None,
            }
        return {
            "organization_id": organization_id,
            "conversation_id": conversation["id"],
            "duplicate": False,
            # Never reuse the mode read while creating the conversation: an
            # operator may have changed it in the meantime.
            "mode": self.current_mode(organization_id=organization_id, conversation_id=conversation["id"]),
        }

    def deliver_ai_response(
        self,
        *,
        organization_id: str,
        conversation_id: str,
        content: str,
        occurred_at: str,
        send_outbound: Callable[[str], Mapping[str, Any]],
        provider: str = "zapi",
        attempt: int = 1,
    ) -> dict[str, Any]:
        outbound = self.repository.create_outbound_message(
            organization_id=organization_id, conversation_id=conversation_id, content=content
        )
        if not outbound or not outbound.get("id"):
            raise CrmRestError("CRM outbound message insert did not return a message")
        try:
            delivery = send_outbound(content)
            sent_at = str(delivery.get("sent_at") or occurred_at)
            self.repository.update_message(
                organization_id=organization_id,
                message_id=str(outbound["id"]),
                payload={
                    "delivery_status": "sent",
                    "external_message_id": delivery.get("external_message_id"),
                    "sent_at": sent_at,
                },
            )
            self.repository.update_conversation(
                organization_id=organization_id,
                conversation_id=conversation_id,
                payload={"last_message_at": sent_at, "last_ai_message_at": sent_at, "updated_at": sent_at},
            )
            self.repository.record_event(
                organization_id=organization_id,
                conversation_id=conversation_id,
                event_type="AI_RESPONSE_COMPLETED",
                occurred_at=sent_at,
            )
            return {"delivery_status": "sent", "external_message_id": delivery.get("external_message_id"), "sent_at": sent_at}
        except Exception as exc:
            safe_error = sanitize_crm_error(exc)
            self.repository.update_message(
                organization_id=organization_id, message_id=str(outbound["id"]), payload={"delivery_status": "failed"}
            )
            self.repository.record_event(
                organization_id=organization_id,
                conversation_id=conversation_id,
                event_type="AI_RESPONSE_FAILED",
                occurred_at=occurred_at,
                severity="error",
                metadata={
                    "attempt": attempt,
                    "provider": provider,
                    "error_code": safe_error["code"],
                    "error_type": safe_error["type"],
                    "safe_message": safe_error["message"],
                },
            )
            return {"delivery_status": "failed"}

    def request_handoff(
        self,
        *,
        organization_id: str,
        conversation_id: str,
        reason: str,
        occurred_at: str,
        origin: str = "ai",
    ) -> None:
        self.repository.update_conversation(
            organization_id=organization_id,
            conversation_id=conversation_id,
            payload={
                "handoff_requested": True,
                "handoff_reason": reason,
                # The live CRM schema uses handoff_requested_by (not the old
                # handoff_origin name retained by a stale test fixture).
                "handoff_requested_by": origin,
                "handoff_requested_at": occurred_at,
                "status": "HANDOFF_REQUESTED",
                "mode": "human",
                "updated_at": occurred_at,
            },
        )
        self.repository.record_event(
            organization_id=organization_id,
            conversation_id=conversation_id,
            event_type="HANDOFF_REQUESTED",
            occurred_at=occurred_at,
        )


_SECRET_KEY_RE = re.compile(r"(?:authorization|api[_-]?key|token|secret|password|credential|jwt)", re.IGNORECASE)
_URL_CREDENTIAL_RE = re.compile(r"(?:postgres(?:ql)?|https?)://[^\s]+", re.IGNORECASE)
_BEARER_RE = re.compile(r"bearer\s+[a-z0-9._-]+", re.IGNORECASE)
_KEY_VALUE_RE = re.compile(r"\b(?:token|secret|password|api[_-]?key)\s*=\s*[^\s,;]+", re.IGNORECASE)


def _safe_message(value: Any) -> str:
    message = str(value)
    if _SECRET_KEY_RE.search(message) or _URL_CREDENTIAL_RE.search(message) or _BEARER_RE.search(message):
        return "CRM integration error"
    return _KEY_VALUE_RE.sub("[REDACTED]", message)


def _sanitize_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if _SECRET_KEY_RE.search(str(key)):
            continue
        if isinstance(value, Mapping):
            safe[str(key)] = _sanitize_metadata(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe[str(key)] = _safe_message(value) if isinstance(value, str) else value
    return safe


def sanitize_crm_error(error_value: Exception, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return diagnostic data fit for logs/events without credentials or URLs."""
    return {
        "code": error_value.__class__.__name__,
        "type": error_value.__class__.__name__,
        "message": _safe_message(error_value),
        "metadata": _sanitize_metadata(metadata or {}),
    }


def scoped_crm_conversation_identity(instance_id: str, canonical_contact: str) -> str:
    """Return the collision-safe CRM identity for one Z-API contact.

    CRM organizations can own multiple Z-API instances. Percent encoding each
    component makes the instance/contact boundary unambiguous even when an
    upstream identifier itself contains punctuation. `phone_number` remains a
    separate display/contact field and is never used as the CRM row identity.
    """
    return "zapi:" + parse.quote(str(instance_id), safe="") + ":" + parse.quote(str(canonical_contact), safe="")
