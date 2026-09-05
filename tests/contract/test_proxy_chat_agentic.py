"""Contract test (spec 016, US1): POST /proxy/chat is an agentic chat call.

Runs offline by monkeypatching the handler's collaborators so no live OWUI
HTTP/socket happens. The handler is a plain ``def`` dispatched to the thread
pool; the FastAPI ``TestClient`` drives the real dispatch path.
"""

from fastapi.testclient import TestClient

import api as proxy_api


def _patch_common(monkeypatch, sales_text="respuesta"):
    # No real OWUI calls: stub the default-agent resolution and chat helpers.
    monkeypatch.setattr(
        proxy_api,
        "resolve_default_agent",
        lambda: {"model": "asistente-de-ventas", "tool_ids": [], "title_generation": False},
    )
    monkeypatch.setattr(
        proxy_api,
        "get_or_create_chat",
        lambda *a, **k: {
            "chat_id": "c1",
            "assistant_response": sales_text,
            "output": [],
            "follow_ups": [],
        },
    )
    monkeypatch.setattr(
        proxy_api,
        "continue_chat",
        lambda *a, **k: {
            "chat_id": "c1",
            "assistant_response": sales_text,
            "output": [],
            "follow_ups": [],
        },
    )


def _post(client, message="hola", chat_id=None, token="tok"):
    headers = {"Authorization": f"Bearer {token}"}
    body = {"message": message}
    if chat_id is not None:
        body["chat_id"] = chat_id
    return client.post("/proxy/chat", json=body, headers=headers)


def test_request_needs_only_message_and_optional_chat_id(monkeypatch):
    """The body requires message; chat_id is optional (absent => new chat)."""
    _patch_common(monkeypatch)
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola")

    assert resp.status_code == 200
    assert resp.json() == {"assistant_response": "respuesta"}


def test_empty_message_is_rejected(monkeypatch):
    """An empty message returns 400."""
    _patch_common(monkeypatch)
    client = TestClient(proxy_api.app)

    resp = _post(client, message="   ")

    assert resp.status_code == 400


def test_missing_bearer_token_is_rejected(monkeypatch):
    """A request without an Authorization header returns 401."""
    _patch_common(monkeypatch)
    client = TestClient(proxy_api.app)

    resp = client.post("/proxy/chat", json={"message": "hola"})

    assert resp.status_code == 401


def test_no_default_agent_is_rejected(monkeypatch):
    """If no default agent is configured the request fails clearly (500)."""
    monkeypatch.setattr(proxy_api, "resolve_default_agent", lambda: None)
    monkeypatch.setattr(
        proxy_api,
        "get_or_create_chat",
        lambda *a, **k: {"chat_id": "c1", "assistant_response": "x"},
    )
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola")

    assert resp.status_code == 500


def test_chat_id_present_continues_chat(monkeypatch):
    """With a chat_id, the handler calls continue_chat (not get_or_create_chat)."""
    calls = []
    monkeypatch.setattr(
        proxy_api,
        "resolve_default_agent",
        lambda: {"model": "m", "tool_ids": [], "title_generation": False},
    )

    def fake_continue(*a, **k):
        calls.append(("continue", a[0]))
        return {"chat_id": a[0], "assistant_response": "ok", "output": [], "follow_ups": []}

    def fake_create(*a, **k):
        calls.append(("create", None))
        return {"chat_id": "c1", "assistant_response": "ok", "output": [], "follow_ups": []}

    monkeypatch.setattr(proxy_api, "continue_chat", fake_continue)
    monkeypatch.setattr(proxy_api, "get_or_create_chat", fake_create)
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola", chat_id="chat-123")

    assert resp.status_code == 200
    assert any(c[0] == "continue" and c[1] == "chat-123" for c in calls)
    assert not any(c[0] == "create" for c in calls)


def test_chat_id_absent_creates_chat(monkeypatch):
    """Without a chat_id, the handler calls get_or_create_chat."""
    calls = []
    monkeypatch.setattr(
        proxy_api,
        "resolve_default_agent",
        lambda: {"model": "m", "tool_ids": [], "title_generation": False},
    )

    def fake_continue(*a, **k):
        calls.append(("continue", a[0]))
        return None

    def fake_create(*a, **k):
        calls.append(("create", None))
        return {"chat_id": "c1", "assistant_response": "ok", "output": [], "follow_ups": []}

    monkeypatch.setattr(proxy_api, "continue_chat", fake_continue)
    monkeypatch.setattr(proxy_api, "get_or_create_chat", fake_create)
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola")

    assert resp.status_code == 200
    assert not any(c[0] == "continue" for c in calls)
    assert any(c[0] == "create" for c in calls)


def test_response_only_has_assistant_response(monkeypatch):
    """The response contains only assistant_response (no user_id/tenant_id/chat_id)."""
    _patch_common(monkeypatch)
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola")

    data = resp.json()
    assert set(data.keys()) == {"assistant_response"}


def test_bearer_header_reaches_owui_without_duplicate_prefix(monkeypatch):
    """The incoming 'Bearer <jwt>' header must reach OWUI as-is (no 'Bearer Bearer').

    Regression: _get_bearer_token returns the full header value, and with_token
    adds the scheme itself — the handler must strip it once first.
    """
    seen = {}
    monkeypatch.setattr(
        proxy_api,
        "resolve_default_agent",
        lambda: {"model": "m", "tool_ids": [], "title_generation": False},
    )

    def fake_create(*a, **k):
        seen["auth"] = k["owui_client"].session.headers.get("Authorization")
        return {"chat_id": "c1", "assistant_response": "ok", "output": [], "follow_ups": []}

    monkeypatch.setattr(proxy_api, "get_or_create_chat", fake_create)
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola", token="jwt-abc-123")

    assert resp.status_code == 200
    assert seen["auth"] == "Bearer jwt-abc-123"


def test_bare_token_without_scheme_still_works(monkeypatch):
    """A header value without the 'Bearer ' scheme is forwarded with one prefix."""
    seen = {}
    monkeypatch.setattr(
        proxy_api,
        "resolve_default_agent",
        lambda: {"model": "m", "tool_ids": [], "title_generation": False},
    )

    def fake_create(*a, **k):
        seen["auth"] = k["owui_client"].session.headers.get("Authorization")
        return {"chat_id": "c1", "assistant_response": "ok", "output": [], "follow_ups": []}

    monkeypatch.setattr(proxy_api, "get_or_create_chat", fake_create)
    client = TestClient(proxy_api.app)

    resp = client.post(
        "/proxy/chat",
        json={"message": "hola"},
        headers={"Authorization": "tok-sin-prefijo"},
    )

    assert resp.status_code == 200
    assert seen["auth"] == "Bearer tok-sin-prefijo"


def test_invalid_token_surfaces_auth_error(monkeypatch):
    """An OWUI auth failure during the call surfaces as a 401 to the caller."""
    from src.client.openwebui_client import AuthExpiredError

    monkeypatch.setattr(
        proxy_api,
        "resolve_default_agent",
        lambda: {"model": "m", "tool_ids": [], "title_generation": False},
    )

    def fake_continue(*a, **k):
        raise AuthExpiredError("token expired")

    monkeypatch.setattr(proxy_api, "continue_chat", fake_continue)
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola", chat_id="chat-123")

    assert resp.status_code == 401
