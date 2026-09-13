"""Contract tests for batch truncation (spec 020, US2)."""

from fastapi.testclient import TestClient

import api as proxy_api
import src.services.batch as batch


def _patch(monkeypatch):
    monkeypatch.setattr(proxy_api.client, "get_model_tool_ids", lambda *a, **k: [])

    def fake_create(user_id, assistant_id, message, **kwargs):
        return {"chat_id": f"c-{assistant_id}", "assistant_response": "ok"}

    monkeypatch.setattr(batch, "get_or_create_chat", fake_create)
    monkeypatch.setattr(batch, "continue_chat", lambda *a, **k: None)


def _post(client, count, max_n, monkeypatch):
    monkeypatch.setattr(proxy_api, "MAX_BATCH_SUBAGENTS", max_n)
    headers = {"Authorization": "Bearer tok", "X-Subagent-Tools-Key": "k"}
    tasks = [{"message": f"m{i}", "model_id": f"model{i}"} for i in range(count)]
    return client.post("/proxy/chat/batch", json={"tasks": tasks}, headers=headers)


def test_over_limit_batch_is_truncated_with_info(monkeypatch):
    """4 tasks with max 2 -> 2 results, truncated_count 2, info names indices 2,3."""
    _patch(monkeypatch)
    client = TestClient(proxy_api.app)

    resp = _post(client, count=4, max_n=2, monkeypatch=monkeypatch)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 2
    assert data["truncated_count"] == 2
    assert data["max_subagents"] == 2
    assert "2, 3" in data["info"]
    assert "MAX_BATCH_SUBAGENTS" in data["info"]


def test_within_limit_has_no_info(monkeypatch):
    """A batch inside the limit carries no truncation note."""
    _patch(monkeypatch)
    client = TestClient(proxy_api.app)

    resp = _post(client, count=2, max_n=2, monkeypatch=monkeypatch)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 2
    assert data["truncated_count"] == 0
    assert data["info"] is None
