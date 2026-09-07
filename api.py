"""FastAPI entry point for the OWUI Agent Proxy.
Provides the POST /proxy/chat endpoint — an agentic sub-agent call authenticated
by the caller's bearer token and routed to the requested model_id with live-resolved
tools (spec 017).
"""

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from src.client.openwebui_client import (
    AuthExpiredError,
    OpenWebUIClient,
    UnknownModelError,
)
from src.config import OPENWEBUI_BASE_URL
from src.services.chat_management import continue_chat, get_or_create_chat
from src.utils.logger import logger
from src.utils.timing import RequestTiming
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


class ChatRequest(BaseModel):
    message: str
    model_id: str | None = None
    chat_id: str | None = None


class ChatResponse(BaseModel):
    assistant_response: str
    subagent_chat_id: str


@app.post("/proxy/chat", response_model=ChatResponse, operation_id="sub_agent")
def proxy_chat(request: ChatRequest, http_request: Request):
    """Run the requested sub-agent model on a message (specs 017-018, dynamic routing).

    Authenticates by the caller's bearer token (passthrough), resolves the
    target model's configured tools with the ``X-Subagent-Tools-Key`` header,
    continues the given ``chat_id`` or creates a new chat, and returns the
    agent's answer text plus the live sub-agent session id. No JSON config
    file is read.

    Returns:
        A ``ChatResponse`` with ``assistant_response`` and ``subagent_chat_id``.
    """
    timing = RequestTiming()

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")

    if not request.model_id or not request.model_id.strip():
        raise HTTPException(status_code=400, detail="no valid model_id was sent")

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

    tools_key = http_request.headers.get(TOOLS_KEY_HEADER)
    if not tools_key or not tools_key.strip():
        raise HTTPException(
            status_code=401,
            detail="Missing X-Subagent-Tools-Key header",
        )

    assistant_id = request.model_id.strip()
    per_user_client = client.with_token(bearer)

    try:
        tool_ids = client.get_model_tool_ids(assistant_id, tools_key.strip())
    except UnknownModelError as exc:
        raise HTTPException(status_code=400, detail=f"unknown model_id '{assistant_id}'") from exc
    except AuthExpiredError as exc:
        raise HTTPException(
            status_code=500,
            detail="tools lookup unauthorized — check X-Subagent-Tools-Key",
        ) from exc
    # Timeout/network failure already warns inside the helper and yields [];
    # built-in tools still apply, so proceed with the empty list.
    agent_config = {"model": assistant_id, "tool_ids": tool_ids, "title_generation": False}

    logger.info(
        "Received sub-agent proxy chat request (model=%s, chat_id=%s)",
        assistant_id,
        request.chat_id,
    )

    def _run_chat():
        """Continue the given chat or create a new one for the caller's bearer token."""
        chat = None
        if request.chat_id:
            chat = continue_chat(
                request.chat_id,
                request.message,
                assistant_id,
                owui_client=per_user_client,
                tenant_config=agent_config,
                timing=timing,
            )
            if not chat:
                logger.warning(
                    "continue_chat failed for chat_id %s — falling back to new chat",
                    request.chat_id,
                )
        if not request.chat_id or chat is None:
            # The caller's identity is carried by the bearer token (passthrough);
            # get_or_create_chat only uses user_id for logging, so pass a placeholder.
            chat = get_or_create_chat(
                "passthrough",
                assistant_id,
                request.message,
                tenant_config=agent_config,
                owui_client=per_user_client,
                timing=timing,
            )
        return chat

    try:
        chat = _run_chat()
    except AuthExpiredError as exc:
        # Passthrough mode: no credentials to re-authenticate, so surface the
        # auth failure to the caller instead of a silent retry.
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token") from exc

    if not chat:
        raise HTTPException(status_code=500, detail="Chat creation failed")

    sales_text = chat.get("assistant_response", "")
    if not sales_text:
        logger.warning("Returning empty assistant_response for chat %s", chat["chat_id"])

    timing.round_trips = per_user_client.round_trips
    timing.emit(chat_id=chat["chat_id"])

    # chat["chat_id"] is the live session id in all paths: newly created id on
    # first call, echoed id on continuation, new id when continuation falls back.
    return ChatResponse(assistant_response=sales_text, subagent_chat_id=chat["chat_id"])
