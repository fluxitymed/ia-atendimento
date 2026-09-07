from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import json
from os import environ
from typing import Protocol
from typing import Any
from urllib import request
from uuid import uuid4

from ai_agent_runtime.integrations.config import IntegrationConfig

from .channel import MediaReference, WhatsAppMessageType, WhatsAppProvider


class MediaDecision(str, Enum):
    MEDIA_UNDERSTOOD = "MEDIA_UNDERSTOOD"
    MEDIA_RETRY_REQUIRED = "MEDIA_RETRY_REQUIRED"
    HUMAN_HANDOFF_REQUIRED = "HUMAN_HANDOFF_REQUIRED"


@dataclass(frozen=True)
class MediaProcessingResult:
    decision: MediaDecision
    operational_text: str | None = None
    transcript: str | None = None
    extracted_text: str | None = None
    handoff_reason: str | None = None
    retry_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SpeechToTextProvider(ABC):
    model: str = "gpt-4o-mini-transcribe"

    @abstractmethod
    def transcribe(self, *, audio: bytes, mime_type: str | None, file_name: str | None) -> str:
        raise NotImplementedError


class SpeechToTextTransientError(RuntimeError):
    pass


class AudioTranscriptionTransport(Protocol):
    def post_multipart(self, url: str, *, headers: dict[str, str], fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> dict[str, Any]:
        ...


class UrllibAudioTranscriptionTransport:
    def post_multipart(self, url: str, *, headers: dict[str, str], fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> dict[str, Any]:
        boundary = f"----codex-audio-{uuid4().hex}"
        body_parts: list[bytes] = []
        for name, value in fields.items():
            body_parts.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                    str(value).encode("utf-8"),
                    b"\r\n",
                ]
            )
        for name, (file_name, data, mime_type) in files.items():
            body_parts.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{name}"; filename="{file_name}"\r\n'.encode("utf-8"),
                    f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"),
                    data,
                    b"\r\n",
                ]
            )
        body_parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        req = request.Request(
            url,
            data=b"".join(body_parts),
            headers={**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8") or "{}")


class OpenAISpeechToTextProvider(SpeechToTextProvider):
    transcriptions_url = "https://api.openai.com/v1/audio/transcriptions"

    def __init__(self, config: IntegrationConfig, transport: AudioTranscriptionTransport | None = None):
        self.config = config
        self.transport = transport or UrllibAudioTranscriptionTransport()
        self.model = config.openai_stt_model

    def transcribe(self, *, audio: bytes, mime_type: str | None, file_name: str | None) -> str:
        if not self.config.openai_api_key:
            raise SpeechToTextTransientError("OPENAI_API_KEY is required")
        try:
            response = self.transport.post_multipart(
                self.transcriptions_url,
                headers={"Authorization": f"Bearer {self.config.openai_api_key}"},
                fields={"model": self.model},
                files={"file": (file_name or _default_audio_file_name(mime_type), audio, mime_type or "application/octet-stream")},
            )
        except Exception as exc:
            raise SpeechToTextTransientError(_sanitize_media_error(str(exc))) from exc
        text = response.get("text")
        if text is None and isinstance(response.get("data"), dict):
            text = response["data"].get("text")
        return str(text or "").strip()


class FakeSpeechToTextProvider(SpeechToTextProvider):
    def __init__(self, transcript: str | None = None, fail: bool = False):
        self.transcript = transcript
        self.fail = fail
        self.calls = 0

    def transcribe(self, *, audio: bytes, mime_type: str | None, file_name: str | None) -> str:
        self.calls += 1
        if self.fail or not audio:
            return ""
        return self.transcript or "Quero marcar uma consulta sexta a tarde."


class MediaProcessor:
    audio_mime_types = {"audio/ogg", "audio/mpeg", "audio/mp4", "audio/wav", "audio/webm"}
    image_mime_types = {"image/jpeg", "image/png", "image/webp"}
    document_mime_types = {"application/pdf", "text/plain", "text/markdown"}

    def __init__(
        self,
        *,
        provider: WhatsAppProvider,
        speech_to_text: SpeechToTextProvider,
        max_size_bytes: int | None = None,
        stt_max_attempts: int | None = None,
        stage_logger: Any | None = None,
    ):
        self.provider = provider
        self.speech_to_text = speech_to_text
        self.max_size_bytes = max_size_bytes or int(environ.get("AUDIO_MAX_BYTES", str(20 * 1024 * 1024)))
        self.stt_max_attempts = stt_max_attempts or int(environ.get("AUDIO_STT_MAX_ATTEMPTS", "2"))
        self.stage_logger = stage_logger

    def process(
        self,
        *,
        organization_id: str,
        message_type: WhatsAppMessageType,
        media_reference: MediaReference,
        mime_type: str | None,
        file_name: str | None,
        metadata: dict[str, Any],
    ) -> MediaProcessingResult:
        validation_error = self._validate(message_type, media_reference, mime_type)
        if validation_error:
            self._log(
                _invalid_media_stage(message_type, validation_error),
                {
                    "providerMediaId": media_reference.provider_media_id,
                    "messageType": message_type.value,
                    "reason": validation_error,
                    "mimeType": mime_type,
                    "hasTemporaryUrl": bool(media_reference.url),
                },
            )
            return MediaProcessingResult(
                decision=MediaDecision.HUMAN_HANDOFF_REQUIRED,
                handoff_reason=validation_error,
                metadata={"mediaReference": media_reference.provider_media_id},
            )
        if message_type == WhatsAppMessageType.AUDIO:
            return self._process_audio(organization_id, media_reference, mime_type, file_name)
        if message_type == WhatsAppMessageType.IMAGE:
            return self._process_image(organization_id, media_reference, metadata)
        if message_type == WhatsAppMessageType.DOCUMENT:
            return self._process_document(organization_id, media_reference, mime_type, metadata)
        return MediaProcessingResult(decision=MediaDecision.HUMAN_HANDOFF_REQUIRED, handoff_reason="UNSUPPORTED_MEDIA_TYPE")

    def _validate(self, message_type: WhatsAppMessageType, media_reference: MediaReference, mime_type: str | None) -> str | None:
        if not media_reference.provider_media_id:
            return "MEDIA_REFERENCE_MISSING"
        if media_reference.size_bytes is not None and media_reference.size_bytes > self.max_size_bytes:
            return "MEDIA_TOO_LARGE"
        allowed = {
            WhatsAppMessageType.AUDIO: self.audio_mime_types,
            WhatsAppMessageType.IMAGE: self.image_mime_types,
            WhatsAppMessageType.DOCUMENT: self.document_mime_types,
        }.get(message_type, set())
        if mime_type not in allowed:
            return "UNSUPPORTED_MIME_TYPE"
        return None

    def _process_audio(self, organization_id: str, media_reference: MediaReference, mime_type: str | None, file_name: str | None) -> MediaProcessingResult:
        self._log("media_download_started", {"providerMediaId": media_reference.provider_media_id, "messageType": "AUDIO", "mimeType": mime_type})
        try:
            audio = self.provider.download_media(organization_id=organization_id, media=media_reference)
        except Exception as exc:
            self._log("media_download_failed", {"providerMediaId": media_reference.provider_media_id, "messageType": "AUDIO", "error": _sanitize_media_error(str(exc))})
            self._log("media_retry_required", {"providerMediaId": media_reference.provider_media_id, "reason": "MEDIA_DOWNLOAD_FAILED"})
            return MediaProcessingResult(
                decision=MediaDecision.MEDIA_RETRY_REQUIRED,
                retry_message="Nao consegui baixar esse audio com seguranca. Pode me mandar novamente ou escrever aqui?",
                metadata={"model": self.speech_to_text.model, "mediaReference": media_reference.provider_media_id, "reason": "MEDIA_DOWNLOAD_FAILED"},
            )
        self._log("media_download_completed", {"providerMediaId": media_reference.provider_media_id, "messageType": "AUDIO", "sizeBytes": len(audio), "mimeType": mime_type})
        if len(audio) > self.max_size_bytes:
            return MediaProcessingResult(decision=MediaDecision.HUMAN_HANDOFF_REQUIRED, handoff_reason="MEDIA_TOO_LARGE")
        transcript = ""
        for attempt in range(1, max(self.stt_max_attempts, 1) + 1):
            self._log("transcription_started", {"provider": "openai", "model": self.speech_to_text.model, "attempt": attempt})
            try:
                transcript = self.speech_to_text.transcribe(audio=audio, mime_type=mime_type, file_name=file_name).strip()
                self._log("transcription_completed", {"provider": "openai", "model": self.speech_to_text.model, "attempt": attempt})
                break
            except SpeechToTextTransientError as exc:
                self._log("transcription_failed", {"provider": "openai", "model": self.speech_to_text.model, "attempt": attempt, "error": _sanitize_media_error(str(exc))})
                if attempt >= max(self.stt_max_attempts, 1):
                    self._log("media_retry_required", {"providerMediaId": media_reference.provider_media_id, "reason": "TRANSCRIPTION_FAILED"})
                    return MediaProcessingResult(
                        decision=MediaDecision.MEDIA_RETRY_REQUIRED,
                        retry_message="Nao consegui entender bem esse audio. Pode me mandar novamente ou escrever aqui?",
                        metadata={"model": self.speech_to_text.model, "mediaReference": media_reference.provider_media_id, "reason": "TRANSCRIPTION_FAILED"},
                    )
        if not transcript:
            self._log("transcript_length", {"provider": "openai", "model": self.speech_to_text.model, "length": 0})
            self._log("media_retry_required", {"providerMediaId": media_reference.provider_media_id, "reason": "EMPTY_TRANSCRIPT"})
            return MediaProcessingResult(
                decision=MediaDecision.MEDIA_RETRY_REQUIRED,
                retry_message="Nao consegui entender bem esse audio. Pode me mandar novamente ou escrever aqui?",
                metadata={"model": self.speech_to_text.model, "mediaReference": media_reference.provider_media_id},
            )
        self._log("transcript_length", {"provider": "openai", "model": self.speech_to_text.model, "length": len(transcript)})
        return MediaProcessingResult(
            decision=MediaDecision.MEDIA_UNDERSTOOD,
            operational_text=transcript,
            transcript=transcript,
            metadata={"model": self.speech_to_text.model, "mediaReference": media_reference.provider_media_id, "sourceMessageType": "AUDIO"},
        )

    def _process_image(self, organization_id: str, media_reference: MediaReference, metadata: dict[str, Any]) -> MediaProcessingResult:
        image = self.provider.download_media(organization_id=organization_id, media=media_reference)
        if len(image) > self.max_size_bytes:
            return MediaProcessingResult(decision=MediaDecision.HUMAN_HANDOFF_REQUIRED, handoff_reason="MEDIA_TOO_LARGE")
        if metadata.get("clinical") or metadata.get("ambiguous"):
            return MediaProcessingResult(
                decision=MediaDecision.HUMAN_HANDOFF_REQUIRED,
                handoff_reason="IMAGE_REQUIRES_HUMAN_REVIEW",
                metadata={"mediaReference": media_reference.provider_media_id, "clinical": bool(metadata.get("clinical"))},
            )
        description = str(metadata.get("administrativeDescription") or "").strip()
        if not description:
            return MediaProcessingResult(decision=MediaDecision.HUMAN_HANDOFF_REQUIRED, handoff_reason="IMAGE_NOT_UNDERSTOOD")
        return MediaProcessingResult(
            decision=MediaDecision.MEDIA_UNDERSTOOD,
            operational_text=description,
            extracted_text=description,
            metadata={"mediaReference": media_reference.provider_media_id},
        )

    def _process_document(self, organization_id: str, media_reference: MediaReference, mime_type: str | None, metadata: dict[str, Any]) -> MediaProcessingResult:
        document = self.provider.download_media(organization_id=organization_id, media=media_reference)
        if len(document) > self.max_size_bytes:
            return MediaProcessingResult(decision=MediaDecision.HUMAN_HANDOFF_REQUIRED, handoff_reason="MEDIA_TOO_LARGE")
        if metadata.get("clinical") or metadata.get("corrupted") or metadata.get("illegible"):
            return MediaProcessingResult(
                decision=MediaDecision.HUMAN_HANDOFF_REQUIRED,
                handoff_reason="DOCUMENT_REQUIRES_HUMAN_REVIEW",
                metadata={"mediaReference": media_reference.provider_media_id, "clinical": bool(metadata.get("clinical"))},
            )
        extracted = str(metadata.get("extractedText") or "").strip()
        if not extracted and mime_type in {"text/plain", "text/markdown"} and document:
            extracted = document.decode("utf-8", errors="replace").strip()
        if not extracted:
            return MediaProcessingResult(decision=MediaDecision.HUMAN_HANDOFF_REQUIRED, handoff_reason="DOCUMENT_NOT_UNDERSTOOD")
        return MediaProcessingResult(
            decision=MediaDecision.MEDIA_UNDERSTOOD,
            operational_text=extracted,
            extracted_text=extracted,
            metadata={"mediaReference": media_reference.provider_media_id},
        )

    def _log(self, stage: str, details: dict[str, Any]) -> None:
        if self.stage_logger is not None:
            self.stage_logger(stage, _sanitize_media_details(details))


def _default_audio_file_name(mime_type: str | None) -> str:
    by_mime = {
        "audio/ogg": "audio.ogg",
        "audio/mpeg": "audio.mp3",
        "audio/mp4": "audio.mp4",
        "audio/wav": "audio.wav",
        "audio/webm": "audio.webm",
    }
    return by_mime.get(str(mime_type or "").split(";", 1)[0].lower(), "audio.bin")


def _sanitize_media_details(details: dict[str, Any]) -> dict[str, Any]:
    sanitized = {}
    for key, value in details.items():
        lowered = str(key).lower()
        if "token" in lowered or "secret" in lowered or "authorization" in lowered or "base64" in lowered or "url" in lowered:
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_media_details(value)
        else:
            sanitized[key] = value
    return sanitized


def _sanitize_media_error(text: str) -> str:
    lowered = str(text or "").lower()
    if "token" in lowered or "secret" in lowered or "authorization" in lowered or "api key" in lowered or "base64" in lowered:
        return "media processing error"
    return str(text or "")[:300]


def _invalid_media_stage(message_type: WhatsAppMessageType, reason: str) -> str:
    if message_type == WhatsAppMessageType.AUDIO and reason == "MEDIA_URL_MISSING":
        return "audio_payload_missing_url"
    return "zapi_media_payload_invalid"
