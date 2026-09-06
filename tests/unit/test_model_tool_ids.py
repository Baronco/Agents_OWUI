"""Unit tests for model tool-list lookup (spec 017, Foundational).

`get_model_tool_ids` resolves a model's configured tools per request via
`GET /api/v1/models/model?id=...`, so the chat endpoint no longer reads
`tool_ids` from any JSON config file.
"""

from unittest.mock import MagicMock

import pytest
import requests

from src.client.openwebui_client import (
    AuthExpiredError,
    OpenWebUIClient,
    UnknownModelError,
)


def _make_client():
    client = OpenWebUIClient(base_url="http://test")
    client.session = MagicMock()
    return client


def _resp(status=200, payload=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload if payload is not None else {}
    r.request.method = "GET"
    r.request.url = "http://test/api/v1/models/model?id=m"
    return r


def test_returns_meta_tool_ids_on_success():
    """200 with meta.toolIds returns the configured tool list."""
    client = _make_client()
    client.session.get.return_value = _resp(
        200, {"id": "m", "meta": {"toolIds": ["server:1", "chat_id"]}}
    )

    result = client.get_model_tool_ids("m", "tools-key")

    assert result == ["server:1", "chat_id"]
    _, kwargs = client.session.get.call_args
    assert kwargs["headers"] == {"Authorization": "Bearer tools-key"}


def test_missing_tool_ids_defaults_to_empty():
    """200 without meta.toolIds returns an empty list (never None)."""
    client = _make_client()
    client.session.get.return_value = _resp(200, {"id": "m", "meta": {}})

    assert client.get_model_tool_ids("m", "tools-key") == []


def test_unknown_model_raises():
    """404 raises the UnknownModelError domain exception."""
    client = _make_client()
    client.session.get.return_value = _resp(404, {"detail": "not found"})

    with pytest.raises(UnknownModelError):
        client.get_model_tool_ids("nope", "tools-key")


def test_unauthorized_key_raises_auth_error():
    """401 propagates as AuthExpiredError (distinct from unknown-model)."""
    client = _make_client()
    client.session.get.return_value = _resp(401, {"detail": "unauthorized"})

    with pytest.raises(AuthExpiredError):
        client.get_model_tool_ids("m", "bad-key")


def test_timeout_returns_empty_list():
    """Timeout/network failure warns and returns [] (built-ins still apply)."""
    client = _make_client()
    client.session.get.side_effect = requests.Timeout("timed out")

    assert client.get_model_tool_ids("m", "tools-key") == []


def test_invalid_json_body_returns_empty_list():
    """A 200 with a non-JSON body returns [] instead of raising."""
    client = _make_client()
    resp = _resp(200, None)
    resp.json.side_effect = ValueError("bad json")
    client.session.get.return_value = resp

    assert client.get_model_tool_ids("m", "tools-key") == []
