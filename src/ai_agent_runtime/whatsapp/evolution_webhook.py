from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .adapter import WhatsAppChannelAdapter
from .channel import ChannelRecord
from .evolution import EvolutionWhatsAppConfig, redact_evolution_secret


WEBHOOK_PATH = "/webhooks/evolution/whatsapp"


@dataclass(frozen=True)
class EvolutionWebhookResponse:
    status_code: int
    body: str
    headers: dict[str, str] = field(default_factory=lambda: {"Content-Type": "text/plain"})


class EvolutionWebhookError(ValueError):
    pass


def validate_evolution_webhook(headers: dict[str, str], config: EvolutionWhatsAppConfig) -> bool:
    if not config.webhook_secret:
        return True
    secret = _header(headers, "x-evolution-webhook-secret") or _header(headers, "x-webhook-secret")
    authorization = _header(headers, "authorization")
    if authorization and authorization.lower().startswith("bearer "):
        secret = authorization.split(" ", 1)[1]
    return secret == config.webhook_secret


def parse_evolution_webhook_payload(raw_body: bytes) -> list[dict[str, Any]]:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise EvolutionWebhookError("INVALID_JSON") from exc

    event_name = str(payload.get("event") or payload.get("type") or "").upper()
    instance = payload.get("instance") or payload.get("instanceName") or payload.get("server_url")
    data = payload.get("data") or payload

    if event_name and event_name not in {"MESSAGES_UPSERT", "MESSAGES_UPDATE", "SEND_MESSAGE"}:
        return []
    messages = data if isinstance(data, list) else data.get("messages") if isinstance(data, dict) else None
    if messages is None:
        messages = [data]
    if not isinstance(messages, list):
        raise EvolutionWebhookError("INVALID_MESSAGES")

    events = []
    for message in messages:
        if isinstance(message, dict):
            parsed = _parse_evolution_message(message, str(instance or ""))
            if parsed:
                events.append(parsed)
    return [event for event in events if event.get("providerAccountId") and event.get("providerMessageId")]


def handle_evolution_webhook_post(
    *,
    raw_body: bytes,
    headers: dict[str, str],
    config: EvolutionWhatsAppConfig,
    adapter: WhatsAppChannelAdapter,
) -> tuple[EvolutionWebhookResponse, list[ChannelRecord]]:
    if not validate_evolution_webhook(headers, config):
        return EvolutionWebhookResponse(status_code=403, body="Invalid webhook secret"), []
    try:
        events = parse_evolution_webhook_payload(raw_body)
    except EvolutionWebhookError as exc:
        return EvolutionWebhookResponse(status_code=400, body=str(exc)), []

    records: list[ChannelRecord] = []
    for event in events:
        try:
            records.append(adapter.process_event(event))
        except ValueError as exc:
            message = redact_evolution_secret(str(exc), config.webhook_secret, config.api_key)
            if message == "UNKNOWN_PROVIDER_ACCOUNT":
                return EvolutionWebhookResponse(status_code=403, body="UNKNOWN_INSTANCE"), records
            return EvolutionWebhookResponse(status_code=400, body=message), records
    return EvolutionWebhookResponse(status_code=200, body="EVENT_RECEIVED"), records


def _parse_evolution_message(message: dict[str, Any], instance: str) -> dict[str, Any] | None:
    key = message.get("key") if isinstance(message.get("key"), dict) else {}
    message_body = message.get("message") if isinstance(message.get("message"), dict) else {}
    raw_type = str(message.get("messageType") or _detect_message_type(message_body) or "").lower()
    message_id = key.get("id") or message.get("id") or message.get("messageId")
    remote_jid = key.get("remoteJid") or message.get("remoteJid") or message.get("from") or ""
    from_self = bool(key.get("fromMe") or message.get("fromMe"))
    contact = _normalize_remote_jid(str(remote_jid))
    timestamp = message.get("messageTimestamp") or message.get("timestamp")

    base = {
        "providerAccountId": instance or message.get("instance") or message.get("instanceName"),
        "providerMessageId": message_id,
        "contactExternalId": contact,
        "timestamp": str(timestamp or ""),
        "fromSelf": from_self,
        "metadata": {
            "provider": "evolution",
            "eventMessageType": raw_type,
            "pushName": message.get("pushName"),
            "participant": key.get("participant"),
        },
    }

    if raw_type in {"conversation", "extendedtextmessage", "text"}:
        text = message.get("text") or message_body.get("conversation") or message_body.get("extendedTextMessage", {}).get("text")
        return {**base, "type": "TEXT", "text": text}
    if raw_type in {"audiomessage", "audio"}:
        media = message_body.get("audioMessage", {}) if isinstance(message_body.get("audioMessage"), dict) else message
        return {**base, "type": "AUDIO", **_media_fields(media, message, "audio")}
    if raw_type in {"imagemessage", "image"}:
        media = message_body.get("imageMessage", {}) if isinstance(message_body.get("imageMessage"), dict) else message
        return {**base, "type": "IMAGE", **_media_fields(media, message, "image")}
    if raw_type in {"documentmessage", "document"}:
        media = message_body.get("documentMessage", {}) if isinstance(message_body.get("documentMessage"), dict) else message
        return {**base, "type": "DOCUMENT", **_media_fields(media, message, "document")}
    if not raw_type and message.get("text"):
        return {**base, "type": "TEXT", "text": message.get("text")}
    raise EvolutionWebhookError(f"UNSUPPORTED_MESSAGE_TYPE:{raw_type or 'unknown'}")


def _media_fields(media: dict[str, Any], message: dict[str, Any], media_type: str) -> dict[str, Any]:
    provider_media_id = str(message.get("id") or message.get("messageId") or message.get("key", {}).get("id") or "")
    media_url = message.get("mediaUrl") or media.get("url")
    file_name = message.get("fileName") or media.get("fileName") or media.get("filename")
    mime_type = message.get("mimeType") or media.get("mimetype") or media.get("mime_type")
    return {
        "mimeType": mime_type,
        "fileName": file_name,
        "media": {
            "providerMediaId": provider_media_id,
            "url": media_url if isinstance(media_url, str) and media_url.startswith(("http://", "https://")) else None,
            "sha256": media.get("fileSha256") or media.get("sha256"),
            "sizeBytes": media.get("fileLength") or media.get("sizeBytes"),
            "storageReference": f"evolution:{provider_media_id}" if provider_media_id else None,
            "metadata": {
                "provider": "evolution",
                "type": media_type,
                "base64": message.get("base64"),
                "clinical": message.get("clinical"),
                "ambiguous": message.get("ambiguous"),
                "corrupted": message.get("corrupted"),
                "illegible": message.get("illegible"),
                "administrativeDescription": message.get("administrativeDescription"),
                "extractedText": message.get("extractedText"),
            },
        },
    }


def _detect_message_type(message_body: dict[str, Any]) -> str:
    if "conversation" in message_body:
        return "conversation"
    for key in ("extendedTextMessage", "audioMessage", "imageMessage", "documentMessage"):
        if key in message_body:
            return key
    return ""


def _normalize_remote_jid(remote_jid: str) -> str:
    if "@" in remote_jid:
        return remote_jid.split("@", 1)[0]
    return remote_jid


def _header(headers: dict[str, str], key: str) -> str | None:
    lowered = {name.lower(): value for name, value in headers.items()}
    return lowered.get(key.lower())
