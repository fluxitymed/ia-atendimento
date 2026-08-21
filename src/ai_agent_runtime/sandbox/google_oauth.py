from __future__ import annotations

import json
import secrets
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from os import chmod, environ
from pathlib import Path
from socketserver import TCPServer
from typing import Any
from urllib import parse, request

from .config import SANDBOX_ENV
from .redaction import redact
from .reporting import dumps_report


GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_OAUTH_SCOPES = (
    "https://www.googleapis.com/auth/calendar.freebusy",
    "https://www.googleapis.com/auth/calendar.events",
)
DEFAULT_REDIRECT_PORT = 8765
DEFAULT_TOKEN_FILE = ".secrets/google-calendar-sandbox-oauth.json"
REQUIRED_OAUTH_ENV = (
    "APP_ENV",
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
)
SAFE_ENV_NAMES = (
    "GOOGLE_CALENDAR_ACCESS_TOKEN",
    "GOOGLE_CALENDAR_REFRESH_TOKEN",
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "GOOGLE_OAUTH_TOKEN_URI",
)


class GoogleOAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class GoogleOAuthConfig:
    app_env: str | None
    client_id: str | None
    client_secret: str | None
    redirect_port: int = DEFAULT_REDIRECT_PORT
    token_uri: str = GOOGLE_TOKEN_URI
    token_file: Path = Path(DEFAULT_TOKEN_FILE)

    @classmethod
    def from_env(cls) -> "GoogleOAuthConfig":
        return cls(
            app_env=environ.get("APP_ENV"),
            client_id=environ.get("GOOGLE_OAUTH_CLIENT_ID"),
            client_secret=environ.get("GOOGLE_OAUTH_CLIENT_SECRET"),
            redirect_port=int(environ.get("GOOGLE_OAUTH_REDIRECT_PORT", str(DEFAULT_REDIRECT_PORT))),
            token_uri=environ.get("GOOGLE_OAUTH_TOKEN_URI", GOOGLE_TOKEN_URI),
            token_file=Path(environ.get("GOOGLE_OAUTH_TOKEN_FILE", DEFAULT_TOKEN_FILE)),
        )

    @property
    def redirect_uri(self) -> str:
        return f"http://127.0.0.1:{self.redirect_port}/oauth2callback"


def missing_oauth_env(config: GoogleOAuthConfig) -> tuple[str, ...]:
    missing: list[str] = []
    if config.app_env != SANDBOX_ENV:
        missing.append("APP_ENV")
    if not config.client_id:
        missing.append("GOOGLE_OAUTH_CLIENT_ID")
    if not config.client_secret:
        missing.append("GOOGLE_OAUTH_CLIENT_SECRET")
    return tuple(missing)


def build_authorization_url(config: GoogleOAuthConfig, *, state: str) -> str:
    if not config.client_id:
        raise GoogleOAuthError("GOOGLE_OAUTH_CLIENT_ID missing")
    params = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_CALENDAR_OAUTH_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "false",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URI}?{parse.urlencode(params)}"


def exchange_code_for_tokens(config: GoogleOAuthConfig, *, code: str) -> dict[str, Any]:
    if not config.client_id:
        raise GoogleOAuthError("GOOGLE_OAUTH_CLIENT_ID missing")
    if not config.client_secret:
        raise GoogleOAuthError("GOOGLE_OAUTH_CLIENT_SECRET missing")
    payload = parse.urlencode({
        "code": code,
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "redirect_uri": config.redirect_uri,
        "grant_type": "authorization_code",
    }).encode("utf-8")
    req = request.Request(
        config.token_uri,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with request.urlopen(req, timeout=30) as response:
        token_response = json.loads(response.read().decode("utf-8"))
    return normalize_token_response(token_response)


def normalize_token_response(token_response: dict[str, Any]) -> dict[str, Any]:
    issued_at = int(time.time())
    expires_in = token_response.get("expires_in")
    normalized = {
        "access_token": token_response.get("access_token"),
        "refresh_token": token_response.get("refresh_token"),
        "expires_in": expires_in,
        "expires_at": issued_at + int(expires_in) if expires_in is not None else None,
        "token_type": token_response.get("token_type"),
        "scope": token_response.get("scope"),
        "issued_at": issued_at,
    }
    return normalized


def write_token_file(config: GoogleOAuthConfig, token_response: dict[str, Any]) -> Path:
    config.token_file.parent.mkdir(parents=True, exist_ok=True)
    config.token_file.write_text(json.dumps(token_response, indent=2, sort_keys=True), encoding="utf-8")
    chmod(config.token_file, 0o600)
    return config.token_file


def build_safe_env_guidance(config: GoogleOAuthConfig, token_response: dict[str, Any] | None = None) -> dict[str, Any]:
    token_response = token_response or {}
    return redact({
        "status": "OAUTH_READY",
        "tokenFile": str(config.token_file),
        "scopes": list(GOOGLE_CALENDAR_OAUTH_SCOPES),
        "envVarsToFill": list(SAFE_ENV_NAMES),
        "preservedRefreshToken": bool(token_response.get("refresh_token")),
        "preservedAccessToken": bool(token_response.get("access_token")),
        "values": {
            "GOOGLE_CALENDAR_ACCESS_TOKEN": token_response.get("access_token"),
            "GOOGLE_CALENDAR_REFRESH_TOKEN": token_response.get("refresh_token"),
            "GOOGLE_OAUTH_CLIENT_ID": config.client_id,
            "GOOGLE_OAUTH_CLIENT_SECRET": config.client_secret,
            "GOOGLE_OAUTH_TOKEN_URI": config.token_uri,
        },
    })


def run_desktop_oauth(config: GoogleOAuthConfig | None = None) -> dict[str, Any]:
    config = config or GoogleOAuthConfig.from_env()
    missing = missing_oauth_env(config)
    if missing:
        return {
            "status": "BLOCKED_MISSING_CREDENTIALS",
            "missingEnv": list(missing),
            "envVarsToFill": list(SAFE_ENV_NAMES),
        }

    state = secrets.token_urlsafe(24)
    auth_url = build_authorization_url(config, state=state)
    print(dumps_report({
        "status": "OPEN_BROWSER",
        "authorizationUrl": auth_url,
        "scopes": GOOGLE_CALENDAR_OAUTH_SCOPES,
        "note": "A URL contem client_id e state; nao contem client_secret.",
    }))
    webbrowser.open(auth_url)
    code = wait_for_oauth_code(config.redirect_port, expected_state=state)
    token_response = exchange_code_for_tokens(config, code=code)
    write_token_file(config, token_response)
    return build_safe_env_guidance(config, token_response)


def wait_for_oauth_code(port: int, *, expected_state: str) -> str:
    result: dict[str, str] = {}

    class OAuthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = parse.urlparse(self.path)
            query = parse.parse_qs(parsed.query)
            state = query.get("state", [""])[0]
            code = query.get("code", [""])[0]
            error = query.get("error", [""])[0]
            if error:
                result["error"] = error
                self._respond(400, "OAuth retornou erro. Pode fechar esta janela.")
                return
            if state != expected_state:
                result["error"] = "state_mismatch"
                self._respond(400, "State OAuth invalido. Pode fechar esta janela.")
                return
            result["code"] = code
            self._respond(200, "OAuth sandbox concluido. Pode fechar esta janela.")

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _respond(self, status: int, body: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

    with TCPServer(("127.0.0.1", port), OAuthHandler) as httpd:
        httpd.handle_request()
    if result.get("error"):
        raise GoogleOAuthError(result["error"])
    if not result.get("code"):
        raise GoogleOAuthError("authorization_code_missing")
    return result["code"]


def main() -> int:
    result = run_desktop_oauth()
    print(dumps_report(result))
    return 0 if result.get("status") == "OAUTH_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
