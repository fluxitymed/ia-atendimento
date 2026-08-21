from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from ai_agent_runtime.providers import RetrievalResult
from ai_agent_runtime.retrieval import RetrievalIsolationError, require_organization_id


@dataclass(frozen=True)
class SupabaseCandidate:
    id: str
    organization_id: str
    document_id: str
    document_version_id: str
    content: str
    score: float
    source: str
    status: str
    processing_valid: bool
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    metadata: dict | None = None


class SupabaseRetrievalTransport(Protocol):
    def lexical_candidates(self, *, organization_id: str, query: str, limit: int) -> list[SupabaseCandidate]:
        ...

    def vector_candidates(self, *, organization_id: str, query: str, limit: int) -> list[SupabaseCandidate]:
        ...


@dataclass(frozen=True)
class HybridEvidence:
    result: RetrievalResult
    metadata: dict
    grounding_required: bool = True


def is_candidate_eligible(candidate: SupabaseCandidate, now: datetime) -> bool:
    if candidate.status != "PUBLISHED":
        return False
    if candidate.processing_valid is not True:
        return False
    if candidate.effective_from and candidate.effective_from > now:
        return False
    if candidate.effective_until and candidate.effective_until < now:
        return False
    return True


class SupabaseHybridRetrievalProvider:
    def __init__(self, transport: SupabaseRetrievalTransport, *, now: datetime | None = None):
        self.transport = transport
        self.now = now or datetime.now(timezone.utc)

    def search(self, *, organization_id: str, query: str, limit: int = 8) -> list[HybridEvidence]:
        require_organization_id(organization_id)
        lexical = self.transport.lexical_candidates(organization_id=organization_id, query=query, limit=limit)
        vector = self.transport.vector_candidates(organization_id=organization_id, query=query, limit=limit)

        fused: dict[str, HybridEvidence] = {}
        for candidate in sorted([*lexical, *vector], key=lambda item: item.score, reverse=True):
            if candidate.organization_id != organization_id:
                raise RetrievalIsolationError("cross-organization retrieval result rejected")
            if not is_candidate_eligible(candidate, self.now):
                continue
            if candidate.id in fused:
                continue
            fused[candidate.id] = HybridEvidence(
                result=RetrievalResult(
                    id=candidate.id,
                    organization_id=candidate.organization_id,
                    document_version_id=candidate.document_version_id,
                    content=candidate.content,
                    score=candidate.score,
                    source=candidate.source,
                ),
                metadata={
                    "documentId": candidate.document_id,
                    "documentVersionId": candidate.document_version_id,
                    "source": candidate.source,
                    "score": candidate.score,
                    **(candidate.metadata or {}),
                },
            )
        return list(fused.values())[:limit]
