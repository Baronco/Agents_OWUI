"""Unit tests for OPENWEBUI_BASE_URL actually reaching OpenWebUIClient (spec 009, US1).

Before this fix, ``api.py`` constructed ``OpenWebUIClient()`` with no
argument, so ``src.config.OPENWEBUI_BASE_URL`` (which already read the env
var) had zero effect — the class's own hardcoded default was always used.
"""
import importlib

import src.config as config_module


def _reload_with_env(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("OPENWEBUI_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("OPENWEBUI_BASE_URL", value)
    importlib.reload(config_module)
    import api as api_module
    importlib.reload(api_module)
    return api_module


def test_custom_base_url_env_var_is_used(monkeypatch):
    api_module = _reload_with_env(monkeypatch, "http://custom-owui:9000")
    try:
        assert api_module.client.base_url == "http://custom-owui:9000"
    finally:
        _reload_with_env(monkeypatch, None)


def test_default_base_url_when_env_var_unset(monkeypatch):
    api_module = _reload_with_env(monkeypatch, None)
    assert api_module.client.base_url == "http://localhost:3000"
