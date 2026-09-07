from __future__ import annotations

import json
from dataclasses import dataclass
from os import environ
from typing import Any
from urllib import parse, request

from ai_agent_runtime.integrations.config import load_env_file

from .channel import MediaReference, WhatsAppProvider


DEFAULT_META_API_VERSION = "v23.0"


@dataclass(frozen=True)
class MetaWhatsAppConfig:
    provider: str = "meta_cloud"
    access_token: str | None = None
    phone_number_id: str | None = None
    business_account_id: str | None = None
    verify_token: str | None = None
    app_secret: str | None = None
    api_version: str = DEFAULT_META_API_VERSION
    public_webhook_url: str | None = None

    @classmethod
    def from_env(cls) -> "MetaWhatsAppConfig":
        load_env_file()
        return cls(
            provider=environ.get("WHATSAPP_PROVIDER", cls.provider),
            access_token=environ.get("META_WHATSAPP_ACCESS_TOKEN"),
            phone_number_id=environ.get("META_WHATSAPP_PHONE_NUMBER_ID"),
            business_account_id=environ.get("META_WHATSAPP_BUSINESS_ACCOUNT_ID"),
            verify_token=environ.get("META_WHATSAPP_VERIFY_TOKEN"),
            app_secret=environ.get("META_WHATSAPP_APP_SECRET"),
            api_version=environ.get("META_WHATSAPP_API_VERSION", cls.api_version),
            public_webhook_url=environ.get("META_WHATSAPP_PUBLIC_WEBHOOK_URL"),
        )

    def missing_for_live(self) -> list[str]:
        missing = []
        for key, value in (
            ("META_WHATSAPP_ACCESS_TOKEN", self.access_token),
            ("META_WHATSAPP_PHONE_NUMBER_ID", self.phone_number_id),
            ("META_WHATSAPP_BUSINESS_ACCOUNT_ID", self.business_account_id),
            ("META_WHATSAPP_VERIFY_TOKEN", self.verify_token),
            ("META_WHATSAPP_APP_SECRET", self.app_secret),
            ("META_WHATSAPP_PUBLIC_WEBHOOK_URL", self.public_webhook_url),
        ):
            if not value:
                missing.append(key)
        return missing


class MetaWhatsAppApiError(RuntimeError):
    pass


class MetaGraphTransport:
    base_url = "https://graph.facebook.com"

    def request_json(self, method: str, path: str, *, access_token: str, payload: dict[str, Any] | None = None, query: dict[str, str] | None = None) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{parse.urlencode(query)}"
        req = request.Request(url, data=body, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=30) as response:
                response_body = response.read().decode("utf-8")
                return json.loads(response_body) if response_body else {}
        except Exception as exc:
            raise MetaWhatsAppApiError(_safe_error(exc)) from exc

    def get_bytes(self, url: str, *, access_token: str) -> bytes:
        req = request.Request(url, headers={"Authorization": f"Bearer {access_token}"}, method="GET")
        try:
            with request.urlopen(req, timeout=30) as response:
                return response.read()
        except Exception as exc:
            raise MetaWhatsAppApiError(_safe_error(exc)) from exc


class MetaWhatsAppCloudProvider(WhatsAppProvider):
    def __init__(self, *, config: MetaWhatsAppConfig, transport: MetaGraphTransport | None = None):
        self.config = config
        self.transport = transport or MetaGraphTransport()

    def send_text(self, *, organization_id: str, contact_external_id: str, text: str, conversation_id: str) -> dict[str, Any]:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": contact_external_id,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": text,
            },
        }
        response = self._post_messages(payload)
        message_id = _first_message_id(response)
        return {
            "provider": "meta_cloud",
            "providerMessageId": message_id,
            "organizationId": organization_id,
            "contactExternalId": contact_external_id,
            "conversationId": conversation_id,
            "raw": response,
        }

    def send_media(self, *, organization_id: str, contact_external_id: str, media: MediaReference, caption: str | None = None) -> dict[str, Any]:
        media_type = str(media.metadata.get("type") or "document")
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": contact_external_id,
            "type": media_type,
            media_type: {
                "id": media.provider_media_id,
                **({"caption": caption} if caption else {}),
            },
        }
        response = self._post_messages(payload)
        return {
            "provider": "meta_cloud",
            "providerMessageId": _first_message_id(response),
            "organizationId": organization_id,
            "contactExternalId": contact_external_id,
            "mediaReference": media.provider_media_id,
            "raw": response,
        }

    def download_media(self, *, organization_id: str, media: MediaReference) -> bytes:
        if not self.config.phone_number_id:
            raise MetaWhatsAppApiError("META_WHATSAPP_PHONE_NUMBER_ID is required")
        metadata = self.transport.request_json(
            "GET",
            f"/{self.config.api_version}/{media.provider_media_id}",
            access_token=self._access_token(),
            query={"phone_number_id": self.config.phone_number_id},
        )
        url = metadata.get("url")
        if not url:
            raise MetaWhatsAppApiError("Meta media URL missing from response")
        return self.transport.get_bytes(url, access_token=self._access_token())

    def mark_as_read(self, *, organization_id: str, provider_message_id: str) -> dict[str, Any]:
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": provider_message_id,
        }
        return self._post_messages(payload)

    def _post_messages(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.config.phone_number_id:
            raise MetaWhatsAppApiError("META_WHATSAPP_PHONE_NUMBER_ID is required")
        return self.transport.request_json(
            "POST",
            f"/{self.config.api_version}/{self.config.phone_number_id}/messages",
            access_token=self._access_token(),
            payload=payload,
        )

    def _access_token(self) -> str:
        if not self.config.access_token:
            raise MetaWhatsAppApiError("META_WHATSAPP_ACCESS_TOKEN is required")
        return self.config.access_token


def _first_message_id(response: dict[str, Any]) -> str | None:
    messages = response.get("messages")
    if isinstance(messages, list) and messages:
        return messages[0].get("id")
    return None


def _safe_error(exc: Exception) -> str:
    text = str(exc)
    if "access_token" in text.lower() or "bearer" in text.lower():
        return "Meta Graph API request failed"
    return text
