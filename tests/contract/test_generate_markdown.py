"""Contract test (spec 015, US1): POST /learn returns a plain confirmation.

Runs offline by monkeypatching the endpoint's collaborators so no live OWUI
HTTP/socket happens. The handler is an ``async def``, so the FastAPI
``TestClient`` drives the real dispatch path.
"""
from fastapi.testclient import TestClient

import api as proxy_api


def _patch_common(monkeypatch, result):
    # No real user-id lookup, no real upload, no real knowledge filing.
    monkeypatch.setattr(
        proxy_api, "build_request_context", lambda req: {"headers": dict(req.headers)}
    )
    monkeypatch.setattr(proxy_api, "_generate_markdown", lambda *a, **k: result)
    monkeypatch.setattr(proxy_api, "build_download_response", lambda res: res)
    monkeypatch.setattr(proxy_api, "OWUI_URL", "http://localhost:3000")


def _post(client, python_script, file_name):
    return client.post(
        "/learn",
        json={"python_script": python_script, "file_name": file_name},
    )


def test_learn_returns_confirmation_on_success(monkeypatch):
    """A successful generation replies with a plain confirmation message."""
    _patch_common(monkeypatch, {
        "file_path_download": "[Download report.md](/api/v1/files/abc/content)",
        "download_url": "/api/v1/files/abc/content",
        "file_id": "abc",
        "file_name": "report",
        "file_type": "md",
    })
    client = TestClient(proxy_api.app)

    resp = _post(client, "MD_BUFFER = md_buffer\nMD_BUFFER.write(b'# Hola\\n')", "report")

    assert resp.status_code == 200
    assert resp.json() == {"message": "Meta-learning created"}


def test_learn_returns_error_when_result_has_error(monkeypatch):
    """A failure carrier (error key) is surfaced, not treated as success."""
    _patch_common(monkeypatch, {"error": {"message": "upload failed"}})
    client = TestClient(proxy_api.app)

    resp = _post(client, "bad script", "report")

    assert resp.status_code == 200
    assert "error" in resp.json()


def test_learn_returns_error_when_result_is_error_json_string(monkeypatch):
    """A JSON-string error payload is parsed and surfaced."""
    _patch_common(monkeypatch, '{"error": {"message": "no user id"}}')
    client = TestClient(proxy_api.app)

    resp = _post(client, "bad script", "report")

    assert resp.status_code == 200
    assert "error" in resp.json()


def test_generate_markdown_returns_error_on_failure(monkeypatch):
    """A generation collaborator failure degrades to an error payload."""
    # Generate collaborator fails -> endpoint degrades to an error payload.
    monkeypatch.setattr(proxy_api, "build_request_context", lambda req: {"headers": {}})

    def _raise(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(proxy_api, "_generate_markdown", _raise)
    monkeypatch.setattr(proxy_api, "build_download_response", lambda res: res)
    monkeypatch.setattr(proxy_api, "OWUI_URL", "http://localhost:3000")
    client = TestClient(proxy_api.app)

    resp = _post(client, "bad script", "report")

    assert resp.status_code == 200
    assert "error" in resp.json()


def test_proxy_chat_still_served_by_same_app(monkeypatch):
    """The new endpoint is additive on the same FastAPI application."""
    assert hasattr(proxy_api, "proxy_chat")
    assert hasattr(proxy_api, "learn")
    assert any(getattr(r, "path", None) == "/proxy/chat" for r in proxy_api.app.routes)
    assert any(getattr(r, "path", None) == "/learn" for r in proxy_api.app.routes)
    assert not any(getattr(r, "path", None) == "/generate_markdown" for r in proxy_api.app.routes)


def test_learn_handler_is_async():
    """The /learn handler is a coroutine function (async def)."""
    import inspect

    assert inspect.iscoroutinefunction(proxy_api.learn)


def test_endpoint_description_has_tool_instructions():
    """The OpenAPI description carries the ported markdown tool instructions."""
    for route in proxy_api.app.routes:
        if getattr(route, "path", None) == "/learn":
            desc = route.description or ""
            assert "MD_BUFFER = md_buffer" in desc
