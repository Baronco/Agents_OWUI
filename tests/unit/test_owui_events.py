"""Unit tests for best-effort status event emission (spec 020, US3)."""

import src.client.owui_events as events


class _Resp:
    def __init__(self, status_code):
        self.status_code = status_code


def test_posts_status_event_with_auth_and_body(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(url=url, json=json, headers=headers, timeout=timeout)
        return _Resp(200)

    monkeypatch.setattr(events.requests, "post", fake_post)

    ok = events.emit_status(
        "http://owui", "tok", "chat1", "msg1", {"description": "x", "done": False}
    )

    assert ok is True
    assert captured["url"] == "http://owui/api/v1/chats/chat1/messages/msg1/event"
    assert captured["json"] == {"type": "status", "data": {"description": "x", "done": False}}
    assert captured["headers"]["Authorization"] == "Bearer tok"


def test_non_2xx_returns_false(monkeypatch):
    monkeypatch.setattr(events.requests, "post", lambda *a, **k: _Resp(500))

    assert events.emit_status("http://owui", "tok", "chat1", "msg1", {"done": True}) is False


def test_exception_is_swallowed(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("down")

    monkeypatch.setattr(events.requests, "post", boom)

    assert events.emit_status("http://owui", "tok", "chat1", "msg1", {"done": True}) is False


def test_missing_parts_never_posts(monkeypatch):
    called = []
    monkeypatch.setattr(events.requests, "post", lambda *a, **k: called.append(1))

    assert events.emit_status("", "tok", "chat1", "msg1", {}) is False
    assert events.emit_status("http://owui", "", "chat1", "msg1", {}) is False
    assert events.emit_status("http://owui", "tok", "", "msg1", {}) is False
    assert events.emit_status("http://owui", "tok", "chat1", "", {}) is False
    assert called == []
