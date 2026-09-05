"""FastAPI entry point for the OWUI Agent Proxy.
Provides the POST /proxy/chat endpoint — an agentic sub-agent call authenticated
by the caller's bearer token and routed to the platform's default agent — plus
POST /learn, the agent's memory / meta-learning tool (spec 015).
"""

from dotenv import load_dotenv

load_dotenv()
from json import dumps, loads
from os import getenv
from pathlib import Path
from typing import Annotated

from fastapi import Body, FastAPI, HTTPException, Request
from pydantic import BaseModel

from src.client.openwebui_client import AuthExpiredError, OpenWebUIClient
from src.config import OPENWEBUI_BASE_URL
from src.services.chat_management import continue_chat, get_or_create_chat
from src.services.tenant_routing import resolve_default_agent
from src.utils.logger import logger
from src.utils.timing import RequestTiming
from tools import shared as tools_shared
from tools.markdown_tool import generate_markdown as _generate_markdown
from tools.shared import (
    DOWNLOAD_HTML_BUTTON,
    build_download_response,
    build_request_context,
)
from utils.config.argument_descriptions import ARGUMENT_DESCRIPTIONS
from utils.http.authorization import _get_bearer_token

app = FastAPI()
client = OpenWebUIClient(base_url=OPENWEBUI_BASE_URL)

# Markdown generation endpoint configuration (spec 015). Read from the
# environment with the same defaults as the GenFilesMCP source project.
OWUI_URL = getenv("OWUI_URL", "http://localhost:8080")
ENABLE_CREATE_KNOWLEDGE = getenv("ENABLE_CREATE_KNOWLEDGE", "true").lower() == "true"
KNOWLEDGE_COLLECTION_NAME = getenv("KNOWLEDGE_COLLECTION_NAME", "My Generated Files").strip()

# Always return the raw structured result (never the HTML download button page),
# so the handler can validate success/error and reply with a plain message.
tools_shared.DOWNLOAD_HTML_BUTTON = False

# Tool instructions for the markdown generator (spec 015), copied verbatim
# from GenFilesMCP. The source resolves the {{SUCCESS_DELIVERY_RULE}}
# placeholder depending on DOWNLOAD_HTML_BUTTON; we replicate that rule.
_MARKDOWN_INSTRUCTIONS_FILE = Path(__file__).parent / "tools" / "markdown_instructions.md"
with _MARKDOWN_INSTRUCTIONS_FILE.open("r", encoding="utf-8") as _f:
    MARKDOWN_DESCRIPTION = _f.read()
if DOWNLOAD_HTML_BUTTON:
    MARKDOWN_DESCRIPTION = MARKDOWN_DESCRIPTION.replace(
        "{{SUCCESS_DELIVERY_RULE}}",
        "On success the chat shows a download button — never invent a download link.",
    )


@app.post("/learn", description=MARKDOWN_DESCRIPTION, operation_id="my_meta_learning")
async def learn(
    request: Request,
    python_script: Annotated[
        str, Body(..., description=ARGUMENT_DESCRIPTIONS["common_args"]["python_script"])
    ],
    file_name: Annotated[
        str, Body(..., description=ARGUMENT_DESCRIPTIONS["common_args"]["file_name"])
    ],
):
    """Record a learning as a Markdown document (spec 015, meta-learning).

    Runs the caller's script to fill the markdown buffer, uploads the resulting
    ``.md`` file to Open WebUI, optionally files it into a knowledge collection,
    and returns a download result. Ported verbatim from GenFilesMCP.

    Exposed at ``/learn`` — the agent's memory / meta-learning tool: call it to
    capture knowledge that goes beyond what is in the agent's base training.

    Returns:
        On success, ``{"message": "Meta-learning created"}``. On failure, the
        underlying error payload (with an ``error`` key).
    """
    logger.info("Received request to record learning (Markdown document)")
    try:
        request_context = build_request_context(request)
        result = _generate_markdown(
            python_script,
            file_name,
            request_context,
            OWUI_URL,
            ENABLE_CREATE_KNOWLEDGE,
            KNOWLEDGE_COLLECTION_NAME,
        )
        response = build_download_response(result)
        # With DOWNLOAD_HTML_BUTTON=False build_download_response returns the
        # structured result unchanged. A failure carries an "error" key; a
        # success never does — so report a plain confirmation message.
        if isinstance(response, str):
            try:
                response = loads(response)
            except ValueError:
                return {"error": response}
        if isinstance(response, dict) and "error" in response:
            return response
        return {"message": "Meta-learning created"}
    except Exception as exc:
        logger.error(f"Error generating Meta-learning: {exc}")
        return dumps(
            {"error": "An error occurred while generating the Meta-learning."},
            ensure_ascii=False,
        )


class ChatRequest(BaseModel):
    message: str
    chat_id: str | None = None


class ChatResponse(BaseModel):
    assistant_response: str


@app.post("/proxy/chat", response_model=ChatResponse, operation_id="sub_agent")
def proxy_chat(request: ChatRequest, http_request: Request):
    """Run the platform's default agent on a message (spec 016, agentic).

    Authenticates by the caller's bearer token (passthrough), routes to the
    default agent, continues the given ``chat_id`` or creates a new chat, and
    returns the agent's answer text.

    Returns:
        A ``ChatResponse`` with only ``assistant_response``.
    """
    timing = RequestTiming()

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")

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

    default_agent = resolve_default_agent()
    if not default_agent:
        raise HTTPException(status_code=500, detail="No default agent configured")

    assistant_id = default_agent.get("model")
    per_user_client = client.with_token(bearer)

    logger.info("Received agentic proxy chat request (chat_id=%s)", request.chat_id)

    def _run_chat():
        """Continue the given chat or create a new one for the caller's bearer token."""
        chat = None
        if request.chat_id:
            chat = continue_chat(
                request.chat_id,
                request.message,
                assistant_id,
                owui_client=per_user_client,
                tenant_config=default_agent,
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
                tenant_config=default_agent,
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

    return ChatResponse(assistant_response=sales_text)
