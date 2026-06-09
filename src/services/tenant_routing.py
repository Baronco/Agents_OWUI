"""Tenant routing service.
Maps tenant_id to an assistant configuration including model, tools, and system prompt.
"""
from typing import Optional, TypedDict


class TenantConfig(TypedDict, total=False):
    model: str
    tool_ids: list[str]
    system_prompt: str


TENANT_CONFIG_MAP: dict[str, TenantConfig] = {
    "a0000001-0000-4000-8000-000000000001": {
        "model": "asistente-de-ventas",
        "tool_ids": ["server:0"],
        "system_prompt": "Eres un asistente de ventas amable y servicial. Ayudas a los clientes a encontrar productos y responder preguntas sobre el catálogo.",
    },
}


def resolve_assistant(tenant_id: str) -> Optional[str]:
    """Return the assistant model name for the given tenant, or None if unknown."""
    config = TENANT_CONFIG_MAP.get(tenant_id)
    if config:
        return config.get("model")
    return None


def resolve_tenant_config(tenant_id: str) -> Optional[TenantConfig]:
    """Return the full TenantConfig for the given tenant, or None if unknown."""
    return TENANT_CONFIG_MAP.get(tenant_id)