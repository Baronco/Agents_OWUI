"""Unit tests for parse_structured_from_text + normalize_structured (spec 007).

The formatter model emits the structured object as plain text (it does not do
native tool calls reliably), so the proxy parses and normalizes it.
"""
import json

from src.services.chat_management import parse_structured_from_text, normalize_structured


# --- parse_structured_from_text ------------------------------------------------

def test_parse_format_response_wrapper():
    text = (
        'format_response({\n  "messageType": "list",\n  "body": "Hola",\n'
        '  "listSections": [{"id":"a","title":"A","description":"d"}],\n'
        '  "listButtonText": "Ver", "buttons": "", "escalate": false, "quote": ""\n})'
    )
    d = parse_structured_from_text(text)
    assert d is not None
    assert d["messageType"] == "list"
    assert isinstance(d["listSections"], list)


def test_parse_bare_json():
    d = parse_structured_from_text('{"messageType": "text", "body": "ok"}')
    assert d is not None and d["body"] == "ok"


def test_parse_code_fence():
    d = parse_structured_from_text('```json\n{"messageType":"text","body":"x"}\n```')
    assert d is not None and d["messageType"] == "text"


def test_parse_garbage_returns_none():
    assert parse_structured_from_text("") is None
    assert parse_structured_from_text("no json here") is None
    assert parse_structured_from_text(None) is None


# --- normalize_structured ------------------------------------------------------

def test_normalize_wraps_bare_rows_and_stringifies():
    d = normalize_structured({
        "messageType": "list",
        "body": "Hola",
        "listSections": [
            {"id": "a", "title": "A", "description": "d1"},
            {"id": "b", "title": "B", "description": "d2"},
        ],
        "listButtonText": "Ver",
    })
    assert d is not None
    # listSections becomes a JSON string with a single wrapping section
    assert isinstance(d["listSections"], str)
    sections = json.loads(d["listSections"])
    assert isinstance(sections, list)
    assert "rows" in sections[0]
    assert len(sections[0]["rows"]) == 2
    # all 7 fields present
    assert set(d.keys()) == {
        "messageType", "body", "escalate", "buttons",
        "listSections", "listButtonText", "quote",
    }


def test_normalize_keeps_sections_with_wrapper():
    d = normalize_structured({
        "messageType": "list",
        "body": "x",
        "listSections": [{"title": "Cat", "rows": [{"id": "a", "title": "A"}]}],
        "listButtonText": "Ver",
    })
    sections = json.loads(d["listSections"])
    assert sections[0]["title"] == "Cat"


def test_normalize_buttons_array_to_string():
    d = normalize_structured({
        "messageType": "buttons",
        "body": "x",
        "buttons": [{"id": "o1", "title": "Uno"}],
    })
    assert isinstance(d["buttons"], str)
    assert json.loads(d["buttons"])[0]["id"] == "o1"


def test_normalize_invalid_type_returns_none():
    assert normalize_structured({"messageType": "foo", "body": "x"}) is None
    assert normalize_structured({"body": "x"}) is None
    assert normalize_structured("nope") is None


def test_normalize_escalate_coercion():
    assert normalize_structured({"messageType": "text", "body": "x", "escalate": "true"})["escalate"] is True
    assert normalize_structured({"messageType": "text", "body": "x", "escalate": "false"})["escalate"] is False
