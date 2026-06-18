"""Unit tests for extract_tool_result (spec 007, US1).

Parses the OWUI socket `output` array to recover the structured object returned
by the `format_response` tool. Must take the LAST successful call and ignore
error results.
"""
from src.services.chat_management import extract_tool_result


def _fc(call_id: str, name: str, args: str = "{}") -> dict:
    return {
        "type": "function_call",
        "id": call_id,
        "call_id": call_id,
        "name": name,
        "arguments": args,
        "status": "completed",
    }


def _fco(call_id: str, text: str) -> dict:
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": [{"type": "input_text", "text": text}],
        "status": "completed",
    }


_OK = (
    '{"messageType":"text","body":"hola","escalate":false,"buttons":"",'
    '"listSections":"","listButtonText":"","quote":""}'
)


def test_returns_structured_object():
    output = [
        _fc("c1", "search_catalog"),
        _fco("c1", '{"results": []}'),
        _fc("c2", "format_response"),
        _fco("c2", _OK),
    ]
    result = extract_tool_result(output, "format_response")
    assert result is not None
    assert result["messageType"] == "text"
    assert result["body"] == "hola"


def test_returns_last_successful_ignoring_errors():
    output = [
        _fc("c1", "format_response"),
        _fco("c1", '{"error": true, "field": "buttons", "message": "x", "hint": "y"}'),
        _fc("c2", "format_response"),
        _fco("c2", '{"messageType":"text","body":"ok"}'),
    ]
    result = extract_tool_result(output, "format_response")
    assert result is not None
    assert result["body"] == "ok"


def test_only_errors_returns_none():
    output = [
        _fc("c1", "format_response"),
        _fco("c1", '{"error": true}'),
    ]
    assert extract_tool_result(output, "format_response") is None


def test_garbage_returns_none():
    assert extract_tool_result(None, "format_response") is None
    assert extract_tool_result([], "format_response") is None
    assert extract_tool_result([{"type": "message"}], "format_response") is None
    # tool called but no matching output
    assert extract_tool_result([_fc("c1", "format_response")], "format_response") is None
    # invalid json in output
    assert extract_tool_result(
        [_fc("c1", "format_response"), _fco("c1", "not json")], "format_response"
    ) is None
