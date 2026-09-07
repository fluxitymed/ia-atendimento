from __future__ import annotations

from dataclasses import dataclass
from os import environ
from pathlib import Path


def load_env_file(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in environ:
            environ[key] = value.strip().strip('"').strip("'")


@dataclass(frozen=True)
class IntegrationConfig:
    app_env: str = "development"
    run_live_sandbox: bool = False
    openai_api_key: str | None = None
    openai_responses_model: str = "gpt-5.6-luna"
    openai_reasoning_effort: str = "low"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_stt_model: str = "gpt-4o-mini-transcribe"
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    langsmith_api_key: str | None = None
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_project: str = "ai-atendimento-sandbox"
    langsmith_workspace_id: str | None = None
    google_calendar_id: str | None = None
    google_calendar_access_token: str | None = None
    google_calendar_refresh_token: str | None = None
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_token_uri: str = "https://oauth2.googleapis.com/token"
    google_calendar_timezone: str = "America/Bahia"

    @classmethod
    def from_env(cls) -> "IntegrationConfig":
        load_env_file()
        return cls(
            app_env=environ.get("APP_ENV", cls.app_env),
            run_live_sandbox=environ.get("RUN_LIVE_SANDBOX", "").lower() == "true",
            openai_api_key=environ.get("OPENAI_API_KEY"),
            openai_responses_model=environ.get("OPENAI_RESPONSES_MODEL", cls.openai_responses_model),
            openai_reasoning_effort=environ.get("OPENAI_REASONING_EFFORT", cls.openai_reasoning_effort),
            openai_embedding_model=environ.get("OPENAI_EMBEDDING_MODEL", cls.openai_embedding_model),
            openai_stt_model=environ.get("OPENAI_STT_MODEL", cls.openai_stt_model),
            supabase_url=environ.get("SUPABASE_URL"),
            supabase_service_role_key=environ.get("SUPABASE_SERVICE_ROLE_KEY"),
            langsmith_api_key=environ.get("LANGSMITH_API_KEY"),
            langsmith_endpoint=environ.get("LANGSMITH_ENDPOINT", cls.langsmith_endpoint),
            langsmith_project=environ.get("LANGSMITH_PROJECT", cls.langsmith_project),
            langsmith_workspace_id=environ.get("LANGSMITH_WORKSPACE_ID"),
            google_calendar_id=environ.get("GOOGLE_CALENDAR_ID"),
            google_calendar_access_token=environ.get("GOOGLE_CALENDAR_ACCESS_TOKEN"),
            google_calendar_refresh_token=environ.get("GOOGLE_CALENDAR_REFRESH_TOKEN"),
            google_oauth_client_id=environ.get("GOOGLE_OAUTH_CLIENT_ID"),
            google_oauth_client_secret=environ.get("GOOGLE_OAUTH_CLIENT_SECRET"),
            google_oauth_token_uri=environ.get("GOOGLE_OAUTH_TOKEN_URI", cls.google_oauth_token_uri),
            google_calendar_timezone=environ.get("GOOGLE_CALENDAR_TIMEZONE", cls.google_calendar_timezone),
        )
