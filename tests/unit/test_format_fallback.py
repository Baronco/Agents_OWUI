"""Unit test for the text fallback (spec 007, US1, FR-009).

When the formatter produces no valid structure, the proxy must degrade to a
valid `messageType: "text"` object with the original text.
"""
from src.services.chat_management import text_fallback


def test_text_fallback_shape():
    r = text_fallback("hola mundo")
    assert r == {
        "messageType": "text",
        "body": "hola mundo",
        "escalate": False,
        "buttons": "",
        "listSections": "",
        "listButtonText": "",
        "quote": "",
    }


def test_text_fallback_handles_empty():
    r = text_fallback("")
    assert r["messageType"] == "text"
    assert r["body"] == ""
    # always the 7 fields
    assert set(r.keys()) == {
        "messageType", "body", "escalate", "buttons",
        "listSections", "listButtonText", "quote",
    }
