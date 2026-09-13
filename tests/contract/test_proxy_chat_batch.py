"""Contract tests for POST /proxy/chat/batch (spec 020, US1: parallel batch).

Runs offline: the batch runner's chat helpers and the model-tools lookup are
monkeypatched so no live OWUI HTTP/socket happens.
"""

from fastapi.testclient import TestClient

import api as proxy_api
import src.services.batch as batch


def _patch_batch(monkeypatch):
    monkeypatch.setattr(proxy_api.client, "get_model_tool_ids", lambda *a, **k: [])

    def fake_create(user_id, assistant_id, message, **kwargs):
        return {
            "chat_id": f"c-{assistant_id}",
            "assistant_response": f"resp:{message}",
            "output": [],
            "follow_ups": [],
        }

    monkeypatch.setattr(batch, "get_or_create_chat", fake_create)
    monkeypatch.setattr(batch, "continue_chat", lambda *a, **k: None)


def _post(client, tasks, token="tok", tools_key="tools-key", extra_headers=None):
    headers = {"Authorization": f"Bearer {token}"}
    if tools_key is not None:
        headers["X-Subagent-Tools-Key"] = tools_key
    if extra_headers:
        headers.update(extra_headers)
    return client.post("/proxy/chat/batch", json={"tasks": tasks}, headers=headers)


def test_batch_returns_one_ok_result_per_task(monkeypatch):
    """A batch of 3 tasks returns 3 ok results in request order."""
    _patch_batch(monkeypatch)
    client = TestClient(proxy_api.app)

    resp = _post(
        client,
        [
            {"message": "a", "model_id": "m0"},
            {"message": "b", "model_id": "m1"},
            {"message": "c", "model_id": "m2"},
        ],
    )

    assert resp.status_code == 200
    data = resp.json()
    assert [r["index"] for r in data["results"]] == [0, 1, 2]
    assert all(r["status"] == "ok" for r in data["results"])
    assert [r["model_id"] for r in data["results"]] == ["m0", "m1", "m2"]
    assert all(r["assistant_response"] for r in data["results"])
    assert all(r["subagent_chat_id"] for r in data["results"])
    assert data["truncated_count"] == 0
    assert data["info"] is None
    assert data["max_subagents"] == proxy_api.MAX_BATCH_SUBAGENTS


def test_empty_tasks_is_rejected(monkeypatch):
    """An empty task list returns 400."""
    _patch_batch(monkeypatch)
    client = TestClient(proxy_api.app)

    resp = _post(client, [])

    assert resp.status_code == 400


def test_missing_bearer_is_rejected(monkeypatch):
    """A batch without an Authorization header returns 401."""
    _patch_batch(monkeypatch)
    client = TestClient(proxy_api.app)

    resp = client.post(
        "/proxy/chat/batch",
        json={"tasks": [{"message": "a", "model_id": "m0"}]},
        headers={"X-Subagent-Tools-Key": "k"},
    )

    assert resp.status_code == 401


def test_missing_tools_key_is_rejected(monkeypatch):
    """A batch without X-Subagent-Tools-Key returns 401."""
    _patch_batch(monkeypatch)
    client = TestClient(proxy_api.app)

    resp = _post(client, [{"message": "a", "model_id": "m0"}], tools_key=None)

    assert resp.status_code == 401
    assert "X-Subagent-Tools-Key" in resp.json()["detail"]


def test_per_task_error_is_isolated(monkeypatch):
    """One failing task reports an error without losing the other results."""
    from src.client.openwebui_client import UnknownModelError

    def lookup(model_id, token, **kwargs):
        if model_id == "bad":
            raise UnknownModelError("nope")
        return []

    monkeypatch.setattr(proxy_api.client, "get_model_tool_ids", lookup)

    def fake_create(user_id, assistant_id, message, **kwargs):
        return {"chat_id": f"c-{assistant_id}", "assistant_response": "ok"}

    monkeypatch.setattr(batch, "get_or_create_chat", fake_create)
    monkeypatch.setattr(batch, "continue_chat", lambda *a, **k: None)
    client = TestClient(proxy_api.app)

    resp = _post(
        client,
        [
            {"message": "a", "model_id": "good0"},
            {"message": "b", "model_id": "bad"},
            {"message": "c", "model_id": "good1"},
        ],
    )

    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results[0]["status"] == "ok"
    assert results[1]["status"] == "error"
    assert results[1]["error"]
    assert results[2]["status"] == "ok"


def test_blank_model_id_fails_that_task_only(monkeypatch):
    """A task with a blank model_id fails on its own while others succeed."""
    _patch_batch(monkeypatch)
    client = TestClient(proxy_api.app)

    resp = _post(
        client,
        [
            {"message": "a", "model_id": "good"},
            {"message": "b", "model_id": "   "},
        ],
    )

    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results[0]["status"] == "ok"
    assert results[1]["status"] == "error"


def test_task_with_chat_id_continues_chat(monkeypatch):
    """A task carrying a chat_id continues that session (no new chat created)."""
    monkeypatch.setattr(proxy_api.client, "get_model_tool_ids", lambda *a, **k: [])
    calls = []

    def fake_continue(chat_id, message, model_id, **kwargs):
        calls.append(("continue", chat_id))
        return {"chat_id": chat_id, "assistant_response": "ok"}

    def fake_create(user_id, assistant_id, message, **kwargs):
        calls.append(("create", None))
        return {"chat_id": "c-new", "assistant_response": "ok"}

    monkeypatch.setattr(batch, "continue_chat", fake_continue)
    monkeypatch.setattr(batch, "get_or_create_chat", fake_create)
    client = TestClient(proxy_api.app)

    resp = _post(client, [{"message": "a", "model_id": "m", "chat_id": "chat-1"}])

    assert resp.status_code == 200
    assert ("continue", "chat-1") in calls
    assert not any(c[0] == "create" for c in calls)


def test_task_without_chat_id_creates_chat(monkeypatch):
    """A task without a chat_id creates a new sub-agent chat."""
    monkeypatch.setattr(proxy_api.client, "get_model_tool_ids", lambda *a, **k: [])
    calls = []

    def fake_continue(chat_id, message, model_id, **kwargs):
        calls.append(("continue", chat_id))
        return None

    def fake_create(user_id, assistant_id, message, **kwargs):
        calls.append(("create", None))
        return {"chat_id": "c-new", "assistant_response": "ok"}

    monkeypatch.setattr(batch, "continue_chat", fake_continue)
    monkeypatch.setattr(batch, "get_or_create_chat", fake_create)
    client = TestClient(proxy_api.app)

    resp = _post(client, [{"message": "a", "model_id": "m"}])

    assert resp.status_code == 200
    assert any(c[0] == "create" for c in calls)
    assert not any(c[0] == "continue" for c in calls)


def test_bearer_reaches_owui_without_duplicate_prefix(monkeypatch):
    """The incoming 'Bearer <jwt>' header must reach OWUI as-is (no 'Bearer Bearer')."""
    seen = {}
    monkeypatch.setattr(proxy_api.client, "get_model_tool_ids", lambda *a, **k: [])

    def fake_create(user_id, assistant_id, message, **kwargs):
        seen["auth"] = kwargs["owui_client"].session.headers.get("Authorization")
        return {"chat_id": "c1", "assistant_response": "ok"}

    monkeypatch.setattr(batch, "get_or_create_chat", fake_create)
    monkeypatch.setattr(batch, "continue_chat", lambda *a, **k: None)
    client = TestClient(proxy_api.app)

    resp = _post(client, [{"message": "a", "model_id": "m"}], token="jwt-abc-123")

    assert resp.status_code == 200
    assert seen["auth"] == "Bearer jwt-abc-123"


def test_resolved_tool_ids_reach_chat_call(monkeypatch):
    """The resolved model tools reach the chat call as tenant_config.tool_ids."""
    seen = {}
    monkeypatch.setattr(
        proxy_api.client, "get_model_tool_ids", lambda *a, **k: ["server:1", "chat_id"]
    )

    def fake_create(user_id, assistant_id, message, **kwargs):
        seen["cfg"] = kwargs["tenant_config"]
        seen["model"] = assistant_id
        return {"chat_id": "c1", "assistant_response": "ok"}

    monkeypatch.setattr(batch, "get_or_create_chat", fake_create)
    monkeypatch.setattr(batch, "continue_chat", lambda *a, **k: None)
    client = TestClient(proxy_api.app)

    resp = _post(client, [{"message": "a", "model_id": "asistente-de-ventas"}])

    assert resp.status_code == 200
    assert seen["model"] == "asistente-de-ventas"
    assert seen["cfg"]["tool_ids"] == ["server:1", "chat_id"]
    assert seen["cfg"]["title_generation"] is False
