from __future__ import annotations

from typing import Any

from ai_agent_runtime.integrations.openai_provider import OpenAIProviderError, OpenAIResponsesProvider

from .config import SandboxConfig
from .redaction import redact


SANDBOX_DECISION_SCHEMA = {
    "name": "sandbox_decision",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision": {"type": "string", "enum": ["ANSWER_GROUNDED", "HUMAN_HANDOFF_REQUIRED"]},
            "reason": {"type": "string"},
        },
        "required": ["decision", "reason"],
    },
}


def build_openai_smoke_payload(config: SandboxConfig) -> dict[str, Any]:
    provider = OpenAIResponsesProvider(config.integrations, transport=None)
    return provider.build_response_payload(
        input_messages=[
            {
                "role": "user",
                "content": "Responda apenas com JSON estruturado para smoke test sandbox.",
            }
        ],
        json_schema=SANDBOX_DECISION_SCHEMA,
    )


def run_openai_smoke(config: SandboxConfig) -> dict[str, Any]:
    provider = OpenAIResponsesProvider(config.integrations)
    try:
        response = provider.create_response(
            input_messages=[
                {
                    "role": "user",
                    "content": "Classifique este smoke test ficticio como ANSWER_GROUNDED.",
                }
            ],
            json_schema=SANDBOX_DECISION_SCHEMA,
        )
        return {
            "service": "openai",
            "status": "LIVE_VERIFIED",
            "model": config.integrations.openai_responses_model,
            "usage": response.get("usage"),
        }
    except OpenAIProviderError as exc:
        return redact({
            "service": "openai",
            "status": "FAILED_AUTH_OR_PROVIDER",
            "error": str(exc),
            "api_key": config.integrations.openai_api_key,
        })
