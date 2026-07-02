"""Unit tests for OWUI 0.10.2 socket event handling (spec 012).

Tests cover:
- _extract_text_from_output: pure helper for the new output-array format
- _on_events handler: sets state.content from done event in 0.10.2 format
- Debug logging: logger.debug called for matched events (US2)
"""
import threading
from unittest.mock import patch, MagicMock

from src.client.owui_socket import _extract_text_from_output, _CompletionState, _make_client


# ---------------------------------------------------------------------------
# T002 — _extract_text_from_output
# ---------------------------------------------------------------------------

def _msg_item(text: str, status: str = "completed") -> dict:
    return {
        "type": "message",
        "id": "msg_abc123",
        "status": status,
        "role": "assistant",
        "content": [{"type": "output_text", "text": text}],
    }


def _fc_item(name: str = "search_catalog") -> dict:
    return {"type": "function_call", "id": "fc_001", "call_id": "fc_001", "name": name, "status": "completed"}


def _fco_item() -> dict:
    return {"type": "function_call_output", "id": "fco_001", "call_id": "fc_001",
            "output": [{"type": "input_text", "text": "[]"}], "status": "completed"}


def test_extract_simple_message():
    output = [_msg_item("Hola, te ofrezco estas lámparas.")]
    assert _extract_text_from_output(output) == "Hola, te ofrezco estas lámparas."


def test_extract_message_after_tool_calls():
    output = [_fc_item(), _fco_item(), _msg_item("Resultado de la búsqueda.")]
    assert _extract_text_from_output(output) == "Resultado de la búsqueda."


def test_extract_returns_last_message_item():
    output = [_msg_item("first"), _fc_item(), _fco_item(), _msg_item("second")]
    assert _extract_text_from_output(output) == "second"


def test_extract_empty_list():
    assert _extract_text_from_output([]) == ""


def test_extract_non_list():
    assert _extract_text_from_output(None) == ""
    assert _extract_text_from_output("not a list") == ""
    assert _extract_text_from_output({}) == ""


def test_extract_message_item_with_no_text_parts():
    output = [{"type": "message", "role": "assistant", "content": [], "status": "completed"}]
    assert _extract_text_from_output(output) == ""


def test_extract_message_item_with_empty_text():
    output = [_msg_item("")]
    assert _extract_text_from_output(output) == ""


def test_extract_skips_non_assistant_message_items():
    output = [{"type": "message", "role": "user", "content": [{"type": "output_text", "text": "user msg"}]}]
    assert _extract_text_from_output(output) == ""


def test_extract_only_tool_call_items():
    output = [_fc_item(), _fco_item()]
    assert _extract_text_from_output(output) == ""


# ---------------------------------------------------------------------------
# T003 — _on_events sets state.content from 0.10.2 done event
# ---------------------------------------------------------------------------

def _make_state_and_handler(msg_id: str):
    """Create a _CompletionState and extract the _on_events handler from a real sio client."""
    state = _CompletionState()
    sio = _make_client(msg_id, state)
    handler = sio.handlers["/"]["events"]
    return state, handler


def _wrap_event(msg_id: str, inner_type: str, inner_data: dict) -> dict:
    return {
        "message_id": msg_id,
        "data": {"type": inner_type, "data": inner_data},
    }


def test_on_events_sets_content_from_0102_done_event():
    """0.10.2 done event: content in output array, no top-level content field."""
    msg_id = "test-msg-001"
    state, handler = _make_state_and_handler(msg_id)

    done_event = _wrap_event(msg_id, "chat:completion", {
        "done": True,
        "output": [_msg_item("Tenemos varias lámparas disponibles.")],
        "title": "Test chat",
    })
    handler(done_event)

    assert state.done.is_set()
    assert state.content == "Tenemos varias lámparas disponibles."


def test_on_events_sets_content_from_0102_done_event_with_tools():
    """0.10.2 done event with tool calls before the message item."""
    msg_id = "test-msg-002"
    state, handler = _make_state_and_handler(msg_id)

    done_event = _wrap_event(msg_id, "chat:completion", {
        "done": True,
        "output": [_fc_item(), _fco_item(), _msg_item("Estos son los productos encontrados.")],
        "title": "Test chat",
    })
    handler(done_event)

    assert state.done.is_set()
    assert state.content == "Estos son los productos encontrados."


def test_on_events_preserves_094_done_path():
    """0.9.4 done event: content string at top level still works."""
    msg_id = "test-msg-003"
    state, handler = _make_state_and_handler(msg_id)

    done_event = _wrap_event(msg_id, "chat:completion", {
        "done": True,
        "content": "Respuesta en formato antiguo.",
    })
    handler(done_event)

    assert state.done.is_set()
    assert state.content == "Respuesta en formato antiguo."


def test_on_events_0102_done_with_existing_content_not_overwritten():
    """If state.content was already set (e.g., from a replace event), the done event should not clear it."""
    msg_id = "test-msg-004"
    state, handler = _make_state_and_handler(msg_id)

    # Simulate content already set from a previous replace event
    state.content = "Ya tenía contenido."

    done_event = _wrap_event(msg_id, "chat:completion", {
        "done": True,
        "output": [_msg_item("Otro texto.")],
        "title": "Test chat",
    })
    handler(done_event)

    assert state.done.is_set()
    # state.content should NOT be overwritten if it was already set
    assert state.content == "Ya tenía contenido."


def test_on_events_ignores_wrong_message_id():
    """Events with a different message_id must be silently ignored."""
    msg_id = "test-msg-005"
    state, handler = _make_state_and_handler(msg_id)

    wrong_event = _wrap_event("OTHER-MSG-ID", "chat:completion", {
        "done": True,
        "content": "should be ignored",
    })
    handler(wrong_event)

    assert not state.done.is_set()
    assert state.content == ""


# ---------------------------------------------------------------------------
# T007 — US2: debug logging
# ---------------------------------------------------------------------------

def test_on_events_debug_logged_for_matched_event():
    """logger.debug must be called with the raw event when message_id matches."""
    msg_id = "test-msg-006"
    state, handler = _make_state_and_handler(msg_id)

    ev = _wrap_event(msg_id, "chat:completion", {"done": True, "content": "test"})

    with patch("src.client.owui_socket.logger") as mock_logger:
        handler(ev)
        mock_logger.debug.assert_called()
        # Verify the raw event dict appears in the call args
        call_args = mock_logger.debug.call_args
        assert ev in call_args.args or ev in call_args.kwargs.values() or any(
            ev == a for a in call_args.args
        )


def test_on_events_debug_not_logged_for_unmatched_event():
    """logger.debug must NOT be called when message_id does not match."""
    msg_id = "test-msg-007"
    state, handler = _make_state_and_handler(msg_id)

    ev = _wrap_event("DIFFERENT-ID", "chat:completion", {"done": True, "content": "ignored"})

    with patch("src.client.owui_socket.logger") as mock_logger:
        handler(ev)
        mock_logger.debug.assert_not_called()
