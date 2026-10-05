"""Private CRM knowledge HTTP adapter. Business decisions stay in KnowledgeAdmin."""
from __future__ import annotations

import json
import logging
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from .ingest_knowledge import smoke
from .knowledge import KnowledgeAdmin, organization_uuid
from .markdown import KnowledgeError, MAX_BYTES, source_from_text
from ai_agent_runtime.crm_dispatch import service_bearer_authorized

BASE = "/internal/knowledge"
MAX_HTTP_BODY_BYTES = 1_100_000
DEADLINE_SECONDS = 120


def _uuid(value, code="INVALID_REQUEST"):
    if not isinstance(value, str):
        raise KnowledgeError(code)
    try:
        result = str(UUID(value))
    except ValueError:
        raise KnowledgeError(code) from None
    if result != value:
        raise KnowledgeError(code)
    return result


def _actor(value):
    # The CRM sends its authenticated user's UUID, never arbitrary text.
    return _uuid(value, "ACTOR_REQUIRED")


def _filename(value):
    if not isinstance(value, str) or not re.fullmatch(r"[\w][\w .-]{0,159}\.md", value, re.UNICODE):
        raise KnowledgeError("INVALID_MARKDOWN_FILE")
    return value


def _body(raw_body, content_type):
    if not content_type or content_type.split(";", 1)[0].strip().lower() != "application/json":
        raise KnowledgeError("INVALID_CONTENT_TYPE")
    if len(raw_body) > MAX_HTTP_BODY_BYTES:
        raise KnowledgeError("REQUEST_TOO_LARGE")
    try:
        data = json.loads(raw_body.decode("utf-8", "strict"))
    except (ValueError, UnicodeError):
        raise KnowledgeError("INVALID_REQUEST") from None
    if not isinstance(data, dict):
        raise KnowledgeError("INVALID_REQUEST")
    return data


def _fields(data, required, optional=()):
    if not set(required).issubset(data) or set(data) - set(required) - set(optional):
        raise KnowledgeError("INVALID_REQUEST")


def _log(event, fields):
    # Only internally assembled, already validated IDs/state reach this logger.
    logging.getLogger("ai_agent_runtime.knowledge_api").info("%s %s", event, json.dumps(fields, sort_keys=True))


@contextmanager
def _default_connection():
    dsn = os.environ.get("KNOWLEDGE_DATABASE_URL")
    if not dsn:
        raise KnowledgeError("KNOWLEDGE_DATABASE_URL_REQUIRED")
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row, connect_timeout=10) as db:
        yield db


def _default_provider():
    from ai_agent_runtime.integrations.config import IntegrationConfig
    from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
    return OpenAIResponsesProvider(IntegrationConfig(
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        openai_embedding_model=os.environ.get("OPENAI_EMBEDDING_MODEL", IntegrationConfig.openai_embedding_model)))


def _default_retrieval():
    from ai_agent_runtime.whatsapp.zapi_server import ZApiRuntimeRetrieval
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise KnowledgeError("RETRIEVAL_CONFIGURATION_REQUIRED")
    return ZApiRuntimeRetrieval(supabase_url=url, service_role_key=key)


def _route(method, path):
    if method == "POST":
        action = path.removeprefix(BASE + "/")
        if path.startswith(BASE + "/") and action in {"dry-run", "ingest", "validate", "publish", "smoke", "deactivate"}:
            return action, None, None
    elif method == "GET":
        match = re.fullmatch(r"/internal/knowledge/documents(?:/([0-9a-f-]{36})(?:/(versions)(?:/([0-9a-f-]{36})/review)?)?)?", path)
        if match:
            if match[1]:
                _uuid(match[1])
            if match[3]:
                _uuid(match[3])
            return "list" if match[1] is None else "review" if match[3] else "versions" if match[2] else "detail", match[1], match[3]
    raise KnowledgeError("NOT_FOUND")


def _result_entry(entry, logical_name, filename):
    action = entry["action"]
    return {"filename": filename, "logicalName": logical_name,
            "status": entry.get("status") or entry.get("current_status") or "NEW",
            "currentVersion": entry["version_number"] - (action != "unchanged" and entry.get("status") == "REVIEW_REQUIRED"),
            "proposedVersion": entry["version_number"] if action == "unchanged" else entry["version_number"] + ("status" not in entry),
            "changed": action != "unchanged", "contentHash": entry["sha256"],
            "estimatedChunks": entry["chunk_count"], "documentId": entry["document_id"],
            "versionId": entry.get("version_id")}


def handle_knowledge_request(method, target, raw_body, authorization, *, token,
                             content_type=None, connection_factory=None, provider_factory=None,
                             retrieval_factory=None, logger=None):
    """Return (status, JSON). No exception, secret, or full source in error paths."""
    if not service_bearer_authorized(authorization, token):
        return 401, {"error": "UNAUTHORIZED"}
    log = logger or _log
    org = cor = actor = None
    action = "unknown"
    try:
        url = urlsplit(target)
        action, doc_id, version_path = _route(method, url.path)
        if method == "GET":
            params = parse_qs(url.query, strict_parsing=True)
            if set(params) != {"organizationId", "correlationId"} or any(len(v) != 1 for v in params.values()):
                raise KnowledgeError("INVALID_REQUEST")
            org = organization_uuid(_uuid(params["organizationId"][0], "ORGANIZATION_ID_REQUIRED_UUID"))
            cor = _uuid(params["correlationId"][0])
        else:
            if url.query:
                raise KnowledgeError("INVALID_REQUEST")
            data = _body(raw_body, content_type)
            org = organization_uuid(_uuid(data.get("organizationId"), "ORGANIZATION_ID_REQUIRED_UUID"))
            cor = _uuid(data.get("correlationId"))
            if action in ("validate", "publish", "deactivate"):
                _fields(data, ("organizationId", "correlationId", "versionId", "actor"))
                _uuid(data["versionId"])
                actor = _actor(data["actor"])
            elif action == "smoke":
                _fields(data, ("organizationId", "correlationId", "versionId", "queries"))
                _uuid(data["versionId"])
                if (not isinstance(data["queries"], list) or not 1 <= len(data["queries"]) <= 8 or
                    any(not isinstance(q, str) or not q.strip() or len(q) > 120 for q in data["queries"])):
                    raise KnowledgeError("INVALID_REQUEST")
            else:
                _fields(data, ("organizationId", "correlationId", "logicalName", "filename", "content"), ("actor",))
                _filename(data["filename"])
                if "actor" in data:
                    actor = _actor(data["actor"])
                source = source_from_text(data["logicalName"], data["content"])
                if len(data["content"].encode("utf-8")) > MAX_BYTES:
                    raise KnowledgeError("SOURCE_TOO_LARGE")
        with (connection_factory or _default_connection)() as db:
            admin = KnowledgeAdmin(db, org, deadline=time.monotonic() + DEADLINE_SECONDS)
            if action in ("dry-run", "ingest"):
                if action == "ingest":
                    admin.embeddings = (provider_factory or _default_provider)()
                report = admin.ingest([source], dry_run=action == "dry-run", correlation_id=cor,
                                      actor=actor, original_filename=data["filename"])
                entry = _result_entry(report["documents"][0], data["logicalName"], data["filename"])
                if action == "ingest":
                    entry["status"] = report["documents"][0]["status"]
                    entry["versionNumber"] = report["documents"][0]["version_number"]
                    entry["chunkCount"] = report["documents"][0]["chunk_count"]
                result = {"organizationId": org, "correlationId": cor, "documents": [entry],
                          "summary": report["summary"]}
            elif action in ("validate", "publish", "deactivate", "smoke"):
                manifest = admin.manifest_for_version(data["versionId"])
                if action == "validate":
                    report = admin.validate(manifest, None, actor, correlation_id=cor)
                elif action == "publish":
                    report = admin.publish(manifest, actor, correlation_id=cor)
                elif action == "deactivate":
                    report = admin.deactivate(manifest, actor)
                else:
                    report = smoke(admin, manifest, (retrieval_factory or _default_retrieval)(), data["queries"])
                result = {"organizationId": org, "correlationId": cor, "versionId": data["versionId"],
                          "documentId": manifest["documents"][0]["document_id"],
                          "status": report["documents"][0]["status"] if action != "smoke" else "PUBLISHED"}
                if action == "smoke":
                    result.update(passed=report["passed"], queriesChecked=report["queries_checked"],
                                  versionsRetrieved=report["versions_retrieved"])
            elif action == "list":
                result = {"organizationId": org, "correlationId": cor, "documents": admin.list_documents()}
            elif action == "detail":
                result = {"organizationId": org, "correlationId": cor, "document": admin.document_detail(doc_id)}
            elif action == "versions":
                result = {"organizationId": org, "correlationId": cor, "documentId": doc_id,
                          "versions": admin.document_versions(doc_id)}
            else:
                result = {"organizationId": org, "correlationId": cor, "documentId": doc_id,
                          "versionId": version_path, "chunks": admin.review_chunks(doc_id, version_path)}
        audit_name = {"dry-run": "knowledge_dry_run", "ingest": "knowledge_ingested",
                      "validate": "knowledge_validated", "publish": "knowledge_published",
                      "smoke": "knowledge_smoke_tested", "deactivate": "knowledge_deactivated"}.get(action, "knowledge_" + action)
        log(audit_name, {"organizationId": org, "correlationId": cor,
              "documentId": doc_id if method == "GET" else result.get("documentId") or result.get("documents", [{}])[0].get("documentId"),
              "versionId": version_path if method == "GET" else result.get("versionId") or result.get("documents", [{}])[0].get("versionId"),
              "actor": actor, "outcome": "success", "timestamp": datetime.now(timezone.utc).isoformat()})
        return 200, result
    except KnowledgeError as exc:
        code = str(exc)
        status = (404 if code in {"NOT_FOUND", "DOCUMENT_NOT_FOUND", "VERSION_NOT_FOUND_IN_TENANT", "ORGANIZATION_NOT_ACTIVE_OR_MISSING"}
                  else 409 if code in {"STALE_VERSION", "APPROVAL_REQUIRED", "VERSION_NOT_REVIEWABLE", "ROLLBACK_REQUIRES_CURRENT_PUBLICATION"}
                  else 413 if code in {"REQUEST_TOO_LARGE", "SOURCE_TOO_LARGE"}
                  else 504 if code == "KNOWLEDGE_DEADLINE_EXCEEDED" else 400)
        log("knowledge_request_rejected", {"organizationId": org, "correlationId": cor,
             "actor": actor, "action": action, "outcome": code, "timestamp": datetime.now(timezone.utc).isoformat()})
        return status, {"error": code, "correlationId": cor}
    except Exception:
        log("knowledge_request_failed", {"organizationId": org, "correlationId": cor,
             "actor": actor, "action": action, "outcome": "unavailable", "timestamp": datetime.now(timezone.utc).isoformat()})
        return 503, {"error": "KNOWLEDGE_UNAVAILABLE", "correlationId": cor}
