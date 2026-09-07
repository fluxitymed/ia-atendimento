from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from os import environ
from pathlib import Path
from typing import Any
from urllib import parse, request

from ai_agent_runtime.integrations.config import load_env_file
from ai_agent_runtime.sandbox_ids import PRIMARY_SANDBOX_ORG_ID

from .channel import MediaReference, WhatsAppProvider


class ZApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class ZApiInstanceBinding:
    organization_id: str
    instance_id: str


@dataclass(frozen=True)
class ZApiWhatsAppConfig:
    provider: str = "zapi"
    base_url: str | None = None
    instance_id: str | None = None
    instance_token: str | None = None
    client_token: str | None = None
    public_webhook_url: str | None = None
    organization_id: str = PRIMARY_SANDBOX_ORG_ID
    media_download_timeout_seconds: int = 30
    media_max_bytes: int = 20 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "ZApiWhatsAppConfig":
        load_env_file()
        return cls(
            provider=environ.get("WHATSAPP_PROVIDER", cls.provider),
            base_url=environ.get("ZAPI_BASE_URL"),
            instance_id=environ.get("ZAPI_INSTANCE_ID"),
            instance_token=environ.get("ZAPI_INSTANCE_TOKEN"),
            client_token=environ.get("ZAPI_CLIENT_TOKEN"),
            public_webhook_url=environ.get("ZAPI_PUBLIC_WEBHOOK_URL"),
            organization_id=environ.get("ZAPI_ORGANIZATION_ID", cls.organization_id),
            media_download_timeout_seconds=int(environ.get("AUDIO_DOWNLOAD_TIMEOUT_SECONDS", str(cls.media_download_timeout_seconds))),
            media_max_bytes=int(environ.get("AUDIO_MAX_BYTES", str(cls.media_max_bytes))),
        )

    def missing_for_live(self) -> list[str]:
        missing = []
        for key, value in (
            ("ZAPI_BASE_URL", self.base_url),
            ("ZAPI_INSTANCE_ID", self.instance_id),
            ("ZAPI_INSTANCE_TOKEN", self.instance_token),
            ("ZAPI_CLIENT_TOKEN", self.client_token),
            ("ZAPI_PUBLIC_WEBHOOK_URL", self.public_webhook_url),
        ):
            if not value:
                missing.append(key)
        return missing

    def binding(self) -> ZApiInstanceBinding:
        if not self.instance_id:
            raise ZApiError("ZAPI_INSTANCE_ID is required")
        return ZApiInstanceBinding(organization_id=self.organization_id, instance_id=self.instance_id)


class ZApiTransport:
    def request_json(
        self,
        method: str,
        path: str,
        *,
        base_url: str,
        client_token: str,
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
            headers={"Client-Token": client_token, "Content-Type": "application/json"},
            method=method,
        )
        try:
            with request.urlopen(req, timeout=30) as response:
                response_body = response.read().decode("utf-8")
                return json.loads(response_body) if response_body else {}
        except Exception as exc:
            raise ZApiError(redact_zapi_secret(str(exc), client_token)) from exc

    def get_bytes(self, url: str, *, client_token: str, timeout_seconds: int = 30, max_bytes: int = 20 * 1024 * 1024) -> bytes:
        req = request.Request(url, headers={"Client-Token": client_token}, method="GET")
        try:
            with request.urlopen(req, timeout=timeout_seconds) as response:
                data = response.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise ZApiError("ZAPI_MEDIA_TOO_LARGE")
                return data
        except Exception as exc:
            raise ZApiError(redact_zapi_secret(str(exc), client_token)) from exc


class ZApiWhatsAppProvider(WhatsAppProvider):
    def __init__(self, *, config: ZApiWhatsAppConfig, transport: ZApiTransport | None = None):
        self.config = config
        self.transport = transport or ZApiTransport()

    def send_text(self, *, organization_id: str, contact_external_id: str, text: str, conversation_id: str) -> dict[str, Any]:
        payload = {"phone": contact_external_id, "message": text}
        response = self._request("POST", "/send-text", payload=payload)
        return {
            "provider": "zapi",
            "providerMessageId": _extract_zapi_message_id(response),
            "organizationId": organization_id,
            "contactExternalId": contact_external_id,
            "conversationId": conversation_id,
            "raw": response,
        }

    def send_media(self, *, organization_id: str, contact_external_id: str, media: MediaReference, caption: str | None = None) -> dict[str, Any]:
        media_type = str(media.metadata.get("type") or "document").lower()
        media_value = media.url or media.storage_reference or media.provider_media_id
        if media_type == "image":
            response = self._request(
                "POST",
                "/send-image",
                payload={"phone": contact_external_id, "image": media_value, **({"caption": caption} if caption else {})},
            )
        elif media_type == "audio":
            response = self._request("POST", "/send-audio", payload={"phone": contact_external_id, "audio": media_value})
        else:
            extension = _document_extension(media)
            response = self._request(
                "POST",
                f"/send-document/{extension}",
                payload={
                    "phone": contact_external_id,
                    "document": media_value,
                    **({"fileName": media.metadata.get("fileName")} if media.metadata.get("fileName") else {}),
                    **({"caption": caption} if caption else {}),
                },
            )
        return {
            "provider": "zapi",
            "providerMessageId": _extract_zapi_message_id(response),
            "organizationId": organization_id,
            "contactExternalId": contact_external_id,
            "mediaReference": media.provider_media_id,
            "raw": response,
        }

    def download_media(self, *, organization_id: str, media: MediaReference) -> bytes:
        raw_base64 = media.metadata.get("base64")
        if raw_base64:
            value = str(raw_base64)
            if "," in value and value.strip().startswith("data:"):
                value = value.split(",", 1)[1]
            data = base64.b64decode(value, validate=True)
            if len(data) > self.config.media_max_bytes:
                raise ZApiError("ZAPI_MEDIA_TOO_LARGE")
            return data
        if media.url:
            if not media.url.startswith("https://"):
                raise ZApiError("ZAPI_MEDIA_URL_MUST_BE_HTTPS")
            try:
                return self.transport.get_bytes(
                    media.url,
                    client_token=self._client_token(),
                    timeout_seconds=self.config.media_download_timeout_seconds,
                    max_bytes=self.config.media_max_bytes,
                )
            except TypeError:
                return self.transport.get_bytes(media.url, client_token=self._client_token())
        raise ZApiError("ZAPI_MEDIA_SOURCE_MISSING")

    def mark_as_read(self, *, organization_id: str, provider_message_id: str) -> dict[str, Any]:
        return {
            "provider": "zapi",
            "providerMessageId": provider_message_id,
            "read": "NOT_SUPPORTED_OFFLINE",
            "organizationId": organization_id,
        }

    def instance_status(self) -> dict[str, Any]:
        return self._request("GET", "/status")

    def qr_code(self) -> dict[str, Any]:
        return self._request("GET", "/qr-code")

    def set_received_webhook(self, *, webhook_url: str | None = None) -> dict[str, Any]:
        url = webhook_url or self.config.public_webhook_url
        if not url:
            raise ZApiError("ZAPI_PUBLIC_WEBHOOK_URL is required")
        return self._request("PUT", "/update-webhook-received", payload={"value": url})

    def _request(self, method: str, action_path: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.config.base_url:
            raise ZApiError("ZAPI_BASE_URL is required")
        try:
            return self.transport.request_json(
                method,
                f"{self._instance_path()}{action_path}",
                base_url=self.config.base_url,
                client_token=self._client_token(),
                payload=payload,
            )
        except Exception as exc:
            raise ZApiError(redact_zapi_secret(str(exc), self.config.instance_token, self.config.client_token)) from exc

    def _instance_path(self) -> str:
        if not self.config.instance_id:
            raise ZApiError("ZAPI_INSTANCE_ID is required")
        if not self.config.instance_token:
            raise ZApiError("ZAPI_INSTANCE_TOKEN is required")
        return f"/instances/{self.config.instance_id}/token/{self.config.instance_token}"

    def _client_token(self) -> str:
        if not self.config.client_token:
            raise ZApiError("ZAPI_CLIENT_TOKEN is required")
        return self.config.client_token


def redact_zapi_secret(text: str, *secrets: str | None) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED_SECRET]")
    redacted = _redact_token_path(redacted)
    lowered = redacted.lower()
    if "client-token" in lowered or "authorization" in lowered or "instance_token" in lowered:
        return "Z-API request failed"
    return redacted


def safe_zapi_result(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            lowered = key.lower()
            if "token" in lowered or "secret" in lowered:
                redacted[key] = "[REDACTED_SECRET]"
            elif key == "value" and isinstance(item, str) and item.startswith("data:image/"):
                redacted[key] = "[REDACTED_QR_CODE]"
            else:
                redacted[key] = safe_zapi_result(item)
        return redacted
    if isinstance(value, list):
        return [safe_zapi_result(item) for item in value]
    if isinstance(value, str):
        return redact_zapi_secret(value)
    return value


def _redact_token_path(text: str) -> str:
    marker = "/token/"
    if marker not in text:
        return text
    parts = text.split(marker)
    safe = [parts[0]]
    for tail in parts[1:]:
        token, sep, rest = tail.partition("/")
        safe.append(f"{marker}[REDACTED_SECRET]{sep}{rest}")
    return "".join(safe)


def _extract_zapi_message_id(response: dict[str, Any]) -> str | None:
    for key in ("messageId", "id", "zaapId"):
        value = response.get(key)
        if value:
            return str(value)
    for key in ("data", "message"):
        nested = response.get(key)
        if isinstance(nested, dict):
            value = _extract_zapi_message_id(nested)
            if value:
                return value
    return None


def _document_extension(media: MediaReference) -> str:
    file_name = str(media.metadata.get("fileName") or "")
    if "." in file_name:
        extension = file_name.rsplit(".", 1)[1].lower()
        if extension:
            return extension
    mime_type = str(media.metadata.get("mimeType") or "")
    by_mime = {"application/pdf": "pdf", "text/plain": "txt", "text/markdown": "md"}
    if mime_type in by_mime:
        return by_mime[mime_type]
    storage = media.storage_reference or media.url or media.provider_media_id
    suffix = Path(str(storage)).suffix.lstrip(".").lower()
    return suffix or "pdf"
