"""Unit tests for the title_generation override (spec 008).

A brand-new sales chat (chat_id=None, parent_id=None) may set
``title_generation`` per tenant; continued chats never trigger it, so OWUI
generates the title once per conversation instead of on every turn.
"""
from src.services.chat_management import _completion_payload


def _payload(title_generation_enabled=True):
    return _completion_payload(
        model="some-model",
        messages=[{"role": "user", "content": "hola"}],
        chat_id=None,
        parent_id=None,
        user_message={"id": "u1"},
        assistant_msg_id="a1",
        session_id="s1",
        tool_ids=None,
        title_generation_enabled=title_generation_enabled,
    )


def test_title_generation_enabled_by_default_for_new_chat():
    payload = _completion_payload(
        model="some-model",
        messages=[{"role": "user", "content": "hola"}],
        chat_id=None,
        parent_id=None,
        user_message={"id": "u1"},
        assistant_msg_id="a1",
        session_id="s1",
        tool_ids=None,
    )
    assert payload["background_tasks"]["title_generation"] is True


def test_title_generation_disabled_when_overridden():
    payload = _payload(title_generation_enabled=False)
    assert payload["background_tasks"]["title_generation"] is False


def test_title_generation_stays_false_for_continued_chat_regardless_of_override():
    payload = _completion_payload(
        model="some-model",
        messages=[{"role": "user", "content": "hola"}],
        chat_id="chat-123",
        parent_id="msg-456",
        user_message={"id": "u1"},
        assistant_msg_id="a1",
        session_id="s1",
        tool_ids=None,
        title_generation_enabled=True,
    )
    assert payload["background_tasks"]["title_generation"] is False
