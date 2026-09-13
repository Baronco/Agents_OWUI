"""Unit tests for progress message/emoji composition (spec 020, US3)."""

from src.services import progress


def test_search_task_gets_search_emoji_pool():
    pool = progress.task_emoji_pool("web-search-subagent", "find the TRM rate")

    assert "🔍" in pool or "🌐" in pool


def test_file_task_gets_file_emoji_pool():
    pool = progress.task_emoji_pool("gen-files-subagent", "generate a PDF report")

    assert "📄" in pool


def test_code_task_gets_code_emoji_pool():
    pool = progress.task_emoji_pool("helper", "write a python script")

    assert "💻" in pool


def test_unknown_task_gets_generic_pool():
    pool = progress.task_emoji_pool("mystery", "do the thing")

    assert "🧠" in pool or "🤖" in pool


def test_start_message_is_thinking_style():
    text = progress.start_message("web-search-subagent", 0, 2, "🔍")

    assert "is thinking" in text
    assert "web-search-subagent" in text
    assert "task 1/2" in text


def test_finish_message_success_and_failure():
    ok = progress.finish_message("m", 1, 2, None, "✅")
    bad = progress.finish_message("m", 1, 2, "boom", "❌")

    assert "has finished" in ok
    assert "task 2/2" in ok
    assert "failed" in bad
    assert "❌" in bad


def test_tool_and_status_messages():
    tool = progress.tool_message("gen-files-subagent", "gen_files", "📄")
    status = progress.status_message("web-search-subagent", "Searching the web", "🌐")

    assert "is using gen_files" in tool
    assert "Searching the web" in status


def test_finish_emoji_is_failure_on_error():
    assert progress.finish_emoji("boom") == "❌"
    assert progress.finish_emoji(None) in ("✅", "🎉", "🏁", "🌟")
