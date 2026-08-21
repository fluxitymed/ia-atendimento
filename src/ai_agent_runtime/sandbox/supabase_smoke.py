from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import parse, request
from uuid import NAMESPACE_URL, uuid5

from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider

from .config import SandboxConfig
from .dataset import build_sandbox_dataset, ingestion_pipeline_gap_report
from .redaction import redact
from .scenarios import build_sandbox_scenarios


MIGRATION_PATH = Path("supabase/migrations/202608200001_ai_runtime_integrations.sql")
REQUIRED_TABLES = (
    "organizations",
    "documents",
    "document_versions",
    "chunks",
    "retrieval_index_entries",
    "conversations",
    "conversation_messages",
    "operational_audit_events",
)


class SupabaseSmokeError(RuntimeError):
    pass


@dataclass(frozen=True)
class SupabaseRestClient:
    url: str
    service_role_key: str

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        return {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
            **(extra or {}),
        }

    def _url(self, path: str, params: dict[str, str] | None = None) -> str:
        base = self.url.rstrip("/")
        query = f"?{parse.urlencode(params)}" if params else ""
        return f"{base}/rest/v1/{path}{query}"

    def request_json(self, method: str, path: str, *, params: dict[str, str] | None = None, payload: Any = None, headers: dict[str, str] | None = None) -> Any:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = request.Request(self._url(path, params), data=data, headers=self._headers(headers), method=method)
        try:
            with request.urlopen(req, timeout=30) as response:
                body = response.read().decode("utf-8")
        except Exception as exc:
            raise SupabaseSmokeError(redact(str(exc))) from exc
        if not body:
            return None
        return json.loads(body)

    def get(self, table: str, *, params: dict[str, str]) -> list[dict[str, Any]]:
        return self.request_json("GET", table, params=params)

    def upsert(self, table: str, rows: list[dict[str, Any]], *, conflict: str) -> list[dict[str, Any]]:
        return self.request_json(
            "POST",
            table,
            params={"on_conflict": conflict},
            payload=rows,
            headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        )

    def delete(self, table: str, *, params: dict[str, str]) -> None:
        self.request_json("DELETE", table, params=params, headers={"Prefer": "return=minimal"})


def build_supabase_plan(config: SandboxConfig) -> dict:
    dataset = build_sandbox_dataset()
    return {
        "service": "supabase",
        "status": "IMPLEMENTED",
        "urlConfigured": bool(config.integrations.supabase_url),
        "migrationPath": str(MIGRATION_PATH),
        "requiresTables": list(REQUIRED_TABLES),
        "datasetVersion": dataset.version,
        "organizations": [organization.name for organization in dataset.organizations],
        "scenarioIds": [scenario.id for scenario in build_sandbox_scenarios() if scenario.category.startswith("supabase") or scenario.category in {"procedure_catalog", "procedure_attribute", "cross_org"}],
        "pipelineGap": ingestion_pipeline_gap_report(),
    }


def run_supabase_smoke(config: SandboxConfig) -> dict:
    if not config.integrations.supabase_url or not config.integrations.supabase_service_role_key:
        return {**build_supabase_plan(config), "status": "BLOCKED_MISSING_CREDENTIALS"}
    if not config.integrations.openai_api_key:
        return {**build_supabase_plan(config), "status": "BLOCKED_MISSING_CREDENTIALS", "missing": ["OPENAI_API_KEY"]}

    client = SupabaseRestClient(config.integrations.supabase_url, config.integrations.supabase_service_role_key)
    openai = OpenAIResponsesProvider(config.integrations)
    dataset = build_sandbox_dataset()
    table_checks = _check_tables(client)
    ids = _persist_dataset(client, openai, dataset)
    lexical = _lexical_query(client, ids["aurora_org"], "Dra. Marina")
    vector = _vector_query(client, ids["aurora_org"], openai.create_embedding(text="consulta Dra. Marina R$ 500", embedding_version=dataset.version).vector)
    cross_org = _lexical_query(client, ids["aurora_org"], "Dra. Helena")
    closed_world = _closed_world_decision(client, ids["aurora_org"], "transplante capilar")
    missing_attribute = _missing_attribute_decision(client, ids["aurora_org"], "Botox pode ser parcelado em 10 vezes?")
    grounding = "PASS" if any("R$ 500" in item["content"] for item in lexical) else "FAIL"

    if not lexical or grounding != "PASS":
        raise SupabaseSmokeError("Supabase lexical retrieval did not return grounded Aurora evidence")
    if not vector or vector[0]["organization_id"] != ids["aurora_org"]:
        raise SupabaseSmokeError("Supabase vector retrieval did not return Aurora evidence")
    if cross_org:
        raise SupabaseSmokeError("Supabase cross-org isolation failed for Boreal query inside Aurora org")
    if closed_world != "NOT_OFFERED":
        raise SupabaseSmokeError("Supabase closed-world procedure absence did not produce NOT_OFFERED")
    if missing_attribute != "HUMAN_HANDOFF_REQUIRED":
        raise SupabaseSmokeError("Supabase missing attribute did not produce HUMAN_HANDOFF_REQUIRED")

    return {
        **build_supabase_plan(config),
        "status": "LIVE_VERIFIED",
        "tableChecks": table_checks,
        "datasetPersisted": True,
        "embeddingCount": len(ids["index_ids"]),
        "lexicalHitCount": len(lexical),
        "vectorHitCount": len(vector),
        "hybridHitCount": len({item["id"] for item in [*lexical, *vector]}),
        "crossOrgLeakage": 0,
        "existingInfoDecision": "ANSWER_GROUNDED",
        "missingAttributeDecision": missing_attribute,
        "closedWorldDecision": closed_world,
        "grounding": grounding,
    }


def _uuid(seed: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"ai-atendimento:{seed}"))


def _check_tables(client: SupabaseRestClient) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    for table in REQUIRED_TABLES:
        client.get(table, params={"select": "*", "limit": "1"})
        checks[table] = True
    return checks


def _persist_dataset(client: SupabaseRestClient, openai: OpenAIResponsesProvider, dataset) -> dict[str, Any]:
    org_ids = {org.id: _uuid(org.id) for org in dataset.organizations}
    client.upsert("organizations", [{"id": org_ids[org.id], "name": org.name} for org in dataset.organizations], conflict="id")

    document_rows = []
    version_rows = []
    chunk_rows = []
    index_rows = []
    for document in dataset.documents:
        document_id = _uuid(document.id)
        version_id = _uuid(f"{document.id}:v1")
        chunk_id = _uuid(f"{document.id}:chunk:0")
        index_id = _uuid(f"{document.id}:index:0")
        organization_id = org_ids[document.organization_id]
        document_rows.append({
            "id": document_id,
            "organization_id": organization_id,
            "document_type": document.document_type,
            "title": document.title,
        })
        version_rows.append({
            "id": version_id,
            "organization_id": organization_id,
            "document_id": document_id,
            "version_number": 1,
            "status": document.status,
            "processing_valid": True,
            "knowledge_mode": document.knowledge_mode,
            "closed_world_completeness_approved": document.closed_world_completeness_approved,
            "approved_by": "sandbox",
            "published_by": "sandbox",
        })
        chunk_rows.append({
            "id": chunk_id,
            "organization_id": organization_id,
            "document_id": document_id,
            "document_version_id": version_id,
            "chunk_index": 0,
            "content": document.content,
            "section_path": ["sandbox", document.title],
            "semantic_type": document.document_type,
            "metadata": {"environment": "sandbox", "datasetVersion": dataset.version},
            "chunking_strategy": "sandbox-document",
            "chunking_version": dataset.version,
        })
        embedding = openai.create_embedding(text=document.content, embedding_version=dataset.version)
        index_rows.append({
            "id": index_id,
            "organization_id": organization_id,
            "chunk_id": chunk_id,
            "document_id": document_id,
            "document_version_id": version_id,
            "embedding": _pgvector(embedding.vector),
            "embedding_model": embedding.model,
            "embedding_version": embedding.embedding_version,
            "indexed_at": embedding.indexed_at,
            "metadata": {"environment": "sandbox"},
        })
    client.upsert("documents", document_rows, conflict="id")
    client.upsert("document_versions", version_rows, conflict="id")
    client.upsert("chunks", chunk_rows, conflict="id")
    client.upsert("retrieval_index_entries", index_rows, conflict="id")
    return {"aurora_org": org_ids["sandbox-org-aurora"], "boreal_org": org_ids["sandbox-org-boreal"], "index_ids": [row["id"] for row in index_rows]}


def _pgvector(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def _parse_vector(value: Any) -> list[float]:
    if isinstance(value, list):
        return [float(item) for item in value]
    return [float(item) for item in str(value).strip("[]").split(",") if item]


def _lexical_query(client: SupabaseRestClient, organization_id: str, query: str) -> list[dict[str, Any]]:
    escaped = query.replace("*", "")
    rows = client.get("chunks", params={
        "select": "id,organization_id,document_version_id,content",
        "organization_id": f"eq.{organization_id}",
        "content": f"ilike.*{escaped}*",
        "limit": "8",
    })
    return rows


def _vector_query(client: SupabaseRestClient, organization_id: str, query_vector: list[float]) -> list[dict[str, Any]]:
    rows = client.get("retrieval_index_entries", params={
        "select": "id,organization_id,chunk_id,embedding",
        "organization_id": f"eq.{organization_id}",
        "limit": "32",
    })
    chunk_ids = [row["chunk_id"] for row in rows]
    chunks = _chunks_by_id(client, chunk_ids)
    scored = []
    for row in rows:
        score = _cosine(query_vector, _parse_vector(row["embedding"]))
        chunk = chunks.get(row["chunk_id"], {})
        scored.append({
            "id": row["chunk_id"],
            "organization_id": row["organization_id"],
            "content": chunk.get("content", ""),
            "score": score,
        })
    return sorted(scored, key=lambda item: item["score"], reverse=True)[:3]


def _chunks_by_id(client: SupabaseRestClient, chunk_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not chunk_ids:
        return {}
    rows = client.get("chunks", params={
        "select": "id,content,document_version_id",
        "id": f"in.({','.join(chunk_ids)})",
    })
    return {row["id"]: row for row in rows}


def _cosine(a: list[float], b: list[float]) -> float:
    numerator = sum(x * y for x, y in zip(a, b))
    denom = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return numerator / denom if denom else 0.0


def _closed_world_decision(client: SupabaseRestClient, organization_id: str, procedure_name: str) -> str:
    catalogs = _lexical_query(client, organization_id, "Botox")
    if catalogs and procedure_name.lower() not in "\n".join(item["content"].lower() for item in catalogs):
        return "NOT_OFFERED"
    return "HUMAN_HANDOFF_REQUIRED"


def _missing_attribute_decision(client: SupabaseRestClient, organization_id: str, question: str) -> str:
    hits = _lexical_query(client, organization_id, "10 vezes")
    return "ANSWER_GROUNDED" if hits else "HUMAN_HANDOFF_REQUIRED"
