from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .adapter import WhatsAppChannelAdapter
from .channel import ChannelRecord
from .adapter import WhatsAppRuntimeError
from .zapi import ZApiWhatsAppConfig, redact_zapi_secret


WEBHOOK_PATH = "/webhooks/zapi/whatsapp"


@dataclass(frozen=True)
class ZApiWebhookResponse:
    status_code: int
    body: str
    headers: dict[str, str] = field(default_factory=lambda: {"Content-Type": "text/plain"})


class ZApiWebhookError(ValueError):
    pass


def validate_zapi_webhook(headers: dict[str, str], config: ZApiWhatsAppConfig) -> bool:
    return True


def parse_zapi_webhook_payload(raw_body: bytes) -> list[dict[str, Any]]:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise ZApiWebhookError("INVALID_JSON") from exc

    messages: Any
    if isinstance(payload, list):
        messages = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("messages"), list):
            messages = payload["messages"]
        elif isinstance(payload.get("data"), list):
            messages = payload["data"]
        elif isinstance(payload.get("data"), dict):
            messages = [payload["data"]]
        else:
            messages = [payload]
    else:
        raise ZApiWebhookError("INVALID_PAYLOAD")

    events = []
    for message in messages:
        if isinstance(message, dict):
            parsed = _parse_zapi_message(message)
            if parsed:
                events.append(parsed)
    return [event for event in events if event.get("providerAccountId") and event.get("providerMessageId")]


def handle_zapi_webhook_post(
    *,
    raw_body: bytes,
    headers: dict[str, str],
    config: ZApiWhatsAppConfig,
    adapter: WhatsAppChannelAdapter,
    stage_logger: Any | None = None,
) -> tuple[ZApiWebhookResponse, list[ChannelRecord]]:
    _log_webhook_ingress(raw_body, headers, stage_logger)
    validate_zapi_webhook(headers, config)
    try:
        events = parse_zapi_webhook_payload(raw_body)
    except ZApiWebhookError as exc:
        _log_stage(stage_logger, "zapi_webhook_rejected", {"reason": str(exc)})
        return ZApiWebhookResponse(status_code=400, body=str(exc)), []

    records: list[ChannelRecord] = []
    for event in events:
        if event.get("type") == "AUDIO":
            _log_stage(
                stage_logger,
                "audio_inbound_detected",
                {
                    "providerAccountId": event.get("providerAccountId"),
                    "providerMessageId": event.get("providerMessageId"),
                    "mimeType": event.get("mimeType"),
                    "hasTemporaryUrl": bool((event.get("media") or {}).get("url")),
                    "durationSeconds": ((event.get("media") or {}).get("metadata") or {}).get("durationSeconds"),
                    "ptt": ((event.get("media") or {}).get("metadata") or {}).get("ptt"),
                    "viewOnce": ((event.get("media") or {}).get("metadata") or {}).get("viewOnce"),
                },
            )
        if event.get("type") in {"AUDIO", "IMAGE", "DOCUMENT"} and not ((event.get("media") or {}).get("url")):
            media_type = str(event.get("type") or "").lower()
            reason = "audio_payload_missing_url" if event.get("type") == "AUDIO" else "zapi_media_payload_invalid"
            _log_stage(
                stage_logger,
                reason,
                {
                    "messageType": event.get("type"),
                    "providerAccountId": event.get("providerAccountId"),
                    "providerMessageId": event.get("providerMessageId"),
                    "mediaType": media_type,
                },
            )
        try:
            records.append(adapter.process_event(event))
        except ValueError as exc:
            message = redact_zapi_secret(str(exc), config.instance_token, config.client_token)
            if message == "UNKNOWN_PROVIDER_ACCOUNT":
                _log_stage(stage_logger, "zapi_webhook_rejected", {"reason": "UNKNOWN_INSTANCE", "providerAccountId": event.get("providerAccountId")})
                return ZApiWebhookResponse(status_code=403, body="UNKNOWN_INSTANCE"), records
            _log_stage(stage_logger, "zapi_webhook_rejected", {"reason": message})
            return ZApiWebhookResponse(status_code=400, body=message), records
        except WhatsAppRuntimeError as exc:
            _log_stage(stage_logger, "zapi_webhook_rejected", {"reason": "RUNTIME_ERROR"})
            return ZApiWebhookResponse(status_code=500, body=redact_zapi_secret(str(exc), config.instance_token, config.client_token)), records
    return ZApiWebhookResponse(status_code=200, body="EVENT_RECEIVED"), records


def _parse_zapi_message(message: dict[str, Any]) -> dict[str, Any] | None:
    event_name = str(message.get("type") or "").lower()
    if event_name and event_name not in {"receivedcallback", "received", "message"}:
        return None

    instance_id = message.get("instanceId")
    message_id = message.get("messageId") or message.get("id") or message.get("zaapId")
    contact_identity = _extract_contact_identity(message)
    from_self = bool(message.get("fromMe"))
    timestamp = message.get("momment") or message.get("moment") or message.get("timestamp")
    base = {
        "providerAccountId": instance_id,
        "providerMessageId": message_id,
        "contactExternalId": contact_identity["canonicalContactExternalId"],
        "timestamp": str(timestamp or ""),
        "fromSelf": from_self,
        "organizationId": message.get("organizationId"),
        "metadata": {
            "provider": "zapi",
            "eventType": message.get("type"),
            "senderName": message.get("senderName"),
            "participantPhone": message.get("participantPhone"),
            "senderLid": message.get("senderLid"),
            "chatLid": message.get("chatLid"),
            "participantLid": message.get("participantLid"),
            **contact_identity,
        },
    }

    text = _text_message(message)
    if text is not None:
        return {**base, "type": "TEXT", "text": text}
    if isinstance(message.get("audio"), dict):
        return {**base, "type": "AUDIO", **_media_fields(message["audio"], message, "audio")}
    if isinstance(message.get("image"), dict):
        image = message["image"]
        return {
            **base,
            "type": "IMAGE",
            "text": image.get("caption") or message.get("caption"),
            **_media_fields(image, message, "image"),
        }
    if isinstance(message.get("document"), dict):
        return {**base, "type": "DOCUMENT", **_media_fields(message["document"], message, "document")}
    raise ZApiWebhookError("UNSUPPORTED_MESSAGE_TYPE")


def _log_webhook_ingress(raw_body: bytes, headers: dict[str, str], stage_logger: Any | None) -> None:
    if stage_logger is None:
        return
    details: dict[str, Any] = {
        "method": "POST",
        "contentType": _header_value(headers, "content-type"),
        "payloadKeys": [],
        "payloadShape": "unknown",
        "hasText": False,
        "hasAudio": False,
        "hasImage": False,
        "hasVideo": False,
        "hasDocument": False,
    }
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        _log_stage(stage_logger, "zapi_webhook_ingress_received", {**details, "payloadShape": "invalid_json"})
        return
    message = _first_payload_message(payload)
    if isinstance(payload, dict):
        details["payloadKeys"] = sorted(str(key) for key in payload.keys())
        details["payloadShape"] = "object"
    elif isinstance(payload, list):
        details["payloadShape"] = "list"
        details["payloadLength"] = len(payload)
        if isinstance(message, dict):
            details["payloadKeys"] = sorted(str(key) for key in message.keys())
    else:
        details["payloadShape"] = type(payload).__name__
    if isinstance(message, dict):
        details.update(
            {
                "instanceId": message.get("instanceId"),
                "providerAccountId": message.get("instanceId"),
                "messageId": message.get("messageId") or message.get("id") or message.get("zaapId"),
                "type": message.get("type"),
                "fromMe": bool(message.get("fromMe")),
                "hasText": _text_message(message) is not None,
                "hasAudio": isinstance(message.get("audio"), dict),
                "hasImage": isinstance(message.get("image"), dict),
                "hasVideo": isinstance(message.get("video"), dict),
                "hasDocument": isinstance(message.get("document"), dict),
            }
        )
    _log_stage(stage_logger, "zapi_webhook_ingress_received", details)


def _first_payload_message(payload: Any) -> Any:
    if isinstance(payload, list):
        return payload[0] if payload else None
    if isinstance(payload, dict):
        if isinstance(payload.get("messages"), list):
            return payload["messages"][0] if payload["messages"] else None
        if isinstance(payload.get("data"), list):
            return payload["data"][0] if payload["data"] else None
        if isinstance(payload.get("data"), dict):
            return payload["data"]
        return payload
    return None


def _header_value(headers: dict[str, str], name: str) -> str:
    lowered = name.lower()
    for key, value in headers.items():
        if str(key).lower() == lowered:
            return str(value)
    return ""


def _log_stage(stage_logger: Any | None, stage: str, details: dict[str, Any] | None = None) -> None:
    if stage_logger is not None:
        stage_logger(stage, details or {})



def _text_message(message: dict[str, Any]) -> str | None:
    text = message.get("text")
    if isinstance(text, dict) and text.get("message") is not None:
        return str(text["message"])
    if isinstance(text, str):
        return text
    if message.get("message") is not None and not any(key in message for key in ("audio", "image", "document")):
        return str(message["message"])
    return None


def _media_fields(media: dict[str, Any], message: dict[str, Any], media_type: str) -> dict[str, Any]:
    provider_media_id = str(message.get("messageId") or message.get("id") or media.get("mediaId") or media.get("id") or "")
    url_keys = {
        "audio": ("audioUrl", "url"),
        "image": ("imageUrl", "url"),
        "document": ("documentUrl", "url"),
    }[media_type]
    media_url = next((media.get(key) for key in url_keys if media.get(key)), None)
    mime_type = _clean_mime_type(media.get("mimeType") or media.get("mimetype") or media.get("mime_type"))
    file_name = media.get("fileName") or media.get("filename") or media.get("title")
    return {
        "mimeType": mime_type,
        "fileName": file_name,
        "media": {
            "providerMediaId": provider_media_id,
            "url": media_url if isinstance(media_url, str) and media_url.startswith(("http://", "https://")) else None,
            "sha256": media.get("fileSha256") or media.get("sha256"),
            "sizeBytes": media.get("size") or media.get("sizeBytes") or media.get("fileLength"),
            "storageReference": f"zapi:{provider_media_id}" if provider_media_id else None,
            "metadata": {
                "provider": "zapi",
                "type": media_type,
                "base64": media.get("base64") or message.get("base64"),
                "temporaryUrl": bool(media_url),
                "clinical": message.get("clinical") or media.get("clinical"),
                "ambiguous": message.get("ambiguous") or media.get("ambiguous"),
                "corrupted": message.get("corrupted") or media.get("corrupted"),
                "illegible": message.get("illegible") or media.get("illegible"),
                "administrativeDescription": message.get("administrativeDescription") or media.get("administrativeDescription"),
                "extractedText": message.get("extractedText") or media.get("extractedText"),
                "fileName": file_name,
                "mimeType": mime_type,
                "durationSeconds": media.get("seconds") or media.get("duration") or media.get("durationSeconds"),
                "ptt": media.get("ptt"),
                "viewOnce": media.get("viewOnce"),
            },
        },
    }


def _clean_mime_type(value: Any) -> str | None:
    if not value:
        return None
    return str(value).split(";", 1)[0].strip().lower()


def _extract_contact_identity(message: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "phone": message.get("phone"),
        "phoneNumber": message.get("phoneNumber"),
        "senderPhone": message.get("senderPhone"),
        "participantPhone": message.get("participantPhone"),
        "senderLid": message.get("senderLid"),
        "chatLid": message.get("chatLid"),
        "participantLid": message.get("participantLid"),
        "chatId": message.get("chatId"),
        "remoteJid": message.get("remoteJid"),
        "sender": message.get("sender"),
        "participant": message.get("participant"),
        "lid": message.get("lid") or message.get("contactLid"),
    }
    aliases_by_field: dict[str, str] = {}
    for field_name, value in fields.items():
        for alias in _aliases_from_value(value):
            aliases_by_field.setdefault(field_name, alias)

    aliases = _unique(aliases_by_field.values())
    canonical = _preferred_contact_id(aliases)
    if not canonical and message.get("chatName"):
        canonical = str(message.get("chatName"))
        aliases = _unique([*aliases, canonical])
        aliases_by_field.setdefault("chatName", canonical)
    return {
        "canonicalContactExternalId": canonical,
        "contactAliases": aliases,
        "contactAliasSourceFields": aliases_by_field,
    }


def _aliases_from_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        aliases: list[str] = []
        for key in ("phone", "phoneNumber", "id", "jid", "remoteJid", "lid", "contactLid"):
            aliases.extend(_aliases_from_value(value.get(key)))
        return aliases
    if isinstance(value, (list, tuple)):
        aliases = []
        for item in value:
            aliases.extend(_aliases_from_value(item))
        return aliases
    text = str(value).strip()
    if not text:
        return []
    lowered = text.lower()
    if "@lid" in lowered:
        return [lowered]
    if "@" in lowered and any(suffix in lowered for suffix in ("@s.whatsapp.net", "@c.us")):
        head = lowered.split("@", 1)[0]
        digits = re.sub(r"\D", "", head)
        return [digits] if digits else [lowered]
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 7:
        return [digits]
    return [text]


def _preferred_contact_id(aliases: list[str]) -> str:
    for alias in aliases:
        if "@lid" not in alias.lower() and any(char.isdigit() for char in alias):
            return alias
    return aliases[0] if aliases else ""


def _unique(values: Any) -> list[str]:
    seen = set()
    unique = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            unique.append(text)
    return unique
