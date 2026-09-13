"""Progress message and emoji composition for sub-agent status events (spec 020).

Pure helpers so the wording and the (random) task-relevant emoji selection are
unit-testable without a live chat. The caller picks the emoji from the returned
pool with ``random.choice``.
"""

from __future__ import annotations

import random

_GENERIC = ("🧠", "🤖", "✨", "⚡", "🚀", "💡", "🔮")

# Ordered keyword groups → emoji pool. First match wins.
_KEYWORD_POOLS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        (
            "search",
            "web",
            "búsqueda",
            "busqueda",
            "research",
            "investiga",
            "news",
            "noticia",
            "trm",
            "browse",
        ),
        ("🔍", "🌐", "🛰️", "🧭", "📡"),
    ),
    (
        (
            "file",
            "archivo",
            "pdf",
            "xlsx",
            "docx",
            "pptx",
            "report",
            "informe",
            "document",
            "csv",
            "gen-files",
        ),
        ("📄", "📊", "📁", "📝", "🗂️", "📑"),
    ),
    (
        ("image", "imagen", "picture", "foto", "chart", "gráfico", "grafico"),
        ("🖼️", "🎨", "📷", "📈"),
    ),
    (
        ("code", "código", "codigo", "script", "python", "program"),
        ("💻", "⚙️", "🧪", "🛠️"),
    ),
)

_FINISH_EMOJIS = ("✅", "🎉", "🏁", "🌟")
_FAIL_EMOJI = "❌"


def task_emoji_pool(model_id: str | None, message: str | None) -> list[str]:
    """Return a task-relevant emoji pool (generic when nothing matches)."""
    text = f"{model_id or ''} {message or ''}".lower()
    for keywords, pool in _KEYWORD_POOLS:
        if any(keyword in text for keyword in keywords):
            return list(pool)
    return list(_GENERIC)


def finish_emoji(error: str | None) -> str:
    """Return the failure emoji on error, otherwise a random success emoji."""
    if error:
        return _FAIL_EMOJI
    return random.choice(_FINISH_EMOJIS)


def start_message(model_id: str, index: int, total: int, emoji: str) -> str:
    """Compose the per-task start status (Claude-style "is thinking")."""
    return f"{emoji} {model_id} is thinking… (task {index + 1}/{total})"


def finish_message(model_id: str, index: int, total: int, error: str | None, emoji: str) -> str:
    """Compose the per-task completion status."""
    if error:
        return f"{emoji} {model_id} failed (task {index + 1}/{total})"
    return f"{emoji} {model_id} has finished (task {index + 1}/{total})"


def status_message(model_id: str, description: str, emoji: str) -> str:
    """Compose an intermediate status forwarded from Open WebUI."""
    return f"{emoji} {model_id}: {description}"


def tool_message(model_id: str, tool_name: str, emoji: str) -> str:
    """Compose a "is using tool X" status."""
    return f"{emoji} {model_id} is using {tool_name}…"
