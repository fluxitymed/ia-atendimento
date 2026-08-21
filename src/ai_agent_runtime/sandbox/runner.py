from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter

from .config import REQUIRED_ENV_BY_STEP, SandboxConfig, evaluate_readiness
from .google_calendar_smoke import build_google_calendar_plan, run_google_calendar_smoke
from .langsmith_smoke import build_langsmith_plan, run_langsmith_smoke
from .openai_smoke import build_openai_smoke_payload, run_openai_smoke
from .redaction import redact
from .reporting import build_report
from .supabase_smoke import build_supabase_plan, run_supabase_smoke


@dataclass(frozen=True)
class SandboxStepResult:
    name: str
    status: str
    details: dict
    latency_ms: float | None = None
    usage: dict | None = None


@dataclass(frozen=True)
class SandboxRunResult:
    status: str
    live_enabled: bool
    app_env: str | None
    steps: tuple[SandboxStepResult, ...]
    missing_by_step: dict[str, tuple[str, ...]] = field(default_factory=dict)
    exit_code: int = 0

    def as_dict(self) -> dict:
        return build_report({
            "status": self.status,
            "liveEnabled": self.live_enabled,
            "appEnv": self.app_env,
            "missingByStep": self.missing_by_step,
            "exitCode": self.exit_code,
            "steps": [
                {
                    "name": step.name,
                    "status": step.status,
                    "details": step.details,
                    "latencyMs": step.latency_ms,
                    "usage": step.usage,
                }
                for step in self.steps
            ],
        })


def run_sandbox(config: SandboxConfig | None = None) -> SandboxRunResult:
    config = config or SandboxConfig.from_env()
    readiness = evaluate_readiness(config)
    if readiness.blocked_reason == "LIVE_DISABLED":
        steps = _implemented_steps(config, status="DISABLED")
        return SandboxRunResult(
            status="IMPLEMENTED",
            live_enabled=False,
            app_env=config.app_env,
            steps=steps,
            exit_code=0,
        )
    if readiness.blocked_reason == "APP_ENV_NOT_SANDBOX":
        return SandboxRunResult(
            status="BLOCKED_APP_ENV_NOT_SANDBOX",
            live_enabled=False,
            app_env=config.app_env,
            steps=_implemented_steps(config, status="BLOCKED_APP_ENV_NOT_SANDBOX"),
            exit_code=2,
        )
    if readiness.blocked_reason == "MISSING_CREDENTIALS":
        return SandboxRunResult(
            status="BLOCKED_MISSING_CREDENTIALS",
            live_enabled=False,
            app_env=config.app_env,
            missing_by_step=readiness.missing_by_step,
            steps=_implemented_steps(config, status="BLOCKED_MISSING_CREDENTIALS"),
            exit_code=2,
        )
    steps = (
        _timed_step("openai", lambda: run_openai_smoke(config)),
        _timed_step("supabase", lambda: run_supabase_smoke(config)),
        _timed_step("google_calendar", lambda: run_google_calendar_smoke(config)),
        _timed_step("langsmith", lambda: run_langsmith_smoke(config)),
    )
    verified = all(step.status == "LIVE_VERIFIED" for step in steps)
    return SandboxRunResult(
        status="LIVE_VERIFIED" if verified else "READY_FOR_LIVE_EXECUTION",
        live_enabled=True,
        app_env=config.app_env,
        steps=steps,
        exit_code=0 if verified else 1,
    )


def _implemented_steps(config: SandboxConfig, *, status: str) -> tuple[SandboxStepResult, ...]:
    openai_payload = build_openai_smoke_payload(config)
    return (
        SandboxStepResult("openai", status, {"payload": openai_payload, "requiredEnv": REQUIRED_ENV_BY_STEP["openai"]}),
        SandboxStepResult("supabase", status, build_supabase_plan(config)),
        SandboxStepResult("google_calendar", status, build_google_calendar_plan(config)),
        SandboxStepResult("langsmith", status, build_langsmith_plan(config)),
    )


def _timed_step(name: str, fn) -> SandboxStepResult:
    started = perf_counter()
    try:
        details = fn()
    except Exception as exc:
        details = {
            "status": "FAILED",
            "errorType": exc.__class__.__name__,
            "error": redact(str(exc)),
        }
    latency_ms = round((perf_counter() - started) * 1000, 3)
    return SandboxStepResult(
        name=name,
        status=details.get("status", "UNKNOWN"),
        details=details,
        latency_ms=latency_ms,
        usage=details.get("usage"),
    )
