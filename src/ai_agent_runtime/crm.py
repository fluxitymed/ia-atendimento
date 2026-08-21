from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .providers import CRMProvider


ALLOWED_PROGRESSIVE_FIELDS = {
    "name",
    "phone",
    "procedure_interest",
    "professional_interest",
    "unit",
    "conversation_stage",
    "qualification",
    "loss_reason",
    "scheduling_intent",
    "selected_datetime",
    "appointment_completed",
    "handoff",
    "notes",
}


@dataclass(frozen=True)
class TrustedField:
    value: Any
    source: str


def build_crm_field_update(fields: dict[str, TrustedField | None]) -> dict[str, Any]:
    update: dict[str, Any] = {}
    for key, trusted in fields.items():
        if key not in ALLOWED_PROGRESSIVE_FIELDS:
            continue
        if trusted is None or trusted.value is None or trusted.value == "":
            continue
        if not trusted.source:
            continue
        update[key] = trusted.value
    return update


class CRMTools:
    def __init__(self, provider: CRMProvider):
        self.provider = provider

    def upsert_contact(self, *, organization_id: str, contact: dict[str, Any]) -> dict[str, Any]:
        clean_contact = {key: value for key, value in contact.items() if value not in (None, "")}
        return self.provider.upsert_contact(organization_id=organization_id, contact=clean_contact)

    def update_progressive_fields(
        self,
        *,
        organization_id: str,
        contact_id: str,
        fields: dict[str, TrustedField | None],
    ) -> dict[str, Any]:
        update = build_crm_field_update(fields)
        return self.provider.update_fields(
            organization_id=organization_id,
            contact_id=contact_id,
            fields=update,
        )
