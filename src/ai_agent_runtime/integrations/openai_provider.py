from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib import request

from .config import IntegrationConfig


class OpenAIProviderError(RuntimeError):
    pass


class HttpTransport(Protocol):
    def post_json(self, url: str, *, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
        ...


class UrllibJsonTransport:
    def post_json(self, url: str, *, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=data, headers=headers, method="POST")
        with request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


@dataclass(frozen=True)
class EmbeddingResult:
    vector: list[float]
    model: str
    embedding_version: str
    indexed_at: str


class OpenAIResponsesProvider:
    responses_url = "https://api.openai.com/v1/responses"
    embeddings_url = "https://api.openai.com/v1/embeddings"

    def __init__(self, config: IntegrationConfig, transport: HttpTransport | None = None):
        self.config = config
        self.transport = transport or UrllibJsonTransport()

    def _headers(self) -> dict[str, str]:
        if not self.config.openai_api_key:
            raise OpenAIProviderError("OPENAI_API_KEY is required")
        return {
            "Authorization": f"Bearer {self.config.openai_api_key}",
            "Content-Type": "application/json",
        }

    def build_response_payload(
        self,
        *,
        input_messages: list[dict[str, Any]],
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.openai_responses_model,
            "input": input_messages,
            "reasoning": {"effort": self.config.openai_reasoning_effort},
            "store": False,
        }
        if json_schema is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": json_schema.get("name", "runtime_decision"),
                    "strict": True,
                    "schema": json_schema["schema"],
                }
            }
        return payload

    def create_response(self, *, input_messages: list[dict[str, Any]], json_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = self.build_response_payload(input_messages=input_messages, json_schema=json_schema)
        response = self.transport.post_json(self.responses_url, headers=self._headers(), payload=payload)
        if response.get("status") == "failed" or response.get("error"):
            raise OpenAIProviderError(response.get("error", {}).get("message") or "OpenAI response failed")
        return response

    def create_embedding(self, *, text: str, embedding_version: str = "v1") -> EmbeddingResult:
        payload = {"model": self.config.openai_embedding_model, "input": text}
        response = self.transport.post_json(self.embeddings_url, headers=self._headers(), payload=payload)
        try:
            vector = response["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenAIProviderError("OpenAI embedding response missing vector") from exc
        return EmbeddingResult(
            vector=vector,
            model=self.config.openai_embedding_model,
            embedding_version=embedding_version,
            indexed_at=datetime.now(timezone.utc).isoformat(),
        )
