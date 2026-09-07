from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any

from .zapi import ZApiWhatsAppConfig, ZApiWhatsAppProvider, redact_zapi_secret, safe_zapi_result
from .zapi_webhook import WEBHOOK_PATH


ZAPI_LIVE_SCENARIOS = [
    "validate_config",
    "instance_status",
    "qr_code",
    "webhook_setup",
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
class ZApiLivePlan:
    service: str
    provider: str
    status: str
    webhookPath: str
    requiredEnv: list[str]
    missing: list[str]
    scenarios: list[str]
    commands: dict[str, str]
    liveVerifiedRequiresRealZApiCalls: bool
    notes: list[str]


def build_zapi_live_plan(config: ZApiWhatsAppConfig) -> dict[str, Any]:
    missing = config.missing_for_live()
    status = "BLOCKED_MISSING_CREDENTIALS" if missing else "READY_FOR_LIVE_EXECUTION"
    plan = ZApiLivePlan(
        service="whatsapp",
        provider="zapi",
        status=status,
        webhookPath=WEBHOOK_PATH,
        requiredEnv=[
            "WHATSAPP_PROVIDER",
            "ZAPI_BASE_URL",
            "ZAPI_INSTANCE_ID",
            "ZAPI_INSTANCE_TOKEN",
            "ZAPI_CLIENT_TOKEN",
            "ZAPI_PUBLIC_WEBHOOK_URL",
            "ZAPI_ORGANIZATION_ID",
        ],
        missing=missing,
        scenarios=list(ZAPI_LIVE_SCENARIOS),
        commands={
            "server": "PYTHONPATH=src python3 -m ai_agent_runtime.whatsapp.zapi_server",
            "smoke": "PYTHONPATH=src python3 -m ai_agent_runtime.whatsapp.zapi_sandbox smoke",
            "status": "PYTHONPATH=src RUN_ZAPI_LIVE=true python3 -m ai_agent_runtime.whatsapp.zapi_sandbox status",
            "qrCode": "PYTHONPATH=src RUN_ZAPI_LIVE=true python3 -m ai_agent_runtime.whatsapp.zapi_sandbox qr-code",
            "setWebhook": "PYTHONPATH=src RUN_ZAPI_LIVE=true python3 -m ai_agent_runtime.whatsapp.zapi_sandbox set-webhook",
        },
        liveVerifiedRequiresRealZApiCalls=True,
        notes=[
            "Z-API is used only as a WhatsApp Web sandbox/MVP provider for commercial validation.",
            "Offline tests do not call Z-API.",
            "LIVE_VERIFIED is reserved for opt-in sandbox execution with real status, webhook, outbound and inbound checks.",
            "Z-API webhooks require a public HTTPS URL and do not document a native inbound secret/signature.",
        ],
    )
    return asdict(plan)


def run_zapi_live_smoke(config: ZApiWhatsAppConfig | None = None) -> dict[str, Any]:
    cfg = config or ZApiWhatsAppConfig.from_env()
    plan = build_zapi_live_plan(cfg)
    if plan["missing"]:
        return plan
    if os.environ.get("RUN_ZAPI_LIVE") != "true":
        return {
            **plan,
            "status": "READY_FOR_LIVE_EXECUTION",
            "notes": [
                *plan["notes"],
                "Set RUN_ZAPI_LIVE=true only after configuring a sandbox instance and public webhook.",
            ],
        }

    provider = ZApiWhatsAppProvider(config=cfg)
    try:
        state = provider.instance_status()
    except Exception as exc:
        return {
            **plan,
            "status": "READY_FOR_LIVE_EXECUTION",
            "error": redact_zapi_secret(str(exc), cfg.instance_token, cfg.client_token),
        }
    return {
        **plan,
        "status": "READY_FOR_LIVE_EXECUTION",
        "instanceStatus": safe_zapi_result(state),
        "notes": [
            *plan["notes"],
            "Instance status was checked. Full LIVE_VERIFIED still requires webhook delivery and inbound/outbound sandbox messages.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else os.sys.argv[1:]
    command = args[0] if args else "smoke"
    config = ZApiWhatsAppConfig.from_env()
    provider = ZApiWhatsAppProvider(config=config)
    if command == "plan":
        result = build_zapi_live_plan(config)
    elif command == "status":
        result = safe_zapi_result(provider.instance_status())
    elif command == "qr-code":
        result = safe_zapi_result(provider.qr_code())
    elif command == "set-webhook":
        result = safe_zapi_result(provider.set_received_webhook())
    else:
        result = run_zapi_live_smoke(config)
    print(json.dumps(result, indent=2, sort_keys=True))
    status = result.get("status") if isinstance(result, dict) else None
    if status == "LIVE_VERIFIED":
        return 0
    if status == "BLOCKED_MISSING_CREDENTIALS":
        return 2
    return 1 if status else 0


if __name__ == "__main__":
    raise SystemExit(main())
