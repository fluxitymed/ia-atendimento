from __future__ import annotations

import re
from typing import Any


BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
TOKEN_VALUE_RE = re.compile(r"\b(?:sk|lsv2|ghp|ya29|eyJ)[A-Za-z0-9._~+/=-]{8,}\b")


def is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    if normalized in {"authorization", "token", "access_token", "refresh_token", "client_secret", "service_role_key"}:
        return True
    return (
        normalized.endswith("_token")
        or normalized.endswith("_secret")
        or normalized.endswith("_api_key")
        or normalized.endswith("_credential")
        or normalized.endswith("_credentials")
        or normalized.endswith("_service_role_key")
    )


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if is_sensitive_key(str(key)):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        value = BEARER_RE.sub("Bearer [REDACTED]", value)
        return TOKEN_VALUE_RE.sub("[REDACTED]", value)
    return value
