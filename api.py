"""FastAPI entry point for the OWUI Agent Proxy.
Provides the POST /proxy/chat endpoint as defined in the contract.
"""
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import threading

from src.services.tenant_routing import resolve_assistant, resolve_tenant_config
from src.services.user_provisioning import provision_user, get_owui_chat_id, store_chat_mapping
from src.services.chat_management import get_or_create_chat, continue_chat, run_formatter, text_fallback
from src.client.openwebui_client import AuthExpiredError, OpenWebUIClient
from src.utils.logger import logger
from src.utils.timing import RequestTiming

app = FastAPI()
client = OpenWebUIClient()
_user_locks: dict = {}
_user_locks_lock = threading.Lock()


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
    assistant_response: dict
    chat_id: str
    user_id: str
    assistant_id: str
    tenant_id: str
    timestamp: str
    follow_ups: list[str] = []


@app.post("/proxy/chat", response_model=ChatResponse)
async def proxy_chat(request: ChatRequest):
    timing = RequestTiming()
    lock = _get_user_lock(request.client_phone, request.tenant_id)
    with lock:
        logger.info("Received proxy chat request for client %s tenant %s", request.client_phone, request.tenant_id)

    assistant_id = resolve_assistant(request.tenant_id)
    if not assistant_id:
        raise HTTPException(status_code=404, detail="Unknown tenant mapping")

    tenant_config = resolve_tenant_config(request.tenant_id)

    def _provision(force: bool = False):
        with timing.phase("provision_ms"):
            return provision_user(request.client_phone, request.tenant_id, owui_client=client, force=force)

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
                owui_chat_id, request.message, assistant_id,
                owui_client=per_user_client, tenant_config=tenant_config, timing=timing,
            )
            if not chat:
                logger.warning("continue_chat failed for owui_id %s — falling back to new chat", owui_chat_id)
        if not owui_chat_id or chat is None:
            chat = get_or_create_chat(
                info["user_id"], assistant_id, request.message,
                tenant_config=tenant_config, owui_client=per_user_client, timing=timing,
            )
            if chat:
                store_chat_mapping(info["email"], request.chat_id, chat["chat_id"])
        return per_user_client, chat

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

    # Second pass: hand the sales agent's text to the global formatter agent,
    # which structures it for WhatsApp. Degrade to a plain text object on failure.
    structured = run_formatter(sales_text, user_info["user_id"], per_user_client, timing)
    if structured is None:
        structured = text_fallback(sales_text)

    timing.round_trips = per_user_client.round_trips
    timing.emit(chat_id=chat["chat_id"], user_id=user_info["user_id"])

    return ChatResponse(
        assistant_response=structured,
        chat_id=chat["chat_id"],
        user_id=user_info["user_id"],
        assistant_id=assistant_id,
        tenant_id=request.tenant_id,
        timestamp=datetime.utcnow().isoformat() + "Z",
        follow_ups=chat.get("follow_ups", []),
    )