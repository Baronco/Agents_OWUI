"""Contract test (spec 014, US1): assistant_response is the sales assistant's plain text.

Runs offline by monkeypatching the proxy's collaborators and calling the
endpoint function directly (no live OWUI, no HTTP client needed). The handler
is a plain ``def`` (spec 010, US1), so it's called synchronously.
"""
import api as proxy_api


def _patch_common(monkeypatch, sales_text):
    monkeypatch.setattr(proxy_api, "resolve_assistant", lambda t: "asistente-de-ventas")
    monkeypatch.setattr(proxy_api, "resolve_tenant_config", lambda t: {})
    monkeypatch.setattr(
        proxy_api, "provision_user",
        lambda *a, **k: {"user_id": "u1", "email": "e@proxy.local", "token": "tok", "is_new_session": True},
    )
    monkeypatch.setattr(proxy_api, "get_owui_chat_id", lambda *a, **k: None)
    monkeypatch.setattr(proxy_api, "store_chat_mapping", lambda *a, **k: None)
    monkeypatch.setattr(
        proxy_api, "get_or_create_chat",
        lambda *a, **k: {"chat_id": "c1", "assistant_response": sales_text, "output": [], "follow_ups": []},
    )


def _request():
    return proxy_api.ChatRequest(
        tenant_id="a0000001-0000-4000-8000-000000000001",
        client_phone="+573001234567",
        chat_id="x",
        message="hola",
    )


def test_assistant_response_is_plain_text(monkeypatch):
    _patch_common(monkeypatch, "Tenemos tres planes disponibles.")

    resp = proxy_api.proxy_chat(_request())

    assert isinstance(resp.assistant_response, str)
    assert resp.assistant_response == "Tenemos tres planes disponibles."


def test_empty_answer_passes_through(monkeypatch):
    _patch_common(monkeypatch, "")

    resp = proxy_api.proxy_chat(_request())

    assert resp.assistant_response == ""


def test_endpoint_has_no_formatter_seam():
    # Spec 014: the formatter assistant pass is removed entirely — the API
    # module must not reference any formatter machinery.
    assert not hasattr(proxy_api, "run_formatter")
    assert not hasattr(proxy_api, "text_fallback")
