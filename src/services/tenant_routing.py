"""Tenant routing service.
Maps tenant_id to an assistant configuration including model, tools, and system prompt.

Since spec 009, the tenant list comes from ``config/tenants.json`` (see
``tenant_config_loader``) instead of living as Python constants. By explicit
choice, the file is re-read and re-validated on every call below (not
cached) — adding a tenant takes effect on the very next request, with no
process restart. The trade-off: each call pays the cost of reading + parsing
the file (small for a config file this size), and a file broken *after*
startup surfaces as a failure on the next request that needs it, rather than
at a fixed "reload" moment. See specs/009-config-externalization for the full
discussion.
"""
from typing import Optional, TypedDict

from src.services.tenant_config_loader import load_config


class TenantConfig(TypedDict, total=False):
    model: str
    tool_ids: list[str]
    title_generation: bool


# Fail fast if the file is already broken at process startup (spec 009,
# US3). This result is intentionally NOT cached — every resolve_*() call
# below re-reads the file fresh; this call is purely a startup health check.
load_config()


def resolve_assistant(tenant_id: str) -> Optional[str]:
    """Return the assistant model name for the given tenant, or None if unknown."""
    config = load_config()["tenants"].get(tenant_id)
    if config:
        return config.get("model")
    return None


def resolve_tenant_config(tenant_id: str) -> Optional[TenantConfig]:
    """Return the full TenantConfig for the given tenant, or None if unknown."""
    return load_config()["tenants"].get(tenant_id)
