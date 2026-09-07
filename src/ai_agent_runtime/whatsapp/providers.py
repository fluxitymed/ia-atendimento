from __future__ import annotations

from typing import Literal

from .evolution import EvolutionTransport, EvolutionWhatsAppConfig, EvolutionWhatsAppProvider
from .meta import MetaGraphTransport, MetaWhatsAppCloudProvider, MetaWhatsAppConfig
from .zapi import ZApiTransport, ZApiWhatsAppConfig, ZApiWhatsAppProvider


ProviderName = Literal["evolution", "meta", "meta_cloud", "zapi"]


def build_whatsapp_provider(
    provider: ProviderName | None = None,
    *,
    evolution_config: EvolutionWhatsAppConfig | None = None,
    meta_config: MetaWhatsAppConfig | None = None,
    zapi_config: ZApiWhatsAppConfig | None = None,
    evolution_transport: EvolutionTransport | None = None,
    meta_transport: MetaGraphTransport | None = None,
    zapi_transport: ZApiTransport | None = None,
):
    selected = (
        provider
        or (zapi_config.provider if zapi_config else None)
        or (evolution_config.provider if evolution_config else None)
        or "evolution"
    ).lower()
    if selected == "evolution":
        config = evolution_config or EvolutionWhatsAppConfig.from_env()
        return EvolutionWhatsAppProvider(config=config, transport=evolution_transport)
    if selected in {"meta", "meta_cloud"}:
        config = meta_config or MetaWhatsAppConfig.from_env()
        return MetaWhatsAppCloudProvider(config=config, transport=meta_transport)
    if selected == "zapi":
        config = zapi_config or ZApiWhatsAppConfig.from_env()
        return ZApiWhatsAppProvider(config=config, transport=zapi_transport)
    raise ValueError("UNKNOWN_WHATSAPP_PROVIDER")
