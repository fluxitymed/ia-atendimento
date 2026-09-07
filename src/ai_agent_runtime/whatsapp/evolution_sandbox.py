from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any

from .evolution import EvolutionWhatsAppConfig, EvolutionWhatsAppProvider, redact_evolution_secret
from .evolution_webhook import WEBHOOK_PATH


EVOLUTION_LIVE_SCENARIOS = [
    "connection_state",
    "create_instance",
    "qr_connect",
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
class EvolutionLivePlan:
    service: str
    provider: str
    status: str
    webhookPath: str
    requiredEnv: list[str]
    missing: list[str]
    scenarios: list[str]
    commands: dict[str, str]
    liveVerifiedRequiresRealEvolutionCalls: bool
    notes: list[str]


def build_evolution_live_plan(config: EvolutionWhatsAppConfig) -> dict[str, Any]:
    missing = config.missing_for_live()
    status = "BLOCKED_MISSING_CREDENTIALS" if missing else "READY_FOR_LIVE_EXECUTION"
    plan = EvolutionLivePlan(
        service="whatsapp",
        provider="evolution",
        status=status,
        webhookPath=WEBHOOK_PATH,
        requiredEnv=[
            "WHATSAPP_PROVIDER",
            "EVOLUTION_API_BASE_URL",
            "EVOLUTION_API_KEY",
            "EVOLUTION_INSTANCE_NAME",
            "EVOLUTION_WEBHOOK_SECRET",
            "EVOLUTION_PUBLIC_WEBHOOK_URL",
            "EVOLUTION_ORGANIZATION_ID",
        ],
        missing=missing,
        scenarios=list(EVOLUTION_LIVE_SCENARIOS),
        commands={
            "server": "PYTHONPATH=src python3 -m ai_agent_runtime.whatsapp.evolution_server",
            "smoke": "PYTHONPATH=src python3 -m ai_agent_runtime.whatsapp.evolution_sandbox smoke",
            "status": "PYTHONPATH=src python3 -m ai_agent_runtime.whatsapp.evolution_sandbox status",
            "createInstance": "PYTHONPATH=src python3 -m ai_agent_runtime.whatsapp.evolution_sandbox create-instance",
            "connect": "PYTHONPATH=src python3 -m ai_agent_runtime.whatsapp.evolution_sandbox connect",
            "setWebhook": "PYTHONPATH=src python3 -m ai_agent_runtime.whatsapp.evolution_sandbox set-webhook",
        },
        liveVerifiedRequiresRealEvolutionCalls=True,
        notes=[
            "Offline tests do not call Evolution API.",
            "LIVE_VERIFIED is reserved for an opt-in sandbox run with real Evolution calls and webhook delivery.",
        ],
    )
    return asdict(plan)


def run_evolution_live_smoke(config: EvolutionWhatsAppConfig | None = None) -> dict[str, Any]:
    cfg = config or EvolutionWhatsAppConfig.from_env()
    plan = build_evolution_live_plan(cfg)
    if plan["missing"]:
        return plan
    if os.environ.get("RUN_EVOLUTION_LIVE") != "true":
        return {
            **plan,
            "status": "READY_FOR_LIVE_EXECUTION",
            "notes": [
                *plan["notes"],
                "Set RUN_EVOLUTION_LIVE=true only after configuring a sandbox instance and public webhook.",
            ],
        }

    provider = EvolutionWhatsAppProvider(config=cfg)
    try:
        state = provider.connection_state()
    except Exception as exc:
        return {
            **plan,
            "status": "READY_FOR_LIVE_EXECUTION",
            "error": redact_evolution_secret(str(exc), cfg.api_key, cfg.webhook_secret),
        }
    return {
        **plan,
        "status": "READY_FOR_LIVE_EXECUTION",
        "connectionState": state,
        "notes": [
            *plan["notes"],
            "Connection state was checked. Full LIVE_VERIFIED still requires webhook delivery and inbound/outbound sandbox messages.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else os.sys.argv[1:]
    command = args[0] if args else "smoke"
    config = EvolutionWhatsAppConfig.from_env()
    if command == "plan":
        result = build_evolution_live_plan(config)
    elif command == "status":
        result = EvolutionWhatsAppProvider(config=config).connection_state()
    elif command == "create-instance":
        result = EvolutionWhatsAppProvider(config=config).create_instance()
    elif command == "connect":
        result = EvolutionWhatsAppProvider(config=config).connect_instance()
    elif command == "set-webhook":
        result = EvolutionWhatsAppProvider(config=config).set_webhook()
    else:
        result = run_evolution_live_smoke(config)
    print(json.dumps(result, indent=2, sort_keys=True))
    status = result.get("status") if isinstance(result, dict) else None
    if status == "LIVE_VERIFIED":
        return 0
    if status == "BLOCKED_MISSING_CREDENTIALS":
        return 2
    return 1 if status else 0


if __name__ == "__main__":
    raise SystemExit(main())
