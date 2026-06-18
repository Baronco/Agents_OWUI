"""Unit tests for the global formatter config (spec 007, US2, FR-005).

The formatter is global: same config for any tenant, independent of
TENANT_CONFIG_MAP.
"""
from src.services.tenant_routing import (
    FORMATTER_MODEL,
    FORMATTER_TOOL_IDS,
    resolve_formatter_config,
)


def test_returns_constant_config():
    cfg = resolve_formatter_config()
    assert cfg["model"] == FORMATTER_MODEL
    assert cfg["tool_ids"] == FORMATTER_TOOL_IDS


def test_formatter_model_is_the_agreed_assistant():
    assert FORMATTER_MODEL == "asistente-de-ventas-formateo-respuestas"
    # Must reference the OWUI tool container id (non-empty) so OWUI attaches it.
    assert FORMATTER_TOOL_IDS and all(isinstance(t, str) and t for t in FORMATTER_TOOL_IDS)


def test_config_is_tenant_agnostic():
    # No tenant_id argument; calling twice yields equivalent config.
    assert resolve_formatter_config() == resolve_formatter_config()
