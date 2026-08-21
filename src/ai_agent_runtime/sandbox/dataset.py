from __future__ import annotations

from dataclasses import dataclass


AURORA_ORG_ID = "sandbox-org-aurora"
BOREAL_ORG_ID = "sandbox-org-boreal"
DATASET_VERSION = "2026-08-20.live-sandbox.v1"


@dataclass(frozen=True)
class SandboxDocument:
    id: str
    organization_id: str
    title: str
    content: str
    document_type: str = "DOCUMENT"
    knowledge_mode: str = "OPEN_WORLD"
    closed_world_completeness_approved: bool = False
    status: str = "PUBLISHED"
    environment: str = "sandbox"


@dataclass(frozen=True)
class SandboxOrganization:
    id: str
    name: str
    environment: str = "sandbox"


@dataclass(frozen=True)
class SandboxDataset:
    version: str
    organizations: tuple[SandboxOrganization, ...]
    documents: tuple[SandboxDocument, ...]
    fictitious: bool = True


def build_sandbox_dataset() -> SandboxDataset:
    return SandboxDataset(
        version=DATASET_VERSION,
        organizations=(
            SandboxOrganization(id=AURORA_ORG_ID, name="Clinica Aurora Sandbox"),
            SandboxOrganization(id=BOREAL_ORG_ID, name="Clinica Boreal Sandbox"),
        ),
        documents=(
            SandboxDocument(
                id="aurora-procedure-catalog",
                organization_id=AURORA_ORG_ID,
                title="Catalogo fechado de procedimentos Aurora",
                document_type="PROCEDURE_CATALOG",
                knowledge_mode="CLOSED_WORLD",
                closed_world_completeness_approved=True,
                content="Botox\nPreenchimento labial\nBlefaroplastia",
            ),
            SandboxDocument(
                id="aurora-prices",
                organization_id=AURORA_ORG_ID,
                title="Informacoes comerciais Aurora",
                content=(
                    "Profissionais ficticios: Dra. Marina Alves e Dr. Rafael Lima.\n"
                    "Consulta com Dra. Marina: R$ 500.\n"
                    "Pagamento: PIX ou cartao.\n"
                    "Retorno: incluso em ate 30 dias.\n"
                    "Blefaroplastia nao inclui servico adicional de hospedagem."
                ),
            ),
            SandboxDocument(
                id="boreal-prices",
                organization_id=BOREAL_ORG_ID,
                title="Informacoes comerciais Boreal",
                content="Consulta com Dra. Helena Costa: R$ 900.",
            ),
        ),
    )


def ingestion_pipeline_gap_report() -> dict[str, str]:
    return {
        "document": "IMPLEMENTED",
        "normalization": "IMPLEMENTED_CONCEPTUAL",
        "chunking": "IMPLEMENTED_DOMAIN",
        "embedding": "IMPLEMENTED_PROVIDER",
        "pgvector": "IMPLEMENTED_MIGRATION",
        "remote_supabase_write": "READY_FOR_LIVE_EXECUTION",
        "live_retrieval": "READY_FOR_LIVE_EXECUTION",
    }
