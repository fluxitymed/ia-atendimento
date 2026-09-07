from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from os import environ
from typing import Any, Protocol
from urllib import parse, request

from ai_agent_runtime.commercial import OrganizationCommercialConfig
from ai_agent_runtime.integrations.config import load_env_file


ACTIVE_ORGANIZATION_STATUSES = {"active", "ACTIVE", "enabled", "ENABLED"}
OPENAI_PROVIDER = "OPENAI"
ZAPI_PROVIDER = "ZAPI"


class OrganizationConfigError(RuntimeError):
    pass


class OrganizationCredentialError(RuntimeError):
    pass


@dataclass(frozen=True)
class OrganizationRuntimeConfig:
    organization_id: str
    assistant_name: str | None = None
    assistant_role: str | None = None
    clinic_name: str | None = None
    doctor_name: str | None = None
    sales_goal: str = OrganizationCommercialConfig.sales_goal
    primary_conversion_action: str = OrganizationCommercialConfig.primary_conversion_action
    max_discovery_depth: int = OrganizationCommercialConfig.max_discovery_depth
    cta_style: str = OrganizationCommercialConfig.cta_style
    appointment_flow: str = OrganizationCommercialConfig.appointment_flow
    business_hours: str | None = None
    locations: tuple[str, ...] = ()
    status: str = "active"

    def is_active(self) -> bool:
        return self.status in ACTIVE_ORGANIZATION_STATUSES

    def to_commercial_config(self) -> OrganizationCommercialConfig:
        return OrganizationCommercialConfig(
            assistant_name=self.assistant_name,
            assistant_role=self.assistant_role,
            clinic_name=self.clinic_name,
            doctor_name=self.doctor_name,
            sales_goal=self.sales_goal,
            primary_conversion_action=self.primary_conversion_action,
            max_discovery_depth=self.max_discovery_depth,
            cta_style=self.cta_style,
            appointment_flow=self.appointment_flow,
            business_hours=self.business_hours,
            locations=self.locations,
        )

    def safe_dict(self) -> dict[str, Any]:
        return {
            "organizationId": self.organization_id,
            "assistantNameConfigured": bool(self.assistant_name),
            "clinicNameConfigured": bool(self.clinic_name),
            "doctorNameConfigured": bool(self.doctor_name),
            "locationCount": len(self.locations),
            "status": self.status,
        }


class OrganizationConfigRepository(Protocol):
    def get_by_organization_id(self, organization_id: str) -> OrganizationRuntimeConfig | None:
        ...

    def is_active(self, organization_id: str) -> bool:
        ...


class InMemoryOrganizationConfigRepository:
    def __init__(self, configs: list[OrganizationRuntimeConfig] | tuple[OrganizationRuntimeConfig, ...]):
        self._configs = {config.organization_id: config for config in configs}

    def get_by_organization_id(self, organization_id: str) -> OrganizationRuntimeConfig | None:
        return self._configs.get(organization_id)

    def is_active(self, organization_id: str) -> bool:
        config = self.get_by_organization_id(organization_id)
        return bool(config and config.is_active())


class EnvironmentOrganizationConfigRepository:
    """Loads non-secret organization config from ORGANIZATION_RUNTIME_CONFIG_JSON."""

    def __init__(self, raw_json: str | None = None):
        self.raw_json = raw_json

    @classmethod
    def from_env(cls) -> "EnvironmentOrganizationConfigRepository":
        load_env_file()
        return cls(environ.get("ORGANIZATION_RUNTIME_CONFIG_JSON"))

    def get_by_organization_id(self, organization_id: str) -> OrganizationRuntimeConfig | None:
        data = _loads_mapping(self.raw_json)
        row = data.get(organization_id)
        if not isinstance(row, dict):
            return None
        return organization_runtime_config_from_mapping(organization_id, row)

    def is_active(self, organization_id: str) -> bool:
        config = self.get_by_organization_id(organization_id)
        return bool(config and config.is_active())


class LegacyEnvironmentOrganizationConfigRepository:
    def __init__(self, organization_id: str):
        self.organization_id = organization_id

    def get_by_organization_id(self, organization_id: str) -> OrganizationRuntimeConfig | None:
        if organization_id != self.organization_id:
            return None
        load_env_file()
        return OrganizationRuntimeConfig(
            organization_id=organization_id,
            assistant_name=_env_optional("AI_ASSISTANT_NAME"),
            assistant_role=_env_optional("AI_ASSISTANT_ROLE"),
            clinic_name=_env_optional("AI_CLINIC_NAME"),
            doctor_name=_env_optional("AI_DOCTOR_NAME"),
            sales_goal=environ.get("AI_SALES_GOAL", OrganizationCommercialConfig.sales_goal),
            primary_conversion_action=environ.get("AI_PRIMARY_CONVERSION_ACTION", OrganizationCommercialConfig.primary_conversion_action),
            max_discovery_depth=int(environ.get("AI_MAX_DISCOVERY_DEPTH", str(OrganizationCommercialConfig.max_discovery_depth))),
            cta_style=environ.get("AI_CTA_STYLE", OrganizationCommercialConfig.cta_style),
            appointment_flow=environ.get("AI_APPOINTMENT_FLOW", OrganizationCommercialConfig.appointment_flow),
            business_hours=_env_optional("AI_BUSINESS_HOURS"),
            locations=tuple(item.strip() for item in environ.get("AI_LOCATIONS", "").split("|") if item.strip()),
            status="active",
        )

    def is_active(self, organization_id: str) -> bool:
        return self.get_by_organization_id(organization_id) is not None


class SupabaseOrganizationConfigRepository:
    def __init__(self, *, supabase_url: str, service_role_key: str, transport: "SupabaseOrganizationTransport | None" = None):
        self.transport = transport or SupabaseOrganizationTransport(supabase_url=supabase_url, service_role_key=service_role_key)

    def get_by_organization_id(self, organization_id: str) -> OrganizationRuntimeConfig | None:
        org_rows = self.transport.get(
            "organizations",
            {
                "select": "id,name,status",
                "id": f"eq.{organization_id}",
                "limit": "1",
            },
        )
        if not org_rows:
            return None
        config_rows = self.transport.get(
            "organization_ai_configs",
            {
                "select": "*",
                "organization_id": f"eq.{organization_id}",
                "limit": "1",
            },
        )
        row = {**org_rows[0], **(config_rows[0] if config_rows else {})}
        return organization_runtime_config_from_mapping(
            organization_id,
            {
                **row,
                "clinic_name": row.get("clinic_name") or row.get("name"),
                "status": row.get("status") or "active",
            },
        )

    def is_active(self, organization_id: str) -> bool:
        config = self.get_by_organization_id(organization_id)
        return bool(config and config.is_active())


class CompositeOrganizationConfigRepository:
    def __init__(self, *repositories: OrganizationConfigRepository):
        self.repositories = repositories

    def get_by_organization_id(self, organization_id: str) -> OrganizationRuntimeConfig | None:
        for repository in self.repositories:
            config = repository.get_by_organization_id(organization_id)
            if config:
                return config
        return None

    def is_active(self, organization_id: str) -> bool:
        config = self.get_by_organization_id(organization_id)
        return bool(config and config.is_active())


@dataclass(frozen=True)
class OrganizationCredential:
    organization_id: str
    provider: str
    credential_ref: str
    secret: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def safe_dict(self) -> dict[str, Any]:
        return {
            "organizationId": self.organization_id,
            "provider": self.provider,
            "credentialRef": self.credential_ref,
            "metadataKeys": sorted(self.metadata.keys()),
        }


class OrganizationCredentialProvider(Protocol):
    def get_credential(self, organization_id: str, provider: str) -> OrganizationCredential | None:
        ...


class EnvironmentCredentialProvider:
    """Resolves credential refs from ORGANIZATION_CREDENTIALS_JSON and env vars."""

    def __init__(self, raw_json: str | None = None):
        self.raw_json = raw_json

    @classmethod
    def from_env(cls) -> "EnvironmentCredentialProvider":
        load_env_file()
        return cls(environ.get("ORGANIZATION_CREDENTIALS_JSON"))

    def get_credential(self, organization_id: str, provider: str) -> OrganizationCredential | None:
        data = _loads_mapping(self.raw_json)
        org = data.get(organization_id)
        if not isinstance(org, dict):
            return None
        row = org.get(provider.upper()) or org.get(provider.lower()) or org.get(provider)
        if not isinstance(row, dict):
            return None
        credential_ref = str(row.get("credential_ref") or row.get("credentialRef") or "")
        if not credential_ref:
            return None
        secret = environ.get(credential_ref)
        if not secret:
            return None
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        return OrganizationCredential(
            organization_id=organization_id,
            provider=provider.upper(),
            credential_ref=credential_ref,
            secret=secret,
            metadata=dict(metadata),
        )


class LegacyEnvironmentCredentialProvider:
    def __init__(self, organization_id: str):
        self.organization_id = organization_id

    def get_credential(self, organization_id: str, provider: str) -> OrganizationCredential | None:
        if organization_id != self.organization_id:
            return None
        load_env_file()
        normalized = provider.upper()
        if normalized == OPENAI_PROVIDER and environ.get("OPENAI_API_KEY"):
            return OrganizationCredential(
                organization_id=organization_id,
                provider=OPENAI_PROVIDER,
                credential_ref="OPENAI_API_KEY",
                secret=str(environ["OPENAI_API_KEY"]),
                metadata={"legacy_fallback": True},
            )
        if normalized == ZAPI_PROVIDER and environ.get("ZAPI_INSTANCE_TOKEN"):
            metadata = {
                "base_url": environ.get("ZAPI_BASE_URL"),
                "instance_id": environ.get("ZAPI_INSTANCE_ID"),
                "client_token_ref": "ZAPI_CLIENT_TOKEN" if environ.get("ZAPI_CLIENT_TOKEN") else None,
                "legacy_fallback": True,
            }
            return OrganizationCredential(
                organization_id=organization_id,
                provider=ZAPI_PROVIDER,
                credential_ref="ZAPI_INSTANCE_TOKEN",
                secret=str(environ["ZAPI_INSTANCE_TOKEN"]),
                metadata={key: value for key, value in metadata.items() if value},
            )
        return None


class CompositeCredentialProvider:
    def __init__(self, *providers: OrganizationCredentialProvider):
        self.providers = providers

    def get_credential(self, organization_id: str, provider: str) -> OrganizationCredential | None:
        for credential_provider in self.providers:
            credential = credential_provider.get_credential(organization_id, provider)
            if credential:
                return credential
        return None


@dataclass(frozen=True)
class AiUsageEvent:
    organization_id: str
    conversation_id: str
    provider: str
    model: str
    provider_request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: float | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_row(self) -> dict[str, Any]:
        return {
            "organization_id": self.organization_id,
            "conversation_id": self.conversation_id,
            "provider": self.provider,
            "model": self.model,
            "provider_request_id": self.provider_request_id,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "created_at": self.created_at,
        }


class AiUsageTracker(Protocol):
    def record(self, event: AiUsageEvent) -> bool:
        ...


class InMemoryAiUsageTracker:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.events: list[AiUsageEvent] = []
        self._seen: set[tuple[str, str]] = set()

    def record(self, event: AiUsageEvent) -> bool:
        if self.fail:
            raise OrganizationConfigError("AI_USAGE_RECORD_FAILED")
        if event.provider_request_id:
            key = (event.provider, event.provider_request_id)
            if key in self._seen:
                return False
            self._seen.add(key)
        self.events.append(event)
        return True


class SupabaseAiUsageTracker:
    def __init__(self, *, supabase_url: str, service_role_key: str, transport: "SupabaseOrganizationTransport | None" = None):
        self.transport = transport or SupabaseOrganizationTransport(supabase_url=supabase_url, service_role_key=service_role_key)

    def record(self, event: AiUsageEvent) -> bool:
        self.transport.upsert("ai_usage_events", [event.as_row()], conflict="provider,provider_request_id")
        return True


class SupabaseOrganizationTransport:
    def __init__(self, *, supabase_url: str, service_role_key: str):
        self.supabase_url = supabase_url
        self.service_role_key = service_role_key

    def get(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        return self.request_json("GET", table, params=params) or []

    def upsert(self, table: str, rows: list[dict[str, Any]], *, conflict: str) -> Any:
        return self.request_json(
            "POST",
            table,
            params={"on_conflict": conflict},
            payload=rows,
            headers={"Prefer": "resolution=ignore-duplicates,return=representation"},
        )

    def request_json(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        payload: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        query = f"?{parse.urlencode(params)}" if params else ""
        req = request.Request(
            f"{self.supabase_url.rstrip('/')}/rest/v1/{table}{query}",
            data=data,
            headers={
                "apikey": self.service_role_key,
                "Authorization": f"Bearer {self.service_role_key}",
                "Content-Type": "application/json",
                **(headers or {}),
            },
            method=method,
        )
        with request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
        return json.loads(body) if body else None


def organization_runtime_config_from_mapping(organization_id: str, row: dict[str, Any]) -> OrganizationRuntimeConfig:
    return OrganizationRuntimeConfig(
        organization_id=organization_id,
        assistant_name=_optional(row.get("assistant_name") or row.get("assistantName")),
        assistant_role=_optional(row.get("assistant_role") or row.get("assistantRole")),
        clinic_name=_optional(row.get("clinic_name") or row.get("clinicName") or row.get("name")),
        doctor_name=_optional(row.get("doctor_name") or row.get("doctorName")),
        sales_goal=str(row.get("sales_goal") or row.get("salesGoal") or OrganizationCommercialConfig.sales_goal),
        primary_conversion_action=str(row.get("primary_conversion_action") or row.get("primaryConversionAction") or OrganizationCommercialConfig.primary_conversion_action),
        max_discovery_depth=int(row.get("max_discovery_depth") or row.get("maxDiscoveryDepth") or OrganizationCommercialConfig.max_discovery_depth),
        cta_style=str(row.get("cta_style") or row.get("ctaStyle") or OrganizationCommercialConfig.cta_style),
        appointment_flow=str(row.get("appointment_flow") or row.get("appointmentFlow") or OrganizationCommercialConfig.appointment_flow),
        business_hours=_optional(row.get("business_hours") or row.get("businessHours")),
        locations=_normalize_locations(row.get("locations")),
        status=str(row.get("status") or "active"),
    )


def resolve_runtime_config(
    organization_id: str,
    *,
    repository: OrganizationConfigRepository,
    fallback_repository: OrganizationConfigRepository | None = None,
    logger=None,
) -> OrganizationRuntimeConfig:
    try:
        config = repository.get_by_organization_id(organization_id)
    except Exception as exc:
        _log(logger, "organization_config_load_failed", {"organizationId": organization_id, "errorType": type(exc).__name__})
        config = None
    if config and config.is_active():
        _log(logger, "organization_config_loaded", config.safe_dict())
        return config
    if config and not config.is_active():
        raise OrganizationConfigError("ORGANIZATION_INACTIVE")
    if fallback_repository:
        fallback = fallback_repository.get_by_organization_id(organization_id)
        if fallback:
            _log(logger, "organization_config_legacy_fallback", fallback.safe_dict())
            return fallback
    raise OrganizationConfigError("ORGANIZATION_CONFIG_NOT_FOUND")


def resolve_credential(
    organization_id: str,
    provider: str,
    *,
    credential_provider: OrganizationCredentialProvider,
    fallback_provider: OrganizationCredentialProvider | None = None,
    logger=None,
) -> OrganizationCredential:
    try:
        credential = credential_provider.get_credential(organization_id, provider)
    except Exception as exc:
        _log(
            logger,
            "organization_credential_load_failed",
            {"organizationId": organization_id, "provider": provider.upper(), "errorType": type(exc).__name__},
        )
        credential = None
    if credential:
        _log(logger, "organization_credential_resolved", credential.safe_dict())
        return credential
    if fallback_provider:
        fallback = fallback_provider.get_credential(organization_id, provider)
        if fallback:
            _log(logger, "organization_credential_legacy_fallback", fallback.safe_dict())
            return fallback
    raise OrganizationCredentialError("ORGANIZATION_CREDENTIAL_NOT_FOUND")


def usage_event_from_openai_response(
    response: dict[str, Any],
    *,
    organization_id: str,
    conversation_id: str,
    model: str,
) -> AiUsageEvent:
    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
    output_tokens = usage.get("output_tokens") or usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")
    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = int(input_tokens or 0) + int(output_tokens or 0)
    return AiUsageEvent(
        organization_id=organization_id,
        conversation_id=conversation_id,
        provider="OPENAI",
        model=model,
        provider_request_id=_optional(response.get("id")),
        input_tokens=_optional_int(input_tokens),
        output_tokens=_optional_int(output_tokens),
        total_tokens=_optional_int(total_tokens),
        estimated_cost_usd=None,
    )


def zapi_instance_organization_map_from_env(default_instance_id: str | None, default_organization_id: str) -> dict[str, str]:
    load_env_file()
    raw = environ.get("ZAPI_INSTANCE_ORGANIZATION_MAP_JSON")
    mapping = {str(key): str(value) for key, value in _loads_mapping(raw).items()}
    if not mapping and default_instance_id:
        mapping[str(default_instance_id)] = default_organization_id
    return mapping


def _loads_mapping(raw_json: str | None) -> dict[str, Any]:
    if not raw_json:
        return {}
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise OrganizationConfigError("INVALID_ORGANIZATION_JSON") from exc
    if not isinstance(data, dict):
        raise OrganizationConfigError("ORGANIZATION_JSON_MUST_BE_OBJECT")
    return data


def _normalize_locations(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(item.strip() for item in re.split(r"[|,]", value) if item.strip())
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _env_optional(key: str) -> str | None:
    value = environ.get(key)
    return value if value else None


def _log(logger, event: str, details: dict[str, Any]) -> None:
    if logger:
        logger(event, details)
