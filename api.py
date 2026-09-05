"""FastAPI entry point for the OWUI Agent Proxy.
Provides the POST /proxy/chat endpoint as defined in the contract, plus
POST /learn — the agent's memory / meta-learning tool (ported verbatim from
GenFilesMCP's markdown generator, spec 015).
"""

from dotenv import load_dotenv

load_dotenv()
import threading
from datetime import datetime
from json import dumps, loads
from os import getenv
from pathlib import Path
from typing import Annotated

from fastapi import Body, FastAPI, HTTPException, Request
from pydantic import BaseModel

from src.client.openwebui_client import AuthExpiredError, OpenWebUIClient
from src.config import OPENWEBUI_BASE_URL
from src.services.chat_management import continue_chat, get_or_create_chat
from src.services.tenant_routing import resolve_assistant, resolve_tenant_config
from src.services.user_provisioning import get_owui_chat_id, provision_user, store_chat_mapping
from src.utils.logger import logger
from src.utils.timing import RequestTiming
from tools import shared as tools_shared
from tools.markdown_tool import generate_markdown as _generate_markdown
from tools.shared import DOWNLOAD_HTML_BUTTON, build_download_response, build_request_context
from utils.config.argument_descriptions import ARGUMENT_DESCRIPTIONS

app = FastAPI()
client = OpenWebUIClient(base_url=OPENWEBUI_BASE_URL)
_user_locks: dict = {}
_user_locks_lock = threading.Lock()

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


def _get_user_lock(client_phone: str, tenant_id: str) -> threading.Lock:
    key = f"{client_phone}:{tenant_id}"
    with _user_locks_lock:
        if key not in _user_locks:
            _user_locks[key] = threading.Lock()
        return _user_locks[key]


class ChatRequest(BaseModel):
    tenant_id: str
    client_phone: str
    chat_id: str
    message: str


class ChatResponse(BaseModel):
    assistant_response: str
    chat_id: str
    user_id: str
    assistant_id: str
    tenant_id: str
    timestamp: str
    follow_ups: list[str] = []


@app.post("/proxy/chat", response_model=ChatResponse)
def proxy_chat(request: ChatRequest):
    timing = RequestTiming()
    logger.info(
        "Received proxy chat request for client %s tenant %s",
        request.client_phone,
        request.tenant_id,
    )

    assistant_id = resolve_assistant(request.tenant_id)
    if not assistant_id:
        raise HTTPException(status_code=404, detail="Unknown tenant mapping")

    tenant_config = resolve_tenant_config(request.tenant_id)

    def _provision(force: bool = False):
        with timing.phase("provision_ms"):
            return provision_user(
                request.client_phone, request.tenant_id, owui_client=client, force=force
            )

    def _run_chat(info):
        """Run the continue/create flow for the given provisioned user.

        Returns (per_user_client, chat). May raise AuthExpiredError if the
        cached token is stale, which the caller handles with one re-auth retry.
        """
        per_user_client = client.with_token(info["token"])
        owui_chat_id = get_owui_chat_id(info["email"], request.chat_id)

        chat = None
        if owui_chat_id:
            chat = continue_chat(
                owui_chat_id,
                request.message,
                assistant_id,
                owui_client=per_user_client,
                tenant_config=tenant_config,
                timing=timing,
            )
            if not chat:
                logger.warning(
                    "continue_chat failed for owui_id %s — falling back to new chat", owui_chat_id
                )
        if not owui_chat_id or chat is None:
            chat = get_or_create_chat(
                info["user_id"],
                assistant_id,
                request.message,
                tenant_config=tenant_config,
                owui_client=per_user_client,
                timing=timing,
            )
            if chat:
                store_chat_mapping(info["email"], request.chat_id, chat["chat_id"])
        return per_user_client, chat

    # Serialize the full provisioning-and-chat-creation flow for the same
    # client so two near-simultaneous messages can't race into duplicate chat
    # creation or duplicate provisioning. Different (client_phone, tenant_id)
    # pairs get different locks, so unrelated clients never block each other.
    lock = _get_user_lock(request.client_phone, request.tenant_id)
    with lock:
        user_info = _provision()
        if not user_info:
            raise HTTPException(status_code=500, detail="User provisioning failed")

        try:
            per_user_client, chat = _run_chat(user_info)
        except AuthExpiredError:
            # Cached token was stale: re-authenticate once and retry (transparent to caller).
            logger.info("OWUI token rejected mid-request — re-authenticating and retrying once")
            user_info = _provision(force=True)
            if not user_info:
                raise HTTPException(status_code=500, detail="User provisioning failed")
            per_user_client, chat = _run_chat(user_info)

    if not chat:
        raise HTTPException(status_code=500, detail="Chat creation failed")

    sales_text = chat.get("assistant_response", "")
    if not sales_text:
        logger.warning("Returning empty assistant_response for chat %s", chat["chat_id"])

    timing.round_trips = per_user_client.round_trips
    timing.emit(chat_id=chat["chat_id"], user_id=user_info["user_id"])

    return ChatResponse(
        assistant_response=sales_text,
        chat_id=chat["chat_id"],
        user_id=user_info["user_id"],
        assistant_id=assistant_id,
        tenant_id=request.tenant_id,
        timestamp=datetime.utcnow().isoformat() + "Z",
        follow_ups=chat.get("follow_ups", []),
    )
