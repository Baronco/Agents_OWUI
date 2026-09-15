"""Contract tests for batch progress event emission (spec 020, US3)."""

from fastapi.testclient import TestClient

import api as proxy_api
import src.services.batch as batch


def _patch(monkeypatch):
    monkeypatch.setattr(proxy_api.client, "get_model_tool_ids", lambda *a, **k: [])
    monkeypatch.setattr(proxy_api, "PROXY_AUTO_ARCHIVE", False)
    monkeypatch.setattr(proxy_api, "MAX_SUBAGENT_CALLS_PER_MESSAGE", 100)
    proxy_api._LOOP_COUNTS.clear()

    def fake_create(user_id, assistant_id, message, **kwargs):
        return {"chat_id": f"c-{assistant_id}", "assistant_response": "ok"}

    monkeypatch.setattr(batch, "get_or_create_chat", fake_create)
    monkeypatch.setattr(batch, "continue_chat", lambda *a, **k: None)


def _post(client, headers_extra=None):
    headers = {"Authorization": "Bearer tok", "X-Subagent-Tools-Key": "k"}
    if headers_extra:
        headers.update(headers_extra)
    tasks = [
        {"message": "a", "model_id": "m0"},
        {"message": "b", "model_id": "m1"},
    ]
    return client.post("/proxy/chat/batch", json={"tasks": tasks}, headers=headers)


def test_emits_start_and_completion_per_task(monkeypatch):
    """With forwarded headers, each task emits a start and a completion event."""
    _patch(monkeypatch)
    calls = []
    monkeypatch.setattr(proxy_api, "emit_status", lambda *a, **k: calls.append((a, k)))
    client = TestClient(proxy_api.app)

    resp = _post(
        client,
        headers_extra={
            "X-OpenWebUI-Chat-Id": "parent-chat",
            "X-OpenWebUI-Message-Id": "parent-msg",
        },
    )

    assert resp.status_code == 200
    # 2 tasks: batch(2) + start(2) + finish(2) + progress(2) = 8
    assert len(calls) == 8
    chat_ids = {args[2] for args, _ in calls}
    message_ids = {args[3] for args, _ in calls}
    assert chat_ids == {"parent-chat"}
    assert message_ids == {"parent-msg"}
    done_flags = [args[4]["done"] for args, _ in calls]
    assert sorted(done_flags) == [False, False, False, False, False, False, True, True]
    descriptions = [args[4]["description"] for args, _ in calls]
    assert any("Launching 2" in d for d in descriptions)
    assert any("completed in" in d for d in descriptions)
    assert any("task progress" in d for d in descriptions)


def test_no_headers_means_no_emission(monkeypatch):
    """Without forwarded headers, no status events are emitted."""
    _patch(monkeypatch)
    calls = []
    monkeypatch.setattr(proxy_api, "emit_status", lambda *a, **k: calls.append((a, k)))
    client = TestClient(proxy_api.app)

    resp = _post(client)

    assert resp.status_code == 200
    assert calls == []


def test_intermediate_socket_events_become_parent_statuses(monkeypatch):
    """Tool-use and status socket events are forwarded with the sub-agent name."""
    monkeypatch.setattr(proxy_api, "PROXY_AUTO_ARCHIVE", False)
    monkeypatch.setattr(proxy_api, "MAX_SUBAGENT_CALLS_PER_MESSAGE", 100)
    proxy_api._LOOP_COUNTS.clear()
    monkeypatch.setattr(proxy_api.client, "get_model_tool_ids", lambda *a, **k: [])

    def fake_create(user_id, assistant_id, message, **kwargs):
        on_progress = kwargs.get("on_progress")
        if on_progress:
            on_progress({"type": "tool", "name": "web_search"})
            on_progress({"type": "status", "data": {"description": "Searching the web"}})
            on_progress({"type": "status", "data": {"description": "secret", "hidden": True}})
        return {"chat_id": f"c-{assistant_id}", "assistant_response": "ok"}

    monkeypatch.setattr(batch, "get_or_create_chat", fake_create)
    monkeypatch.setattr(batch, "continue_chat", lambda *a, **k: None)

    calls = []
    monkeypatch.setattr(proxy_api, "emit_status", lambda *a, **k: calls.append((a, k)))
    client = TestClient(proxy_api.app)

    resp = _post(
        client,
        headers_extra={
            "X-OpenWebUI-Chat-Id": "parent-chat",
            "X-OpenWebUI-Message-Id": "parent-msg",
        },
    )

    assert resp.status_code == 200
    descriptions = [args[4]["description"] for args, _ in calls]
    assert any("is using web_search" in d for d in descriptions)
    assert any("Searching the web" in d for d in descriptions)
    assert not any("secret" in d for d in descriptions)
