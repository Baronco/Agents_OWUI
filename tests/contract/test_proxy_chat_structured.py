"""Contract test (spec 007, US1): assistant_response is a structured object.

Runs offline by monkeypatching the proxy's collaborators and calling the async
endpoint directly (no live OWUI, no HTTP client needed).
"""
import asyncio

import api as proxy_api

_FIELDS = ("messageType", "body", "escalate", "buttons", "listSections", "listButtonText", "quote")


def _patch_common(monkeypatch, structured):
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
        lambda *a, **k: {"chat_id": "c1", "assistant_response": "hola", "output": [], "follow_ups": []},
    )
    monkeypatch.setattr(proxy_api, "run_formatter", lambda *a, **k: structured)


def test_assistant_response_is_structured_object(monkeypatch):
    structured = {
        "messageType": "text", "body": "hola", "escalate": False,
        "buttons": "", "listSections": "", "listButtonText": "", "quote": "",
    }
    _patch_common(monkeypatch, structured)

    req = proxy_api.ChatRequest(
        tenant_id="a0000001-0000-4000-8000-000000000001",
        client_phone="+573001234567",
        chat_id="x",
        message="hola",
    )
    resp = asyncio.run(proxy_api.proxy_chat(req))

    assert isinstance(resp.assistant_response, dict)
    for f in _FIELDS:
        assert f in resp.assistant_response


def test_fallback_to_text_when_formatter_returns_none(monkeypatch):
    _patch_common(monkeypatch, None)  # formatter fails -> None

    req = proxy_api.ChatRequest(
        tenant_id="a0000001-0000-4000-8000-000000000001",
        client_phone="+573001234567",
        chat_id="x",
        message="hola",
    )
    resp = asyncio.run(proxy_api.proxy_chat(req))

    assert isinstance(resp.assistant_response, dict)
    assert resp.assistant_response["messageType"] == "text"
    assert resp.assistant_response["body"] == "hola"
    for f in _FIELDS:
        assert f in resp.assistant_response
