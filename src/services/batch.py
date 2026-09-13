"""Batch sub-agent orchestration (spec 020).

Fans a list of sub-agent tasks out concurrently and assembles one outcome per
task. The truncation policy and the tool-facing endpoint description live here
too, so the FastAPI layer stays thin and every rule is unit-testable.

Concurrency is needed because Open WebUI runs regular tool calls sequentially
and only parallelizes its own native ``delegate_task``; an external tool server
must therefore fan out server-side.
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Protocol

from src.client.openwebui_client import (
    AuthExpiredError,
    OpenWebUIClient,
    UnknownModelError,
)
from src.services.chat_management import continue_chat, get_or_create_chat
from src.utils.logger import logger


class BatchTaskLike(Protocol):
    """Minimal task shape the batch runner needs (satisfied by ``api.BatchTask``)."""

    message: str
    model_id: str | None
    chat_id: str | None


@dataclass
class BatchTaskOutcome:
    """Result of one batch task, aligned by index with the executed task list."""

    index: int
    model_id: str
    status: str
    assistant_response: str = ""
    subagent_chat_id: str | None = None
    error: str | None = None


TaskStartHook = Callable[[int, int, BatchTaskLike], None]
TaskEndHook = Callable[[int, int, BatchTaskLike, BatchTaskOutcome], None]


def truncate_tasks(tasks: list[BatchTaskLike], max_n: int) -> tuple[list[BatchTaskLike], list[int]]:
    """Keep the first ``max_n`` tasks and report the trailing dropped indices."""
    limit = max(max_n, 0)
    kept = list(tasks[:limit])
    dropped = list(range(len(kept), len(tasks)))
    return kept, dropped


def build_batch_description(max_n: int) -> str:
    """Return the OpenAPI description (tool context) for the batch endpoint."""
    return (
        "Run several sub-agent tasks concurrently in a single call.\n\n"
        "Use this when you have independent tasks: each runs in parallel and the "
        "response returns one result per task, in the same order, each with "
        "`assistant_response` and `subagent_chat_id`.\n\n"
        "Each task object has:\n"
        "- `message` (string, required): the instruction for that sub-agent.\n"
        "- `model_id` (string, required): the target sub-agent model id.\n"
        "- `chat_id` (string, optional): continue an existing sub-agent session.\n\n"
        f"Maximum: {max_n} sub-agents per call (MAX_BATCH_SUBAGENTS). If more are "
        f"sent, only the first {max_n} run; the rest are dropped and listed in the "
        "response `info` field."
    )


def truncation_info(dropped_indices: list[int], max_n: int) -> str:
    """Build the response ``info`` note describing dropped trailing tasks."""
    indices = ", ".join(str(i) for i in dropped_indices)
    count = len(dropped_indices)
    noun = "sub-agent" if count == 1 else "sub-agents"
    return (
        f"Truncated {count} trailing {noun} (indices {indices}): the maximum of "
        f"{max_n} sub-agents per batch (MAX_BATCH_SUBAGENTS) was exceeded."
    )


def _run_task(
    index: int,
    spec: BatchTaskLike,
    base_client: OpenWebUIClient,
    bearer: str,
    tools_key: str,
    create_chat: Callable,
    continue_chat_fn: Callable,
    on_progress: Callable[[dict], None] | None = None,
) -> BatchTaskOutcome:
    """Execute one task and return its outcome, isolating all failures."""
    model_id = (spec.model_id or "").strip()
    if not model_id:
        return BatchTaskOutcome(
            index=index, model_id="", status="error", error="model_id is required"
        )
    if not (spec.message or "").strip():
        return BatchTaskOutcome(
            index=index, model_id=model_id, status="error", error="message must not be empty"
        )

    try:
        tool_ids = base_client.get_model_tool_ids(model_id, tools_key)
    except UnknownModelError:
        return BatchTaskOutcome(
            index=index,
            model_id=model_id,
            status="error",
            error=f"unknown model_id '{model_id}'",
        )
    except AuthExpiredError:
        return BatchTaskOutcome(
            index=index, model_id=model_id, status="error", error="tools lookup unauthorized"
        )
    except Exception as exc:
        logger.warning("Batch task %d tool lookup failed for %s: %s", index, model_id, exc)
        tool_ids = []

    per_user_client = base_client.with_token(bearer)
    agent_config = {"model": model_id, "tool_ids": tool_ids, "title_generation": False}

    try:
        chat = None
        if spec.chat_id:
            chat = continue_chat_fn(
                spec.chat_id,
                spec.message,
                model_id,
                owui_client=per_user_client,
                tenant_config=agent_config,
                on_progress=on_progress,
            )
            if not chat:
                logger.warning(
                    "Batch task %d continue failed for chat %s — creating new chat",
                    index,
                    spec.chat_id,
                )
        if not spec.chat_id or chat is None:
            chat = create_chat(
                "passthrough",
                model_id,
                spec.message,
                tenant_config=agent_config,
                owui_client=per_user_client,
                on_progress=on_progress,
            )
    except AuthExpiredError:
        return BatchTaskOutcome(
            index=index, model_id=model_id, status="error", error="unauthorized"
        )
    except Exception as exc:
        logger.error("Batch task %d failed for %s: %s", index, model_id, exc)
        return BatchTaskOutcome(index=index, model_id=model_id, status="error", error=str(exc))

    if not chat:
        return BatchTaskOutcome(
            index=index, model_id=model_id, status="error", error="chat creation failed"
        )

    return BatchTaskOutcome(
        index=index,
        model_id=model_id,
        status="ok",
        assistant_response=chat.get("assistant_response", ""),
        subagent_chat_id=chat.get("chat_id"),
    )


def _safe_call(callback: Callable | None, *args) -> None:
    if callback is None:
        return
    try:
        callback(*args)
    except Exception as exc:
        logger.debug("Batch hook failed: %s", exc)


def run_batch(
    tasks: list[BatchTaskLike],
    base_client: OpenWebUIClient,
    bearer: str,
    tools_key: str,
    on_start: TaskStartHook | None = None,
    on_end: TaskEndHook | None = None,
    on_progress_factory: Callable[[int, BatchTaskLike], Callable[[dict], None] | None]
    | None = None,
    create_chat: Callable | None = None,
    continue_chat_fn: Callable | None = None,
) -> list[BatchTaskOutcome]:
    """Run every task concurrently and return outcomes ordered by task index.

    ``on_progress_factory(index, spec)`` optionally returns a per-task callback
    that receives normalized ``{"type": "status"|"tool", ...}`` progress events
    from the sub-agent's socket stream.
    """
    create = create_chat or get_or_create_chat
    cont = continue_chat_fn or continue_chat
    total = len(tasks)
    if total == 0:
        return []

    outcomes: list[BatchTaskOutcome | None] = [None] * total

    def work(index: int, spec: BatchTaskLike) -> tuple[int, BatchTaskOutcome]:
        _safe_call(on_start, index, total, spec)
        progress_hook = (
            on_progress_factory(index, spec) if on_progress_factory is not None else None
        )
        try:
            outcome = _run_task(
                index,
                spec,
                base_client,
                bearer,
                tools_key,
                create,
                cont,
                on_progress=progress_hook,
            )
        except Exception as exc:
            logger.error("Batch task %d crashed: %s", index, exc)
            outcome = BatchTaskOutcome(
                index=index,
                model_id=(spec.model_id or ""),
                status="error",
                error=str(exc),
            )
        _safe_call(on_end, index, total, spec, outcome)
        return index, outcome

    with ThreadPoolExecutor(max_workers=total) as pool:
        futures = [pool.submit(work, i, spec) for i, spec in enumerate(tasks)]
        for future in as_completed(futures):
            index, outcome = future.result()
            outcomes[index] = outcome

    return [outcome for outcome in outcomes if outcome is not None]
