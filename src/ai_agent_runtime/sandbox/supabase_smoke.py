from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import parse, request
from uuid import NAMESPACE_URL, uuid5

from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.sandbox_ids import BOREAL_ORG_ID, LEONARDO_ORG_ID

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
    primary_org = ids["primary_org"]
    version_state = _document_version_state(client, primary_org)
    lexical = _lexical_query(client, primary_org, "implantes")
    vector = _vector_query(client, primary_org, openai.create_embedding(text="Scanner Virtuo odontologia digital", embedding_version=dataset.version).vector)
    cross_org = _lexical_query(client, primary_org, "Dra. Helena")
    closed_world = _closed_world_decision(client, primary_org, "transplante capilar")
    missing_attribute = _missing_attribute_decision(client, primary_org, "Qual o valor do implante?")
    free_evaluation = _free_evaluation_decision(client, primary_org, "Quanto custa a avaliacao?")
    grounding = "PASS" if any("Dr. Leonardo Carvalho" in item["content"] or "implantes" in item["content"] for item in lexical) else "FAIL"

    if not lexical or grounding != "PASS":
        raise SupabaseSmokeError("Supabase lexical retrieval did not return grounded Dr. Leonardo evidence")
    if not vector or vector[0]["organization_id"] != primary_org:
        raise SupabaseSmokeError("Supabase vector retrieval did not return Dr. Leonardo evidence")
    if cross_org:
        raise SupabaseSmokeError("Supabase cross-org isolation failed for Boreal query inside Dr. Leonardo org")
    if closed_world != "HUMAN_HANDOFF_REQUIRED":
        raise SupabaseSmokeError("Supabase open-world procedure absence should not produce NOT_OFFERED")
    if missing_attribute != "ANSWER_GROUNDED":
        raise SupabaseSmokeError("Supabase authorized post-evaluation pricing policy was not retrieved")
    if free_evaluation != "ANSWER_GROUNDED":
        raise SupabaseSmokeError("Supabase authorized free evaluation policy was not retrieved")
    if any(row["status"] == "PUBLISHED" and row["version_number"] == 1 for row in version_state):
        raise SupabaseSmokeError("Supabase old Dr. Leonardo briefing version is still current")

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
        "freeEvaluationDecision": free_evaluation,
        "procedureAbsenceDecision": closed_world,
        "grounding": grounding,
        "documentVersions": version_state,
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
    superseded_version_rows = []
    version_rows = []
    chunk_rows = []
    index_rows = []
    now = datetime.now(timezone.utc).isoformat()
    for document in dataset.documents:
        document_id = _uuid(document.id)
        previous_version_id = _uuid(f"{document.id}:v1")
        intermediate_version_id = _uuid(f"{document.id}:v2")
        current_version_number = _dataset_version_number(dataset.version)
        current_version_label = f"v{current_version_number}"
        current_version_id = _uuid(f"{document.id}:{current_version_label}")
        chunk_id = _uuid(f"{document.id}:chunk:0:{current_version_label}")
        index_id = _uuid(f"{document.id}:index:0:{current_version_label}")
        organization_id = org_ids[document.organization_id]
        document_rows.append({
            "id": document_id,
            "organization_id": organization_id,
            "document_type": document.document_type,
            "title": document.title,
        })
        superseded_version_rows.append({
            "id": previous_version_id,
            "organization_id": organization_id,
            "document_id": document_id,
            "version_number": 1,
            "status": "SUPERSEDED",
            "effective_until": now,
            "processing_valid": False,
            "knowledge_mode": document.knowledge_mode,
            "closed_world_completeness_approved": document.closed_world_completeness_approved,
            "approved_by": "sandbox",
            "published_by": "sandbox",
        })
        if current_version_number > 2:
            superseded_version_rows.append({
                "id": intermediate_version_id,
                "organization_id": organization_id,
                "document_id": document_id,
                "version_number": 2,
                "status": "SUPERSEDED",
                "effective_until": now,
                "processing_valid": False,
                "knowledge_mode": document.knowledge_mode,
                "closed_world_completeness_approved": document.closed_world_completeness_approved,
                "approved_by": "sandbox",
                "published_by": "sandbox",
            })
        version_rows.append({
            "id": current_version_id,
            "organization_id": organization_id,
            "document_id": document_id,
            "version_number": current_version_number,
            "status": document.status,
            "processing_valid": True,
            "knowledge_mode": document.knowledge_mode,
            "closed_world_completeness_approved": document.closed_world_completeness_approved,
            "approved_by": "sandbox",
            "published_by": "sandbox",
            "published_at": now,
            "supersedes_version_id": intermediate_version_id if current_version_number > 2 else previous_version_id,
        })
        chunk_rows.append({
            "id": chunk_id,
            "organization_id": organization_id,
            "document_id": document_id,
            "document_version_id": current_version_id,
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
            "document_version_id": current_version_id,
            "embedding": _pgvector(embedding.vector),
            "embedding_model": embedding.model,
            "embedding_version": embedding.embedding_version,
            "indexed_at": embedding.indexed_at,
            "metadata": {"environment": "sandbox"},
        })
    client.upsert("documents", document_rows, conflict="id")
    client.upsert("document_versions", superseded_version_rows, conflict="id")
    client.upsert("document_versions", version_rows, conflict="id")
    client.upsert("chunks", chunk_rows, conflict="id")
    client.upsert("retrieval_index_entries", index_rows, conflict="id")
    return {
        "primary_org": org_ids[LEONARDO_ORG_ID],
        "leonardo_org": org_ids[LEONARDO_ORG_ID],
        "boreal_org": org_ids[BOREAL_ORG_ID],
        "index_ids": [row["id"] for row in index_rows],
        "version_ids": [row["id"] for row in version_rows],
    }


def _dataset_version_number(dataset_version: str) -> int:
    match = re.search(r"\.v([0-9]+)(?:$|[^0-9])", dataset_version)
    return int(match.group(1)) if match else 2


def _pgvector(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def _parse_vector(value: Any) -> list[float]:
    if isinstance(value, list):
        return [float(item) for item in value]
    return [float(item) for item in str(value).strip("[]").split(",") if item]


def _lexical_query(client: SupabaseRestClient, organization_id: str, query: str) -> list[dict[str, Any]]:
    version_ids = _published_processed_version_ids(client, organization_id)
    if not version_ids:
        return []
    escaped = query.replace("*", "")
    rows = client.get("chunks", params={
        "select": "id,organization_id,document_version_id,content",
        "organization_id": f"eq.{organization_id}",
        "document_version_id": f"in.({','.join(sorted(version_ids))})",
        "content": f"ilike.*{escaped}*",
        "limit": "8",
    })
    return rows


def _vector_query(client: SupabaseRestClient, organization_id: str, query_vector: list[float]) -> list[dict[str, Any]]:
    version_ids = _published_processed_version_ids(client, organization_id)
    if not version_ids:
        return []
    rows = client.get("retrieval_index_entries", params={
        "select": "id,organization_id,chunk_id,document_version_id,embedding",
        "organization_id": f"eq.{organization_id}",
        "document_version_id": f"in.({','.join(sorted(version_ids))})",
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


def _published_processed_version_ids(client: SupabaseRestClient, organization_id: str) -> set[str]:
    rows = client.get("document_versions", params={
        "select": "id,organization_id,status,processing_valid",
        "organization_id": f"eq.{organization_id}",
        "status": "eq.PUBLISHED",
        "processing_valid": "is.true",
        "limit": "100",
    })
    return {
        str(row["id"])
        for row in rows
        if row.get("organization_id") == organization_id and row.get("status") == "PUBLISHED" and row.get("processing_valid") is True
    }


def _document_version_state(client: SupabaseRestClient, organization_id: str) -> list[dict[str, Any]]:
    rows = client.get("document_versions", params={
        "select": "id,organization_id,document_id,version_number,status,processing_valid,supersedes_version_id",
        "organization_id": f"eq.{organization_id}",
        "order": "document_id.asc,version_number.asc",
        "limit": "100",
    })
    return [
        {
            "id": row.get("id"),
            "document_id": row.get("document_id"),
            "version_number": row.get("version_number"),
            "status": row.get("status"),
            "processing_valid": row.get("processing_valid"),
            "supersedes_version_id": row.get("supersedes_version_id"),
        }
        for row in rows
    ]


def _cosine(a: list[float], b: list[float]) -> float:
    numerator = sum(x * y for x, y in zip(a, b))
    denom = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return numerator / denom if denom else 0.0


def _closed_world_decision(client: SupabaseRestClient, organization_id: str, procedure_name: str) -> str:
    catalogs = _lexical_query(client, organization_id, "servicos")
    catalog_text = "\n".join(item["content"].lower() for item in catalogs)
    closed_world_approved = "completude" in catalog_text and "nao comprova" not in catalog_text
    if closed_world_approved and catalogs and procedure_name.lower() not in catalog_text:
        return "NOT_OFFERED"
    return "HUMAN_HANDOFF_REQUIRED"


def _missing_attribute_decision(client: SupabaseRestClient, organization_id: str, question: str) -> str:
    hits = _lexical_query(client, organization_id, "Valores dos procedimentos")
    return "ANSWER_GROUNDED" if hits else "HUMAN_HANDOFF_REQUIRED"


def _free_evaluation_decision(client: SupabaseRestClient, organization_id: str, question: str) -> str:
    hits = _lexical_query(client, organization_id, "Avaliacao gratuita")
    evidence_text = "\n".join(row.get("content", "") for row in hits).lower()
    if "avaliacao gratuita" in evidence_text and "busca por procedimento" in evidence_text:
        return "ANSWER_GROUNDED"
    return "HUMAN_HANDOFF_REQUIRED"
