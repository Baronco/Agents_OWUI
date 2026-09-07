"""Contract test (spec 017, US1): POST /proxy/chat routes to the requested model.

Runs offline by monkeypatching the handler's collaborators so no live OWUI
HTTP/socket happens. The handler is a plain ``def`` dispatched to the thread
pool; the FastAPI ``TestClient`` drives the real dispatch path.
"""

from fastapi.testclient import TestClient

import api as proxy_api


def _patch_common(monkeypatch, sales_text="respuesta", tool_ids=None):
    # No real OWUI calls: stub the model-tools lookup and chat helpers.
    resolved = ["server:1", "chat_id"] if tool_ids is None else tool_ids
    monkeypatch.setattr(proxy_api.client, "get_model_tool_ids", lambda *a, **k: list(resolved))
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


def _post(
    client,
    message="hola",
    model_id="asistente-de-ventas",
    chat_id=None,
    token="tok",
    tools_key="tools-key",
    extra_headers=None,
    body=None,
):
    headers = {"Authorization": f"Bearer {token}"}
    if tools_key is not None:
        headers["X-Subagent-Tools-Key"] = tools_key
    if extra_headers:
        headers.update(extra_headers)
    if body is None:
        body = {"message": message, "model_id": model_id}
        if chat_id is not None:
            body["chat_id"] = chat_id
    return client.post("/proxy/chat", json=body, headers=headers)


def test_request_needs_message_model_id_and_tools_key(monkeypatch):
    """The body requires message + model_id; chat_id stays optional."""
    _patch_common(monkeypatch)
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola", model_id="asistente-de-ventas")

    assert resp.status_code == 200
    assert resp.json() == {"assistant_response": "respuesta", "subagent_chat_id": "c1"}


def test_create_path_returns_new_session_id(monkeypatch):
    """First call (no chat_id) returns the newly created session id."""
    _patch_common(monkeypatch)
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola", model_id="asistente-de-ventas")

    assert resp.status_code == 200
    assert resp.json()["subagent_chat_id"] == "c1"


def test_continue_path_echoes_session_id(monkeypatch):
    """Second call with a chat_id gets the same session id back."""
    _patch_common(monkeypatch)
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola", model_id="asistente-de-ventas", chat_id="c1")

    assert resp.status_code == 200
    assert resp.json()["subagent_chat_id"] == "c1"


def test_fallback_returns_new_session_id_not_stale(monkeypatch):
    """When continuation fails over to a new chat, the new id is returned."""
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        proxy_api,
        "continue_chat",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        proxy_api,
        "get_or_create_chat",
        lambda *a, **k: {"chat_id": "c-new", "assistant_response": "ok"},
    )
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola", model_id="asistente-de-ventas", chat_id="stale")

    assert resp.status_code == 200
    assert resp.json()["subagent_chat_id"] == "c-new"


def test_session_id_always_present_and_non_empty(monkeypatch):
    """Every successful response carries a non-empty subagent_chat_id."""
    _patch_common(monkeypatch, sales_text="")
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola", model_id="asistente-de-ventas")

    assert resp.status_code == 200
    assert resp.json()["subagent_chat_id"]


def test_missing_model_id_is_rejected(monkeypatch):
    """A missing model_id returns 400 with a clear message."""
    _patch_common(monkeypatch)
    client = TestClient(proxy_api.app)

    resp = _post(client, body={"message": "hola"})

    assert resp.status_code == 400
    assert "model_id" in resp.json()["detail"]


def test_empty_model_id_is_rejected(monkeypatch):
    """An empty model_id returns 400 with a clear message."""
    _patch_common(monkeypatch)
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola", model_id="   ")

    assert resp.status_code == 400
    assert "model_id" in resp.json()["detail"]


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

    resp = client.post(
        "/proxy/chat",
        json={"message": "hola", "model_id": "asistente-de-ventas"},
        headers={"X-Subagent-Tools-Key": "tools-key"},
    )

    assert resp.status_code == 401


def test_missing_tools_key_is_rejected(monkeypatch):
    """A request without X-Subagent-Tools-Key returns 401 with a clear message."""
    _patch_common(monkeypatch)
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola", tools_key=None)

    assert resp.status_code == 401
    assert "X-Subagent-Tools-Key" in resp.json()["detail"]


def test_unknown_model_id_is_rejected(monkeypatch):
    """An unknown model_id returns 400 naming the model."""
    from src.client.openwebui_client import UnknownModelError

    monkeypatch.setattr(
        proxy_api.client,
        "get_model_tool_ids",
        lambda *a, **k: (_ for _ in ()).throw(UnknownModelError("nope")),
    )
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola", model_id="nope")

    assert resp.status_code == 400
    assert "nope" in resp.json()["detail"]


def test_tools_lookup_failure_still_answers(monkeypatch):
    """A lookup timeout warns and proceeds with an empty tool list."""
    monkeypatch.setattr(proxy_api.client, "get_model_tool_ids", lambda *a, **k: [])
    monkeypatch.setattr(
        proxy_api,
        "get_or_create_chat",
        lambda *a, **k: {"chat_id": "c1", "assistant_response": "ok"},
    )
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola")

    assert resp.status_code == 200
    assert resp.json() == {"assistant_response": "ok", "subagent_chat_id": "c1"}


def test_completion_receives_resolved_tool_list(monkeypatch):
    """The resolved model tools reach the chat call (not the JSON file)."""
    seen = {}
    monkeypatch.setattr(
        proxy_api.client, "get_model_tool_ids", lambda *a, **k: ["server:1", "chat_id"]
    )

    def fake_create(*a, **k):
        seen["tenant_config"] = k.get("tenant_config")
        seen["model"] = a[1]
        return {"chat_id": "c1", "assistant_response": "ok"}

    monkeypatch.setattr(proxy_api, "get_or_create_chat", fake_create)
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola", model_id="asistente-de-ventas")

    assert resp.status_code == 200
    assert seen["model"] == "asistente-de-ventas"
    assert seen["tenant_config"]["tool_ids"] == ["server:1", "chat_id"]
    assert seen["tenant_config"]["title_generation"] is False


def test_chat_id_present_continues_chat(monkeypatch):
    """With a chat_id, the handler calls continue_chat (not get_or_create_chat)."""
    calls = []
    monkeypatch.setattr(proxy_api.client, "get_model_tool_ids", lambda *a, **k: [])

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
    monkeypatch.setattr(proxy_api.client, "get_model_tool_ids", lambda *a, **k: [])

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


def test_response_has_answer_and_session_id(monkeypatch):
    """The response contains assistant_response and subagent_chat_id only."""
    _patch_common(monkeypatch)
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola")

    data = resp.json()
    assert set(data.keys()) == {"assistant_response", "subagent_chat_id"}


def test_invalid_token_surfaces_auth_error(monkeypatch):
    """An OWUI auth failure during the call surfaces as a 401 to the caller."""
    from src.client.openwebui_client import AuthExpiredError

    monkeypatch.setattr(proxy_api.client, "get_model_tool_ids", lambda *a, **k: [])

    def fake_continue(*a, **k):
        raise AuthExpiredError("token expired")

    monkeypatch.setattr(proxy_api, "continue_chat", fake_continue)
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola", chat_id="chat-123")

    assert resp.status_code == 401


def test_bearer_header_reaches_owui_without_duplicate_prefix(monkeypatch):
    """The incoming 'Bearer <jwt>' header must reach OWUI as-is (no 'Bearer Bearer')."""
    seen = {}
    monkeypatch.setattr(proxy_api.client, "get_model_tool_ids", lambda *a, **k: [])

    def fake_create(*a, **k):
        seen["auth"] = k["owui_client"].session.headers.get("Authorization")
        return {"chat_id": "c1", "assistant_response": "ok", "output": [], "follow_ups": []}

    monkeypatch.setattr(proxy_api, "get_or_create_chat", fake_create)
    client = TestClient(proxy_api.app)

    resp = _post(client, message="hola", token="jwt-abc-123")

    assert resp.status_code == 200
    assert seen["auth"] == "Bearer jwt-abc-123"
