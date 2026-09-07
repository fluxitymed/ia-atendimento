from __future__ import annotations

from typing import Any

from ai_agent_runtime.sandbox_ids import LEONARDO_ORG_ID, deterministic_sandbox_uuid


CARVALHO_ORGANIZATION_ID = deterministic_sandbox_uuid(LEONARDO_ORG_ID)


def carvalho_runtime_seed() -> dict[str, Any]:
    """Returns non-secret rows for registering the existing Carvalho organization."""
    return {
        "organizations": [
            {
                "id": CARVALHO_ORGANIZATION_ID,
                "name": "Clinica Carvalho e Tavares Odontologia Integrada",
                "slug": "carvalho-tavares",
                "status": "active",
            }
        ],
        "organization_ai_configs": [
            {
                "organization_id": CARVALHO_ORGANIZATION_ID,
                "assistant_name": "Bruna",
                "assistant_role": "atendimento comercial",
                "clinic_name": "Clinica Carvalho e Tavares Odontologia Integrada",
                "doctor_name": "Dr. Leonardo Carvalho",
                "sales_goal": "conduzir o paciente ate avaliacao quando houver interesse em procedimento",
                "primary_conversion_action": "avaliacao",
                "max_discovery_depth": 3,
                "cta_style": "natural e sem pressao",
                "appointment_flow": "somente quando contexto de agendamento estiver ativo",
                "business_hours": "segunda a sexta, 8h as 19h; sabado, 8h as 12h",
                "locations": ["Matatu/Brotas", "Hospital da Bahia"],
                "status": "active",
            }
        ],
        "organization_integrations": [
            {
                "organization_id": CARVALHO_ORGANIZATION_ID,
                "provider": "OPENAI",
                "provider_account_id": "openai-project-carvalho",
                "status": "active",
            },
            {
                "organization_id": CARVALHO_ORGANIZATION_ID,
                "provider": "ZAPI",
                "provider_account_id": "ZAPI_INSTANCE_ID",
                "status": "active",
            },
        ],
        "organization_credentials": [
            {
                "organization_id": CARVALHO_ORGANIZATION_ID,
                "provider": "OPENAI",
                "credential_ref": "OPENAI_API_KEY_CARVALHO",
                "status": "active",
            },
            {
                "organization_id": CARVALHO_ORGANIZATION_ID,
                "provider": "ZAPI",
                "credential_ref": "ZAPI_INSTANCE_TOKEN_CARVALHO",
                "status": "active",
            },
        ],
    }
