from __future__ import annotations

from collections import OrderedDict

from .providers import RetrievalProvider, RetrievalResult


class RetrievalIsolationError(RuntimeError):
    pass


def require_organization_id(organization_id: str) -> None:
    if not organization_id:
        raise RetrievalIsolationError("organizationId is required for retrieval")


class HybridRetrievalService:
    def __init__(self, provider: RetrievalProvider):
        self.provider = provider

    def search(self, *, organization_id: str, query: str) -> list[RetrievalResult]:
        require_organization_id(organization_id)
        lexical = self.provider.lexical_search(organization_id=organization_id, query=query)
        vector = self.provider.vector_search(organization_id=organization_id, query=query)
        fused: OrderedDict[str, RetrievalResult] = OrderedDict()
        for result in sorted([*lexical, *vector], key=lambda item: item.score, reverse=True):
            if result.organization_id != organization_id:
                raise RetrievalIsolationError("cross-organization retrieval result rejected")
            if result.id not in fused:
                fused[result.id] = result
        return list(fused.values())
