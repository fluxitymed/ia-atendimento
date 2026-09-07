from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from os import environ
from typing import Any
from urllib import parse, request

from ai_agent_runtime.integrations.config import load_env_file

from .channel import MediaReference, WhatsAppProvider


class EvolutionApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class EvolutionInstanceBinding:
    organization_id: str
    instance_name: str


@dataclass(frozen=True)
class EvolutionWhatsAppConfig:
    provider: str = "evolution"
    base_url: str | None = None
    api_key: str | None = None
    instance_name: str | None = None
    webhook_secret: str | None = None
    public_webhook_url: str | None = None
    organization_id: str = "sandbox-org-aurora"

    @classmethod
    def from_env(cls) -> "EvolutionWhatsAppConfig":
        load_env_file()
        return cls(
            provider=environ.get("WHATSAPP_PROVIDER", cls.provider),
            base_url=environ.get("EVOLUTION_API_BASE_URL"),
            api_key=environ.get("EVOLUTION_API_KEY"),
            instance_name=environ.get("EVOLUTION_INSTANCE_NAME"),
            webhook_secret=environ.get("EVOLUTION_WEBHOOK_SECRET"),
            public_webhook_url=environ.get("EVOLUTION_PUBLIC_WEBHOOK_URL"),
            organization_id=environ.get("EVOLUTION_ORGANIZATION_ID", cls.organization_id),
        )

    def missing_for_live(self) -> list[str]:
        missing = []
        for key, value in (
            ("EVOLUTION_API_BASE_URL", self.base_url),
            ("EVOLUTION_API_KEY", self.api_key),
            ("EVOLUTION_INSTANCE_NAME", self.instance_name),
            ("EVOLUTION_WEBHOOK_SECRET", self.webhook_secret),
            ("EVOLUTION_PUBLIC_WEBHOOK_URL", self.public_webhook_url),
        ):
            if not value:
                missing.append(key)
        return missing

    def binding(self) -> EvolutionInstanceBinding:
        if not self.instance_name:
            raise EvolutionApiError("EVOLUTION_INSTANCE_NAME is required")
        return EvolutionInstanceBinding(organization_id=self.organization_id, instance_name=self.instance_name)


class EvolutionTransport:
    def request_json(
        self,
        method: str,
        path: str,
        *,
        base_url: str,
        api_key: str,
        payload: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        url = f"{base_url.rstrip('/')}{path}"
        if query:
            url = f"{url}?{parse.urlencode(query)}"
        req = request.Request(
            url,
            data=body,
            headers={"apikey": api_key, "Content-Type": "application/json"},
            method=method,
        )
        try:
            with request.urlopen(req, timeout=30) as response:
                response_body = response.read().decode("utf-8")
                return json.loads(response_body) if response_body else {}
        except Exception as exc:
            raise EvolutionApiError(redact_evolution_secret(str(exc), api_key)) from exc

    def get_bytes(self, url: str, *, api_key: str) -> bytes:
        req = request.Request(url, headers={"apikey": api_key}, method="GET")
        try:
            with request.urlopen(req, timeout=30) as response:
                return response.read()
        except Exception as exc:
            raise EvolutionApiError(redact_evolution_secret(str(exc), api_key)) from exc


class EvolutionWhatsAppProvider(WhatsAppProvider):
    def __init__(self, *, config: EvolutionWhatsAppConfig, transport: EvolutionTransport | None = None):
        self.config = config
        self.transport = transport or EvolutionTransport()

    def send_text(self, *, organization_id: str, contact_external_id: str, text: str, conversation_id: str) -> dict[str, Any]:
        payload = {"number": contact_external_id, "text": text}
        response = self._request("POST", f"/message/sendText/{self._instance_name()}", payload=payload)
        return {
            "provider": "evolution",
            "providerMessageId": _extract_message_id(response),
            "organizationId": organization_id,
            "contactExternalId": contact_external_id,
            "conversationId": conversation_id,
            "raw": response,
        }

    def send_media(self, *, organization_id: str, contact_external_id: str, media: MediaReference, caption: str | None = None) -> dict[str, Any]:
        payload = {
            "number": contact_external_id,
            "mediatype": str(media.metadata.get("type") or "document").lower(),
            "media": media.url or media.storage_reference or media.provider_media_id,
            **({"caption": caption} if caption else {}),
        }
        response = self._request("POST", f"/message/sendMedia/{self._instance_name()}", payload=payload)
        return {
            "provider": "evolution",
            "providerMessageId": _extract_message_id(response),
            "organizationId": organization_id,
            "contactExternalId": contact_external_id,
            "mediaReference": media.provider_media_id,
            "raw": response,
        }

    def download_media(self, *, organization_id: str, media: MediaReference) -> bytes:
        if media.metadata.get("base64"):
            return base64.b64decode(str(media.metadata["base64"]), validate=True)
        if media.url:
            return self.transport.get_bytes(media.url, api_key=self._api_key())
        raise EvolutionApiError("EVOLUTION_MEDIA_SOURCE_MISSING")

    def mark_as_read(self, *, organization_id: str, provider_message_id: str) -> dict[str, Any]:
        return {
            "provider": "evolution",
            "providerMessageId": provider_message_id,
            "read": "NOT_SUPPORTED_OFFLINE",
            "organizationId": organization_id,
        }

    def connection_state(self) -> dict[str, Any]:
        return self._request("GET", f"/instance/connectionState/{self._instance_name()}")

    def create_instance(self) -> dict[str, Any]:
        payload = {"instanceName": self._instance_name(), "qrcode": True}
        return self._request("POST", "/instance/create", payload=payload)

    def connect_instance(self) -> dict[str, Any]:
        return self._request("GET", f"/instance/connect/{self._instance_name()}")

    def set_webhook(self, *, webhook_url: str | None = None) -> dict[str, Any]:
        url = webhook_url or self.config.public_webhook_url
        if not url:
            raise EvolutionApiError("EVOLUTION_PUBLIC_WEBHOOK_URL is required")
        payload = {
            "webhook": {
                "enabled": True,
                "url": url,
                "headers": {"x-evolution-webhook-secret": self.config.webhook_secret or ""},
                "events": ["MESSAGES_UPSERT", "MESSAGES_UPDATE", "SEND_MESSAGE", "CONNECTION_UPDATE", "QRCODE_UPDATED"],
            }
        }
        return self._request("POST", f"/webhook/set/{self._instance_name()}", payload=payload)

    def _request(self, method: str, path: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.config.base_url:
            raise EvolutionApiError("EVOLUTION_API_BASE_URL is required")
        try:
            return self.transport.request_json(method, path, base_url=self.config.base_url, api_key=self._api_key(), payload=payload)
        except Exception as exc:
            raise EvolutionApiError(redact_evolution_secret(str(exc), self.config.api_key, self.config.webhook_secret)) from exc

    def _api_key(self) -> str:
        if not self.config.api_key:
            raise EvolutionApiError("EVOLUTION_API_KEY is required")
        return self.config.api_key

    def _instance_name(self) -> str:
        if not self.config.instance_name:
            raise EvolutionApiError("EVOLUTION_INSTANCE_NAME is required")
        return self.config.instance_name


def redact_evolution_secret(text: str, *secrets: str | None) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED_SECRET]")
    lowered = redacted.lower()
    if "apikey" in lowered or "api key" in lowered or "authorization" in lowered:
        return "Evolution API request failed"
    return redacted


def _extract_message_id(response: dict[str, Any]) -> str | None:
    for path in (
        ("key", "id"),
        ("message", "key", "id"),
        ("data", "key", "id"),
        ("id",),
    ):
        value: Any = response
        for key in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        if value:
            return str(value)
    return None
