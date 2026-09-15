"""Progress message and emoji composition for sub-agent status events (spec 020).

Pure helpers so the wording and the deterministic task-relevant emoji selection are
unit-testable without a live chat. Each task gets one stable emoji for all its
events; finish is always ✅/❌ for scan-ability.
"""

from __future__ import annotations

import hashlib

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

_FAIL_EMOJI = "❌"
_OK_EMOJI = "✅"


def task_emoji_pool(model_id: str | None, message: str | None) -> list[str]:
    """Return a task-relevant emoji pool (generic when nothing matches)."""
    text = f"{model_id or ''} {message or ''}".lower()
    for keywords, pool in _KEYWORD_POOLS:
        if any(keyword in text for keyword in keywords):
            return list(pool)
    return list(_GENERIC)


def task_emoji(model_id: str | None, message: str | None) -> str:
    """Return one stable emoji for the task (deterministic, not random)."""
    pool = task_emoji_pool(model_id, message)
    key = f"{model_id or ''}|{message or ''}"
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    return pool[int(digest, 16) % len(pool)]


def finish_emoji(error: str | None) -> str:
    """Return ✅ on success, ❌ on error (deterministic for scan-ability)."""
    return _FAIL_EMOJI if error else _OK_EMOJI


def _snippet(message: str | None, max_len: int = 48) -> str:
    text = (message or "").strip().replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def start_message(
    model_id: str, index: int, total: int, emoji: str = "🤖", message: str | None = None
) -> str:
    """Compose the per-task start status (uniform Claude-style)."""
    snippet = _snippet(message)
    suffix = f' - "{snippet}"' if snippet else ""
    return f"{emoji} {model_id} is thinking in task {index + 1}{suffix}"


def finish_message(
    model_id: str,
    index: int,
    total: int,
    error: str | None,
    emoji: str,
    elapsed_s: float | None = None,
) -> str:
    """Compose the per-task completion status."""
    base = (
        f"{emoji} {model_id} task {index + 1} has finished"
        if not error
        else f"{emoji} {model_id} task {index + 1} failed"
    )
    if elapsed_s is not None and not error:
        return f"{base} in {elapsed_s:.1f}s"
    if elapsed_s is not None and error:
        return f"{base} after {elapsed_s:.1f}s"
    return base


def status_message(model_id: str, description: str, emoji: str) -> str:
    """Compose an intermediate status forwarded from Open WebUI."""
    return f"{emoji} {model_id}: {description}"


def tool_message(model_id: str, tool_name: str, emoji: str = "🔨") -> str:
    """Compose a "is using tool X" status (uniform hammer)."""
    return f"{emoji} {model_id} is using {tool_name}..."


def batch_start_message(total: int, emoji: str = "🚀") -> str:
    """Compose the batch-level start event."""
    label = "sub-agent" if total == 1 else "sub-agents"
    return f"{emoji} Launching {total} {label}..."


def batch_finish_message(total: int, elapsed_s: float, emoji: str = "✅") -> str:
    """Compose the batch-level completion event (wall time, not sum/average)."""
    label = "sub-agent" if total == 1 else "sub-agents"
    return f"{emoji} All {total} {label} completed in {elapsed_s:.1f}s"


def batch_progress_message(completed: int, total: int, emoji: str = "🔄️") -> str:
    """Compose the batch progress heartbeat."""
    percent = int(completed / total * 100) if total else 0
    return f"{emoji} task progress {percent}% ({completed}/{total})"
