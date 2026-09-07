from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5


LEONARDO_ORG_ID = "sandbox-org-dr-leonardo-carvalho"
AURORA_ORG_ID = "sandbox-org-aurora"
BOREAL_ORG_ID = "sandbox-org-boreal"
PRIMARY_SANDBOX_ORG_ID = LEONARDO_ORG_ID
SECONDARY_SANDBOX_ORG_ID = BOREAL_ORG_ID
DATASET_VERSION = "2026-09-02.dr-leonardo-sandbox.v2"


def deterministic_sandbox_uuid(logical_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"ai-atendimento:{logical_id}"))
