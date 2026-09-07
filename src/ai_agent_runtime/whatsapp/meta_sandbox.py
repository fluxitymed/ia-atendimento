from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from typing import Any

from .meta import MetaWhatsAppConfig
from .meta_webhook import WEBHOOK_PATH


META_LIVE_SCENARIOS = [
    "webhook_verification",
    "inbound_text",
    "outbound_text",
    "inbound_audio",
    "inbound_image",
    "inbound_document",
    "duplicate_webhook",
    "self_message",
    "handoff",
    "scheduling",
]


@dataclass(frozen=True)
class MetaLivePlan:
    service: str
    provider: str
    status: str
    webhookPath: str
    requiredEnv: list[str]
    missing: list[str]
    scenarios: list[str]
    requiresPublicWebhookUrl: bool
    liveVerifiedRequiresRealMetaCalls: bool
    notes: list[str]


def build_meta_live_plan(config: MetaWhatsAppConfig) -> dict[str, Any]:
    missing = config.missing_for_live()
    status = "BLOCKED_MISSING_CREDENTIALS" if missing else "READY_FOR_LIVE_EXECUTION"
    plan = MetaLivePlan(
        service="whatsapp",
        provider="meta_cloud",
        status=status,
        webhookPath=WEBHOOK_PATH,
        requiredEnv=[
            "WHATSAPP_PROVIDER",
            "META_WHATSAPP_ACCESS_TOKEN",
            "META_WHATSAPP_PHONE_NUMBER_ID",
            "META_WHATSAPP_BUSINESS_ACCOUNT_ID",
            "META_WHATSAPP_VERIFY_TOKEN",
            "META_WHATSAPP_APP_SECRET",
            "META_WHATSAPP_API_VERSION",
            "META_WHATSAPP_PUBLIC_WEBHOOK_URL",
        ],
        missing=missing,
        scenarios=list(META_LIVE_SCENARIOS),
        requiresPublicWebhookUrl=True,
        liveVerifiedRequiresRealMetaCalls=True,
        notes=[
            "Offline tests do not call Meta.",
            "LIVE_VERIFIED is reserved for an opt-in sandbox run with real Meta Cloud API calls.",
        ],
    )
    return asdict(plan)


def run_meta_live_smoke(config: MetaWhatsAppConfig | None = None) -> dict[str, Any]:
    cfg = config or MetaWhatsAppConfig.from_env()
    plan = build_meta_live_plan(cfg)
    if plan["missing"]:
        return plan
    if os.environ.get("RUN_META_WHATSAPP_LIVE") != "true":
        return {
            **plan,
            "status": "READY_FOR_LIVE_EXECUTION",
            "notes": [
                *plan["notes"],
                "Set RUN_META_WHATSAPP_LIVE=true only after configuring the public webhook in Meta.",
            ],
        }
    return {
        **plan,
        "status": "READY_FOR_LIVE_EXECUTION",
        "notes": [
            *plan["notes"],
            "Real Meta smoke orchestration requires an external webhook delivery from the sandbox/test number.",
        ],
    }


def main() -> int:
    result = run_meta_live_smoke()
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] == "LIVE_VERIFIED":
        return 0
    if result["status"] == "BLOCKED_MISSING_CREDENTIALS":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
