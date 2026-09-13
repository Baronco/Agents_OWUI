"""FastAPI entry point for the OWUI Agent Proxy.
Provides the single POST /proxy/chat/batch endpoint — an agentic sub-agent call
that runs one or many tasks concurrently. Authenticated by the caller's bearer
token and routed per task to the requested model_id with live-resolved tools.
"""

from dotenv import load_dotenv

load_dotenv()

import random
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from src.client.openwebui_client import OpenWebUIClient
from src.client.owui_events import emit_status
from src.config import MAX_BATCH_SUBAGENTS, OPENWEBUI_BASE_URL
from src.services import progress
from src.services.batch import (
    BatchTaskOutcome,
    build_batch_description,
    run_batch,
    truncate_tasks,
    truncation_info,
)
from src.utils.logger import logger
from tools.shared import build_request_context
from utils.http.authorization import _get_bearer_token

app = FastAPI()
client = OpenWebUIClient(base_url=OPENWEBUI_BASE_URL)

# --- POST /learn disabled (spec 019). Uncomment to restore. ---
# from json import dumps, loads
# from pathlib import Path
# from typing import Annotated
# from fastapi import Body
# from tools import shared as tools_shared
# from tools.markdown_tool import generate_markdown as _generate_markdown
# from tools.shared import DOWNLOAD_HTML_BUTTON, build_download_response
# from utils.config.argument_descriptions import ARGUMENT_DESCRIPTIONS
#
# OWUI_URL = getenv("OWUI_URL", "http://localhost:8080")
# ENABLE_CREATE_KNOWLEDGE = getenv("ENABLE_CREATE_KNOWLEDGE", "true").lower() == "true"
# KNOWLEDGE_COLLECTION_NAME = getenv("KNOWLEDGE_COLLECTION_NAME", "My Generated Files").strip()
# tools_shared.DOWNLOAD_HTML_BUTTON = False
# _MARKDOWN_INSTRUCTIONS_FILE = Path(__file__).parent / "tools" / "markdown_instructions.md"
# with _MARKDOWN_INSTRUCTIONS_FILE.open("r", encoding="utf-8") as _f:
#     MARKDOWN_DESCRIPTION = _f.read()
# if DOWNLOAD_HTML_BUTTON:
#     MARKDOWN_DESCRIPTION = MARKDOWN_DESCRIPTION.replace(
#         "{{SUCCESS_DELIVERY_RULE}}",
#         "On success the chat shows a download button — never invent a download link.",
#     )
#
#
# @app.post("/learn", description=MARKDOWN_DESCRIPTION, operation_id="my_meta_learning")
# async def learn(
#     request: Request,
#     python_script: Annotated[
#         str, Body(..., description=ARGUMENT_DESCRIPTIONS["common_args"]["python_script"])
#     ],
#     file_name: Annotated[
#         str, Body(..., description=ARGUMENT_DESCRIPTIONS["common_args"]["file_name"])
#     ],
# ):
#     """Record a learning as a Markdown document (spec 015, meta-learning)."""
#     logger.info("Received request to record learning (Markdown document)")
#     try:
#         request_context = build_request_context(request)
#         result = _generate_markdown(
#             python_script,
#             file_name,
#             request_context,
#             OWUI_URL,
#             ENABLE_CREATE_KNOWLEDGE,
#             KNOWLEDGE_COLLECTION_NAME,
#         )
#         response = build_download_response(result)
#         if isinstance(response, str):
#             try:
#                 response = loads(response)
#             except ValueError:
#                 return {"error": response}
#         if isinstance(response, dict) and "error" in response:
#             return response
#         return {"message": "Meta-learning created"}
#     except Exception as exc:
#         logger.error(f"Error generating Meta-learning: {exc}")
#         return dumps(
#             {"error": "An error occurred while generating the Meta-learning."},
#             ensure_ascii=False,
#         )


# Header carrying the service API key used to read the target model's
# configured tools. Sent by the API connection, not by the parent agent.
TOOLS_KEY_HEADER = "X-Subagent-Tools-Key"


class BatchTask(BaseModel):
    """One sub-agent invocation inside a batch request."""

    message: str
    model_id: str | None = None
    chat_id: str | None = None


class BatchChatRequest(BaseModel):
    """Tool-facing payload for ``POST /proxy/chat/batch``."""

    tasks: list[BatchTask] = Field(default_factory=list)


class BatchTaskResult(BaseModel):
    """Outcome of one executed batch task, aligned by ``index``."""

    index: int
    model_id: str
    status: Literal["ok", "error"]
    assistant_response: str = ""
    subagent_chat_id: str | None = None
    error: str | None = None


class BatchChatResponse(BaseModel):
    """Batch results plus the configured maximum and any truncation note."""

    results: list[BatchTaskResult]
    max_subagents: int
    truncated_count: int = 0
    info: str | None = None


# Headers forwarded by Open WebUI when ENABLE_FORWARD_USER_INFO_HEADERS=True.
_FORWARDED_CHAT_ID_HEADER = "X-OpenWebUI-Chat-Id"
_FORWARDED_MESSAGE_ID_HEADER = "X-OpenWebUI-Message-Id"

_BATCH_TOOL_DESCRIPTION = build_batch_description(MAX_BATCH_SUBAGENTS)


def _require_bearer(http_request: Request) -> str:
    """Return the caller's bearer token (scheme stripped) or raise 401."""
    bearer = _get_bearer_token(build_request_context(http_request))
    if not bearer:
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")
    # _get_bearer_token returns the full header value ("Bearer <jwt>"), while
    # with_token() adds the scheme itself — strip it once so OWUI receives a
    # single "Bearer <jwt>" instead of a duplicated prefix (which OWUI 401s).
    if bearer[:7].lower() == "bearer ":
        bearer = bearer[7:].strip()
    if not bearer:
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")
    return bearer


def _require_tools_key(http_request: Request) -> str:
    """Return the trimmed X-Subagent-Tools-Key header or raise 401."""
    tools_key = http_request.headers.get(TOOLS_KEY_HEADER)
    if not tools_key or not tools_key.strip():
        raise HTTPException(
            status_code=401,
            detail="Missing X-Subagent-Tools-Key header",
        )
    return tools_key.strip()


def _emit_task_progress(
    bearer: str,
    chat_id: str | None,
    message_id: str | None,
    spec: BatchTask,
    index: int,
    total: int,
    done: bool,
    error: str | None = None,
) -> None:
    """Emit one best-effort start/completion status event for a batch task (US3)."""
    if not chat_id or not message_id:
        return
    model_id = (spec.model_id or "sub-agent").strip() or "sub-agent"
    pool = progress.task_emoji_pool(spec.model_id, spec.message)
    if done:
        emoji = progress.finish_emoji(error)
        description = progress.finish_message(model_id, index, total, error, emoji)
    else:
        description = progress.start_message(model_id, index, total, random.choice(pool))
    emit_status(
        OPENWEBUI_BASE_URL,
        bearer,
        chat_id,
        message_id,
        {"description": description, "done": done},
    )


def _make_progress_emitter(
    bearer: str,
    chat_id: str | None,
    message_id: str | None,
    spec: BatchTask,
):
    """Return a per-task callback for intermediate sub-agent progress, or None.

    The callback receives normalized socket events and forwards them to the
    originating chat as ``status`` events (best-effort).
    """
    if not chat_id or not message_id:
        return None
    model_id = (spec.model_id or "sub-agent").strip() or "sub-agent"
    pool = progress.task_emoji_pool(spec.model_id, spec.message)

    def emit(event: dict) -> None:
        if event.get("type") == "tool":
            description = progress.tool_message(
                model_id, event.get("name") or "a tool", random.choice(pool)
            )
        else:
            data = event.get("data") or {}
            if data.get("hidden"):
                return
            detail = (data.get("description") or "").strip()
            if not detail:
                return
            description = progress.status_message(model_id, detail, random.choice(pool))
        emit_status(
            OPENWEBUI_BASE_URL,
            bearer,
            chat_id,
            message_id,
            {"description": description, "done": False},
        )

    return emit


@app.post(
    "/proxy/chat/batch",
    response_model=BatchChatResponse,
    operation_id="sub_agents",
    summary="Run multiple sub-agent tasks concurrently",
    description=_BATCH_TOOL_DESCRIPTION,
)
def proxy_chat_batch(payload: BatchChatRequest, http_request: Request):
    """Run a batch of sub-agent tasks concurrently (spec 020).

    Validates auth once, truncates to ``MAX_BATCH_SUBAGENTS`` (reporting the
    dropped trailing tasks in ``info``), runs the kept tasks in parallel, and
    emits best-effort start/completion status events to the originating chat
    when the forwarded Open WebUI headers are present.

    Returns:
        A ``BatchChatResponse`` with one result per executed task.
    """
    if not payload.tasks:
        raise HTTPException(status_code=400, detail="tasks must not be empty")

    bearer = _require_bearer(http_request)
    tools_key = _require_tools_key(http_request)

    kept, dropped = truncate_tasks(payload.tasks, MAX_BATCH_SUBAGENTS)
    forwarded_chat_id = http_request.headers.get(_FORWARDED_CHAT_ID_HEADER)
    forwarded_message_id = http_request.headers.get(_FORWARDED_MESSAGE_ID_HEADER)

    def on_start(index: int, total: int, spec: BatchTask) -> None:
        _emit_task_progress(
            bearer, forwarded_chat_id, forwarded_message_id, spec, index, total, done=False
        )

    def on_end(index: int, total: int, spec: BatchTask, outcome: BatchTaskOutcome) -> None:
        _emit_task_progress(
            bearer,
            forwarded_chat_id,
            forwarded_message_id,
            spec,
            index,
            total,
            done=True,
            error=outcome.error,
        )

    def on_progress_factory(index: int, spec: BatchTask):
        return _make_progress_emitter(bearer, forwarded_chat_id, forwarded_message_id, spec)

    logger.info(
        "Received batch sub-agent request (tasks=%d, executed=%d, truncated=%d)",
        len(payload.tasks),
        len(kept),
        len(dropped),
    )

    outcomes = run_batch(
        kept,
        base_client=client,
        bearer=bearer,
        tools_key=tools_key,
        on_start=on_start,
        on_end=on_end,
        on_progress_factory=on_progress_factory,
    )

    results = [
        BatchTaskResult(
            index=outcome.index,
            model_id=outcome.model_id,
            status=outcome.status,
            assistant_response=outcome.assistant_response,
            subagent_chat_id=outcome.subagent_chat_id,
            error=outcome.error,
        )
        for outcome in outcomes
    ]
    info = truncation_info(dropped, MAX_BATCH_SUBAGENTS) if dropped else None
    return BatchChatResponse(
        results=results,
        max_subagents=MAX_BATCH_SUBAGENTS,
        truncated_count=len(dropped),
        info=info,
    )
