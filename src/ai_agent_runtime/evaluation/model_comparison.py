"""Content-free aggregation for controlled commercial model comparisons.

The caller supplies reviewed observations and current token rates. This module
does not call a model, read patient messages, or select a winner.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any, Iterable


def compare_model_observations(
    observations: Iterable[dict[str, Any]],
    *,
    usd_per_million_tokens: dict[str, tuple[Decimal, Decimal]],
) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for item in observations:
        model, scenario = item.get("model"), item.get("scenario")
        if not isinstance(model, str) or not isinstance(scenario, str) or not model or not scenario:
            raise ValueError("MODEL_COMPARISON_INVALID_OBSERVATION")
        if scenario in rows[model]:
            raise ValueError("MODEL_COMPARISON_DUPLICATE_SCENARIO")
        for key in ("conversationQuality", "commercialAccuracy"):
            value = item.get(key)
            if type(value) not in (int, float) or not 0 <= value <= 1:
                raise ValueError("MODEL_COMPARISON_INVALID_SCORE")
        for key in ("latencyMs", "inputTokens", "outputTokens"):
            value = item.get(key)
            if type(value) is not int or value < 0:
                raise ValueError("MODEL_COMPARISON_INVALID_USAGE")
        for key in ("handoff", "inventedFact", "bookingProgress"):
            if type(item.get(key)) is not bool:
                raise ValueError("MODEL_COMPARISON_INVALID_OUTCOME")
        rows[model][scenario] = item
    if len(rows) < 2 or len({frozenset(group) for group in rows.values()}) != 1:
        raise ValueError("MODEL_COMPARISON_UNPAIRED_SCENARIOS")
    result: dict[str, dict[str, Any]] = {}
    for model, scenarios in sorted(rows.items()):
        rates = usd_per_million_tokens.get(model)
        if not rates or len(rates) != 2 or any(rate < 0 for rate in rates):
            raise ValueError("MODEL_COMPARISON_RATES_REQUIRED")
        items = list(scenarios.values())
        count = len(items)
        input_tokens = sum(item["inputTokens"] for item in items)
        output_tokens = sum(item["outputTokens"] for item in items)
        cost = (Decimal(input_tokens) * rates[0] + Decimal(output_tokens) * rates[1]) / Decimal(1_000_000)
        result[model] = {
            "scenarios": count,
            "conversationQuality": sum(item["conversationQuality"] for item in items) / count,
            "commercialAccuracy": sum(item["commercialAccuracy"] for item in items) / count,
            "handoffRate": sum(item["handoff"] for item in items) / count,
            "inventedFactRate": sum(item["inventedFact"] for item in items) / count,
            "bookingProgressRate": sum(item["bookingProgress"] for item in items) / count,
            "meanLatencyMs": sum(item["latencyMs"] for item in items) / count,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "estimatedCostUsd": str(cost),
        }
    return result
