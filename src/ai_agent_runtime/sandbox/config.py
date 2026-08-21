from __future__ import annotations

from dataclasses import dataclass, field
from os import environ

from ai_agent_runtime.integrations.config import IntegrationConfig


SANDBOX_ENV = "sandbox"
RUN_LIVE_FLAG = "RUN_LIVE_SANDBOX"
DEFAULT_LANGSMITH_PROJECT = "ai-atendimento-sandbox"


REQUIRED_ENV_BY_STEP: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY",),
    "supabase": ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"),
    "langsmith": ("LANGSMITH_API_KEY",),
    "google_calendar": ("GOOGLE_CALENDAR_ID",),
}


@dataclass(frozen=True)
class SandboxConfig:
    app_env: str | None
    run_live: bool
    integrations: IntegrationConfig
    google_calendar_timezone: str = "America/Bahia"
    langsmith_project: str = DEFAULT_LANGSMITH_PROJECT

    @classmethod
    def from_env(cls) -> "SandboxConfig":
        integrations = IntegrationConfig.from_env()
        return cls(
            app_env=environ.get("APP_ENV"),
            run_live=environ.get(RUN_LIVE_FLAG, "").lower() == "true",
            integrations=integrations,
            google_calendar_timezone=environ.get("GOOGLE_CALENDAR_TIMEZONE", integrations.google_calendar_timezone),
            langsmith_project=environ.get("LANGSMITH_PROJECT", DEFAULT_LANGSMITH_PROJECT),
        )

    def missing_for(self, step: str) -> tuple[str, ...]:
        missing: list[str] = []
        for key in REQUIRED_ENV_BY_STEP.get(step, ()):
            if not environ.get(key):
                missing.append(key)
        if step == "google_calendar" and not (environ.get("GOOGLE_CALENDAR_ACCESS_TOKEN") or environ.get("GOOGLE_CALENDAR_REFRESH_TOKEN")):
            missing.append("GOOGLE_CALENDAR_ACCESS_TOKEN_OR_REFRESH_TOKEN")
        if step == "google_calendar" and not self.google_calendar_timezone:
            missing.append("GOOGLE_CALENDAR_TIMEZONE")
        return tuple(missing)


@dataclass(frozen=True)
class ReadinessResult:
    live_enabled: bool
    app_env: str | None
    blocked_reason: str | None
    missing_by_step: dict[str, tuple[str, ...]] = field(default_factory=dict)


def evaluate_readiness(config: SandboxConfig, *, steps: tuple[str, ...] = tuple(REQUIRED_ENV_BY_STEP)) -> ReadinessResult:
    if not config.run_live:
        return ReadinessResult(
            live_enabled=False,
            app_env=config.app_env,
            blocked_reason="LIVE_DISABLED",
            missing_by_step={},
        )
    if config.app_env != SANDBOX_ENV:
        return ReadinessResult(
            live_enabled=False,
            app_env=config.app_env,
            blocked_reason="APP_ENV_NOT_SANDBOX",
            missing_by_step={},
        )
    missing = {step: config.missing_for(step) for step in steps}
    missing = {step: values for step, values in missing.items() if values}
    return ReadinessResult(
        live_enabled=not missing,
        app_env=config.app_env,
        blocked_reason="MISSING_CREDENTIALS" if missing else None,
        missing_by_step=missing,
    )
