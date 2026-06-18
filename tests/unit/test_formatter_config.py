"""Unit tests for the global formatter config (spec 007, US2, FR-005; spec 009, US2).

The formatter is global: same config for any tenant, independent of the
tenant list. Since spec 009, both come from `config/tenants.json` (loaded
via `tenant_config_loader`) instead of Python constants — these tests pin
the same literal expected values as before the migration.
"""
from src.services.tenant_routing import resolve_formatter_config

_EXPECTED_MODEL = "asistente-de-ventas-formateo-respuestas"
_EXPECTED_TOOL_IDS = ["format_reponse"]


def test_returns_constant_config():
    cfg = resolve_formatter_config()
    assert cfg["model"] == _EXPECTED_MODEL
    assert cfg["tool_ids"] == _EXPECTED_TOOL_IDS


def test_title_generation_disabled():
    # Spec 008: the formatter creates a new chat on every turn, so leaving
    # title_generation on its default (True) would fire an extra LLM call
    # per message instead of once per conversation.
    assert resolve_formatter_config()["title_generation"] is False


def test_formatter_model_is_the_agreed_assistant():
    cfg = resolve_formatter_config()
    assert cfg["model"] == _EXPECTED_MODEL
    # Must reference the OWUI tool container id (non-empty) so OWUI attaches it.
    assert cfg["tool_ids"] and all(isinstance(t, str) and t for t in cfg["tool_ids"])


def test_config_is_tenant_agnostic():
    # No tenant_id argument; calling twice yields equivalent config.
    assert resolve_formatter_config() == resolve_formatter_config()
