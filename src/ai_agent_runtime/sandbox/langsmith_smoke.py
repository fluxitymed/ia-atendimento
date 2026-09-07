from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from uuid import uuid4
from urllib import error, parse, request

from ai_agent_runtime.integrations.langsmith_observer import LangSmithObserver
from ai_agent_runtime.observability import AuditEvent, AuditStore, RuntimeObservability
from ai_agent_runtime.sandbox_ids import LEONARDO_ORG_ID
from langsmith import Client as LangSmithSdkClient

from .config import DEFAULT_LANGSMITH_PROJECT, SandboxConfig
from .redaction import redact


def build_langsmith_plan(config: SandboxConfig) -> dict:
    observer = LangSmithObserver(api_key=config.integrations.langsmith_api_key, project=config.langsmith_project)
    event = AuditEvent(
        conversation_id="sandbox-conv",
        organization_id=LEONARDO_ORG_ID,
        intent="FACTUAL_QUESTION",
        decision="HUMAN_HANDOFF_REQUIRED",
        tool_called=None,
        grounding_result="FAIL",
        handoff_reason="UNSUPPORTED_FACT",
    )
    payload = observer.prepare_payload(event)
    store = AuditStore()
    RuntimeObservability(store, observer).record_event(event)
    return redact({
        "service": "langsmith",
        "status": "IMPLEMENTED",
        "project": config.langsmith_project or DEFAULT_LANGSMITH_PROJECT,
        "localAuditEvents": len(store.events),
        "payload": payload,
        "authorization": f"Bearer {config.integrations.langsmith_api_key}" if config.integrations.langsmith_api_key else None,
    })


def run_langsmith_smoke(config: SandboxConfig) -> dict:
    missing = not config.integrations.langsmith_api_key
    if missing:
        return {**build_langsmith_plan(config), "status": "BLOCKED_MISSING_CREDENTIALS"}

    client = LangSmithRestClient(
        endpoint=config.integrations.langsmith_endpoint,
        api_key=config.integrations.langsmith_api_key,
        workspace_id=config.integrations.langsmith_workspace_id,
    )
    workspace_resolved = client.ensure_workspace_id()
    sdk = LangSmithSdkClient(
        api_url=config.integrations.langsmith_endpoint,
        api_key=config.integrations.langsmith_api_key,
        workspace_id=client.workspace_id,
    )
    run_id = uuid4()
    trace_id = run_id
    started_at = datetime.now(timezone.utc)
    sdk.create_run(
        id=run_id,
        trace_id=trace_id,
        dotted_order=started_at.strftime("%Y%m%dT%H%M%S%fZ") + str(run_id),
        name="ai-agent-live-sandbox-smoke",
        run_type="chain",
        project_name=config.langsmith_project,
        inputs={"message": "Paciente teste pergunta sobre implante"},
        start_time=started_at,
        extra={"metadata": {"environment": "sandbox", "feature": "ai-agent-live-sandbox"}},
    )
    sdk.update_run(
        run_id,
        outputs={"decision": "HUMAN_HANDOFF_REQUIRED", "redaction": "enabled"},
        end_time=datetime.now(timezone.utc),
    )
    sdk.flush()
    fetched = _read_run_with_retry(sdk, run_id)
    project = sdk.read_project(project_name=config.langsmith_project)
    plan = build_langsmith_plan(config)
    return {
        **plan,
        "status": "LIVE_VERIFIED",
        "sessionId": str(fetched.session_id),
        "runId": str(run_id),
        "traceId": str(fetched.trace_id or trace_id),
        "project": config.langsmith_project,
        "workspaceResolved": workspace_resolved,
        "runCreated": str(fetched.id) == str(run_id),
        "projectMatched": str(fetched.session_id) == str(project.id),
        "redactionChecked": plan["authorization"] == "[REDACTED]",
    }


def _read_run_with_retry(client: LangSmithSdkClient, run_id):
    last_error: Exception | None = None
    for _ in range(6):
        try:
            return client.read_run(run_id)
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"LangSmith run was created but could not be read back: {redact(str(last_error))}") from last_error


class LangSmithRestClient:
    def __init__(self, *, endpoint: str, api_key: str, workspace_id: str | None = None):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.workspace_id = workspace_id

    def _headers(self, *, include_workspace: bool = True) -> dict[str, str]:
        headers = {"X-Api-Key": self.api_key, "Content-Type": "application/json"}
        if include_workspace and self.workspace_id:
            headers["X-Tenant-Id"] = self.workspace_id
        return headers

    def _request(self, method: str, path: str, payload=None, *, include_workspace: bool = True):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = request.Request(f"{self.endpoint}{path}", data=data, headers=self._headers(include_workspace=include_workspace), method=method)
        try:
            with request.urlopen(req, timeout=30) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LangSmith HTTP {exc.code}: {redact(body)}") from exc

    def ensure_workspace_id(self) -> bool:
        if self.workspace_id:
            return True
        workspaces = self._request("GET", "/api/v1/workspaces", include_workspace=False)
        if isinstance(workspaces, list) and len(workspaces) == 1 and workspaces[0].get("id"):
            self.workspace_id = workspaces[0]["id"]
            return True
        if isinstance(workspaces, list) and len(workspaces) > 1:
            raise RuntimeError("LangSmith requires LANGSMITH_WORKSPACE_ID because multiple workspaces are visible to the API key")
        raise RuntimeError("LangSmith workspace could not be resolved from API key")

    def create_session(self, name: str) -> dict:
        existing = self._request("GET", f"/api/v1/sessions?{parse.urlencode({'name': name, 'limit': 1})}")
        if isinstance(existing, list) and existing:
            return existing[0]
        if isinstance(existing, dict):
            sessions = existing.get("sessions") or existing.get("items")
            if isinstance(sessions, list) and sessions:
                return sessions[0]
        return self._request("POST", "/api/v1/sessions", {"name": name})

    def create_run(self, payload: dict) -> dict:
        return self._request("POST", "/api/v1/runs", payload)

    def update_run(self, run_id: str, payload: dict) -> dict:
        return self._request("PATCH", f"/api/v1/runs/{run_id}", payload)

    def get_run(self, run_id: str) -> dict:
        return self._request("GET", f"/api/v1/runs/{run_id}")
