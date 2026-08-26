"""Unit tests for REST fallback when socket delivers empty content (spec 012, US3).

When await_completion returns an empty string as content, get_or_create_chat and
continue_chat must fall back to GET /api/v1/chats/{chat_id} and extract the
assistant's last message via _walk_history_chain.
"""
from unittest.mock import patch, MagicMock

from src.services.chat_management import get_or_create_chat, continue_chat
from src.client.openwebui_client import OpenWebUIClient


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _make_chat_body(messages: dict, current_id: str) -> dict:
    return {
        "chat": {
            "history": {
                "messages": messages,
                "currentId": current_id,
            }
        }
    }


def _msg(id_, role, content, parent_id=None):
    return id_, {"id": id_, "role": role, "content": content, "parentId": parent_id}


def _make_mock_client():
    mock = MagicMock(spec=OpenWebUIClient)
    mock.base_url = "http://test"
    mock.session = MagicMock()
    mock.session.headers = {"Authorization": "Bearer test-token"}
    mock.chat_completion.return_value = {"chat_id": "chat-001", "id": "chat-001"}
    # Replicate the static method logic
    mock._chat_inner.side_effect = lambda r: r.get("chat", r) if isinstance(r, dict) else r
    return mock


# ---------------------------------------------------------------------------
# T010 — REST fallback used when socket content is empty (get_or_create_chat)
# ---------------------------------------------------------------------------

def test_get_or_create_chat_rest_fallback_on_empty_socket():
    """Empty socket content → REST fallback extracts from chat history."""
    expected = "Tenemos estas lámparas disponibles para ti."
    k1, m1 = _msg("u1", "user", "busco lamparas")
    k2, m2 = _msg("a1", "assistant", expected, parent_id="u1")
    fallback = _make_chat_body({k1: m1, k2: m2}, current_id="a1")

    mock_client = _make_mock_client()
    mock_client.get_chat.return_value = fallback

    with patch("src.services.chat_management.await_completion") as mock_cmp:
        mock_cmp.return_value = ("chat-001", "", None)
        result = get_or_create_chat(
            user_id="user-x",
            assistant_id="asst-x",
            message_content="busco lamparas",
            owui_client=mock_client,
        )

    assert result is not None
    assert result["assistant_response"] == expected
    mock_client.get_chat.assert_called_once_with("chat-001")


def test_get_or_create_chat_no_fallback_when_socket_has_content():
    """When socket delivers content, REST fallback is NOT called."""
    mock_client = _make_mock_client()

    with patch("src.services.chat_management.await_completion") as mock_cmp:
        mock_cmp.return_value = ("chat-001", "Tengo contenido.", None)
        result = get_or_create_chat(
            user_id="user-x",
            assistant_id="asst-x",
            message_content="hola",
            owui_client=mock_client,
        )

    assert result is not None
    assert result["assistant_response"] == "Tengo contenido."
    mock_client.get_chat.assert_not_called()


# ---------------------------------------------------------------------------
# T011 — Both socket and REST return empty → ERROR logged
# ---------------------------------------------------------------------------

def test_get_or_create_chat_both_empty_logs_error_no_exception():
    """When socket is empty AND REST has no assistant messages, log ERROR without raising."""
    k1, m1 = _msg("u1", "user", "hello")
    fallback = _make_chat_body({k1: m1}, current_id="u1")

    mock_client = _make_mock_client()
    mock_client.get_chat.return_value = fallback

    with patch("src.services.chat_management.await_completion") as mock_cmp, \
         patch("src.services.chat_management.logger") as mock_logger:
        mock_cmp.return_value = ("chat-002", "", None)
        result = get_or_create_chat(
            user_id="user-x",
            assistant_id="asst-x",
            message_content="hello",
            owui_client=mock_client,
        )

    assert result is not None
    assert result["assistant_response"] == ""
    assert mock_logger.error.call_count >= 1


def test_get_or_create_chat_rest_fallback_exception_logs_error_no_raise():
    """REST fallback request raises → ERROR logged, function still returns (no crash)."""
    mock_client = _make_mock_client()
    mock_client.get_chat.side_effect = Exception("network error")

    with patch("src.services.chat_management.await_completion") as mock_cmp, \
         patch("src.services.chat_management.logger") as mock_logger:
        mock_cmp.return_value = ("chat-003", "", None)
        result = get_or_create_chat(
            user_id="user-x",
            assistant_id="asst-x",
            message_content="hello",
            owui_client=mock_client,
        )

    assert result is not None
    # ERROR must be logged at least once (for the exception)
    assert mock_logger.error.call_count >= 1


# ---------------------------------------------------------------------------
# continue_chat REST fallback
# ---------------------------------------------------------------------------

def test_continue_chat_rest_fallback_on_empty_socket():
    """continue_chat: empty socket content → second get_chat call extracts new message."""
    expected = "La respuesta de continuación."

    # First call: existing history (before new turn)
    k1, m1 = _msg("u0", "user", "hola")
    k2, m2 = _msg("a0", "assistant", "Hola!", parent_id="u0")
    current = _make_chat_body({k1: m1, k2: m2}, current_id="a0")

    # Second call (fallback): history with the new assistant message appended
    k3, m3 = _msg("u1", "user", "busco lamparas", parent_id="a0")
    k4, m4 = _msg("a1", "assistant", expected, parent_id="u1")
    fallback = _make_chat_body({k1: m1, k2: m2, k3: m3, k4: m4}, current_id="a1")

    mock_client = _make_mock_client()
    mock_client.get_chat.side_effect = [current, fallback]

    with patch("src.services.chat_management.await_completion") as mock_cmp:
        mock_cmp.return_value = (None, "", None)
        result = continue_chat(
            chat_id="existing-chat",
            message_content="busco lamparas",
            assistant_id="asst-x",
            owui_client=mock_client,
        )

    assert result is not None
    assert result["assistant_response"] == expected
    assert mock_client.get_chat.call_count == 2
