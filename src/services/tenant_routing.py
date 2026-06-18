"""Tenant routing service.
Maps tenant_id to an assistant configuration including model, tools, and system prompt.
"""
from typing import Optional, TypedDict


class TenantConfig(TypedDict, total=False):
    model: str
    tool_ids: list[str]
    system_prompt: str
    title_generation: bool


TENANT_CONFIG_MAP: dict[str, TenantConfig] = {
    "a0000001-0000-4000-8000-000000000001": {
        "model": "asistente-de-ventas",
        "tool_ids": ["server:0"],
        "system_prompt": "Eres un asistente de ventas amable y servicial. Ayudas a los clientes a encontrar productos y responder preguntas sobre el catálogo.",
        # Disabled to save the extra LLM call on each new conversation's first
        # message. Trade-off: OWUI's chat list shows the raw first user
        # message as the title instead of an AI-generated one (see spec 008
        # research.md R5 — same fallback that affects the formatter's chat).
        "title_generation": False,
    },
}


# Global formatter agent — same for every tenant. Its job (convert the sales
# agent's text into the WhatsApp structured object via the `format_response`
# tool) is tenant-agnostic, so it lives outside TENANT_CONFIG_MAP and is never
# configured per tenant. See specs/007-structured-response-formatter.
FORMATTER_MODEL = "asistente-de-ventas-formateo-respuestas"
# NOTE: this is the OWUI *tool id* (the container), not the function name. The
# tool was created in OWUI with the id "format_reponse" (typo, missing the "s").
# It MUST match exactly or OWUI silently drops the tool and the model emits text.
# The function inside is still named `format_response` (what extract_tool_result
# matches on). If you recreate the tool with a clean id, update this constant.
FORMATTER_TOOL_IDS = ["format_reponse"]


def resolve_assistant(tenant_id: str) -> Optional[str]:
    """Return the assistant model name for the given tenant, or None if unknown."""
    config = TENANT_CONFIG_MAP.get(tenant_id)
    if config:
        return config.get("model")
    return None


def resolve_tenant_config(tenant_id: str) -> Optional[TenantConfig]:
    """Return the full TenantConfig for the given tenant, or None if unknown."""
    return TENANT_CONFIG_MAP.get(tenant_id)


def resolve_formatter_config() -> TenantConfig:
    """Return the global formatter config — identical for all tenants.

    Independent of TENANT_CONFIG_MAP and of any tenant_id.
    """
    # Disable OWUI's title generation: the formatter creates a brand-new chat
    # on every turn (it's stateless), so unlike the sales agent — where this
    # only fires once per conversation — it would otherwise fire an extra LLM
    # call on every single message. The title is never read by anyone.
    return {"model": FORMATTER_MODEL, "tool_ids": FORMATTER_TOOL_IDS, "title_generation": False}