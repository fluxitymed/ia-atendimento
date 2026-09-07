from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Any

from .adapter import WhatsAppChannelAdapter
from .channel import ChannelRecord
from .meta import MetaWhatsAppConfig


WEBHOOK_PATH = "/webhooks/meta/whatsapp"


@dataclass(frozen=True)
class WebhookResponse:
    status_code: int
    body: str
    headers: dict[str, str] = field(default_factory=lambda: {"Content-Type": "text/plain"})


class MetaWebhookError(ValueError):
    pass


def verify_webhook_get(query: dict[str, str], config: MetaWhatsAppConfig) -> WebhookResponse:
    mode = query.get("hub.mode")
    token = query.get("hub.verify_token")
    challenge = query.get("hub.challenge")
    if mode == "subscribe" and token and token == config.verify_token and challenge:
        return WebhookResponse(status_code=200, body=challenge)
    return WebhookResponse(status_code=403, body="Forbidden")


def validate_meta_signature(raw_body: bytes, signature_header: str | None, app_secret: str | None) -> bool:
    if not app_secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    received = signature_header.split("=", 1)[1]
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(received, expected)


def parse_meta_webhook_payload(raw_body: bytes) -> list[dict[str, Any]]:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise MetaWebhookError("INVALID_JSON") from exc
    if payload.get("object") != "whatsapp_business_account":
        raise MetaWebhookError("UNSUPPORTED_OBJECT")

    events: list[dict[str, Any]] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            metadata = value.get("metadata", {})
            provider_account_id = metadata.get("phone_number_id")
            for status in value.get("statuses", []):
                events.append({
                    "providerAccountId": provider_account_id,
                    "providerMessageId": status.get("id"),
                    "contactExternalId": status.get("recipient_id") or "",
                    "type": "TEXT",
                    "text": "",
                    "timestamp": status.get("timestamp"),
                    "fromSelf": True,
                    "metadata": {"metaStatus": status.get("status"), "changeField": change.get("field")},
                })
            for message in value.get("messages", []):
                events.append(_parse_meta_message(message, provider_account_id, change.get("field")))
    return [event for event in events if event.get("providerAccountId") and event.get("providerMessageId")]


def handle_meta_webhook_post(
    *,
    raw_body: bytes,
    headers: dict[str, str],
    config: MetaWhatsAppConfig,
    adapter: WhatsAppChannelAdapter,
) -> tuple[WebhookResponse, list[ChannelRecord]]:
    signature = _header(headers, "x-hub-signature-256")
    if not validate_meta_signature(raw_body, signature, config.app_secret):
        return WebhookResponse(status_code=403, body="Invalid signature"), []
    try:
        events = parse_meta_webhook_payload(raw_body)
    except MetaWebhookError as exc:
        return WebhookResponse(status_code=400, body=str(exc)), []

    records = []
    for event in events:
        records.append(adapter.process_event(event))
    return WebhookResponse(status_code=200, body="EVENT_RECEIVED"), records


def _parse_meta_message(message: dict[str, Any], provider_account_id: str | None, change_field: str | None) -> dict[str, Any]:
    message_type = str(message.get("type", "")).upper()
    base = {
        "providerAccountId": provider_account_id,
        "providerMessageId": message.get("id"),
        "contactExternalId": message.get("from"),
        "type": message_type,
        "timestamp": message.get("timestamp"),
        "metadata": {
            "changeField": change_field,
            "metaMessageType": message.get("type"),
            "context": message.get("context"),
        },
    }
    if message_type == "TEXT":
        return {**base, "text": message.get("text", {}).get("body")}
    if message_type in {"AUDIO", "IMAGE", "DOCUMENT"}:
        media = message.get(message.get("type"), {})
        return {
            **base,
            "mimeType": media.get("mime_type"),
            "fileName": media.get("filename"),
            "media": {
                "providerMediaId": media.get("id"),
                "sha256": media.get("sha256"),
                "storageReference": f"meta:{media.get('id')}" if media.get("id") else None,
                "metadata": {
                    "provider": "meta_cloud",
                    "mediaType": message.get("type"),
                    "voice": media.get("voice"),
                },
            },
        }
    raise MetaWebhookError(f"UNSUPPORTED_MESSAGE_TYPE:{message.get('type')}")


def _header(headers: dict[str, str], key: str) -> str | None:
    lowered = {name.lower(): value for name, value in headers.items()}
    return lowered.get(key.lower())
