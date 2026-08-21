from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

from .redaction import redact


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value


def build_report(payload: dict[str, Any]) -> dict[str, Any]:
    return redact(to_jsonable(payload))


def dumps_report(payload: dict[str, Any]) -> str:
    return json.dumps(build_report(payload), indent=2, sort_keys=True)
