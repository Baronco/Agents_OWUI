"""Unit tests for concurrent batch fan-out (spec 020, US1)."""

import time

import src.services.batch as batch


class _FakeClient:
    """Minimal OpenWebUIClient stand-in for the batch runner."""

    def get_model_tool_ids(self, model_id, token):
        return []

    def with_token(self, token):
        return self


class _Task:
    """Duck-typed task matching BatchTaskLike."""

    def __init__(self, model_id="m", message="hi", chat_id=None):
        self.model_id = model_id
        self.message = message
        self.chat_id = chat_id


def test_batch_runs_tasks_concurrently(monkeypatch):
    """Three 200ms tasks finish in well under their serial 600ms sum."""
    monkeypatch.setattr(
        batch,
        "get_or_create_chat",
        lambda *a, **k: (time.sleep(0.2), {"chat_id": "c", "assistant_response": "ok"})[1],
    )
    monkeypatch.setattr(batch, "continue_chat", lambda *a, **k: None)

    tasks = [_Task(f"m{i}") for i in range(3)]
    start = time.monotonic()
    outcomes = batch.run_batch(tasks, base_client=_FakeClient(), bearer="tok", tools_key="k")
    elapsed = time.monotonic() - start

    assert len(outcomes) == 3
    assert all(o.status == "ok" for o in outcomes)
    assert elapsed < 0.5, f"tasks ran serially (elapsed={elapsed:.2f}s)"


def test_empty_batch_returns_no_outcomes():
    """An empty task list yields an empty result list."""
    assert batch.run_batch([], base_client=_FakeClient(), bearer="tok", tools_key="k") == []


def test_outcomes_preserve_request_order(monkeypatch):
    """Results are ordered by request index regardless of completion order."""

    def create(user_id, assistant_id, message, **kwargs):
        if assistant_id == "slow":
            time.sleep(0.15)
        return {"chat_id": f"c-{assistant_id}", "assistant_response": assistant_id}

    monkeypatch.setattr(batch, "get_or_create_chat", create)
    monkeypatch.setattr(batch, "continue_chat", lambda *a, **k: None)

    tasks = [_Task("slow"), _Task("fast0"), _Task("fast1")]
    outcomes = batch.run_batch(tasks, base_client=_FakeClient(), bearer="tok", tools_key="k")

    assert [o.model_id for o in outcomes] == ["slow", "fast0", "fast1"]
