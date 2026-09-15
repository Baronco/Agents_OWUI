"""Contract test for loop guard: max calls per parent message_id (spec 020)."""

from fastapi.testclient import TestClient

import api as proxy_api
import src.services.batch as batch


def _patch(monkeypatch):
    monkeypatch.setattr(proxy_api.client, "get_model_tool_ids", lambda *a, **k: [])
    monkeypatch.setattr(proxy_api, "emit_status", lambda *a, **k: True)

    def fake_create(user_id, assistant_id, message, **kwargs):
        return {"chat_id": f"c-{assistant_id}", "assistant_response": "ok"}

    monkeypatch.setattr(batch, "get_or_create_chat", fake_create)
    monkeypatch.setattr(batch, "continue_chat", lambda *a, **k: None)


def _post(client, msg_id="loop-msg-1"):
    headers = {
        "Authorization": "Bearer tok",
        "X-Subagent-Tools-Key": "k",
        "X-OpenWebUI-Chat-Id": "parent-chat",
        "X-OpenWebUI-Message-Id": msg_id,
    }
    return client.post(
        "/proxy/chat/batch",
        json={"tasks": [{"message": "a", "model_id": "m"}]},
        headers=headers,
    )


def test_loop_guard_blocks_after_limit(monkeypatch):
    """After 5 calls with same message_id, the 6th is blocked with guard info."""
    monkeypatch.setattr(proxy_api, "PROXY_AUTO_ARCHIVE", False)
    monkeypatch.setattr(proxy_api, "MAX_SUBAGENT_CALLS_PER_MESSAGE", 5)
    proxy_api._LOOP_COUNTS.clear()
    _patch(monkeypatch)
    client = TestClient(proxy_api.app)

    for i in range(5):
        resp = _post(client, msg_id="loop-guard-test")
        assert resp.status_code == 200
        assert resp.json()["info"] is None or "Loop guard" not in (resp.json()["info"] or "")

    # 6th should be blocked
    resp = _post(client, msg_id="loop-guard-test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"] == []
    assert data["info"] is not None
    assert "Loop guard" in data["info"]
    assert "5" in data["info"]


def test_different_message_ids_have_independent_counters(monkeypatch):
    """Different message_ids do not share the loop counter."""
    monkeypatch.setattr(proxy_api, "PROXY_AUTO_ARCHIVE", False)
    monkeypatch.setattr(proxy_api, "MAX_SUBAGENT_CALLS_PER_MESSAGE", 2)
    proxy_api._LOOP_COUNTS.clear()
    _patch(monkeypatch)
    client = TestClient(proxy_api.app)

    for _ in range(2):
        assert _post(client, msg_id="msg-a").status_code == 200
    # msg-a at limit, next would block, but msg-b is fresh
    resp = _post(client, msg_id="msg-b")
    assert resp.status_code == 200
    assert resp.json()["results"]  # not blocked
