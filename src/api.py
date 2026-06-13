"""FastAPI entry point for the OWUI Agent Proxy.
Provides the POST /proxy/chat endpoint as defined in the contract.
"""
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import threading

from src.services.tenant_routing import resolve_assistant, resolve_tenant_config
from src.services.user_provisioning import provision_user, update_cached_chat_id
from src.services.chat_management import get_or_create_chat, continue_chat
from src.client.openwebui_client import OpenWebUIClient
from src.utils.logger import logger

app = FastAPI()
client = OpenWebUIClient()
_user_locks: dict = {}
_user_locks_lock = threading.Lock()


def _get_user_lock(username: str, tenant_id: str) -> threading.Lock:
    key = f"{username}:{tenant_id}"
    with _user_locks_lock:
        if key not in _user_locks:
            _user_locks[key] = threading.Lock()
        return _user_locks[key]


class ChatRequest(BaseModel):
    username: str
    tenant_id: str
    message: str
    chat_id: Optional[str] = None


class ChatResponse(BaseModel):
    assistant_response: str
    chat_id: str
    user_id: str
    assistant_id: str
    tenant_id: str
    timestamp: str
    follow_ups: list[str] = []


@app.post("/proxy/chat", response_model=ChatResponse)
async def proxy_chat(request: ChatRequest):
    lock = _get_user_lock(request.username, request.tenant_id)
    with lock:
        logger.info("Received proxy chat request for user %s tenant %s", request.username, request.tenant_id)

    assistant_id = resolve_assistant(request.tenant_id)
    if not assistant_id:
        raise HTTPException(status_code=404, detail="Unknown tenant mapping")

    tenant_config = resolve_tenant_config(request.tenant_id)

    user_info = provision_user(request.username, request.tenant_id, owui_client=client)
    if not user_info:
        raise HTTPException(status_code=500, detail="User provisioning failed")

    per_user_client = client.with_token(user_info["token"])

    # Priority: explicit request.chat_id > stored chat_id from cache > new chat.
    # On is_new_session (token refresh) always start fresh regardless of cache.
    if user_info.get("is_new_session"):
        effective_chat_id = None
    else:
        effective_chat_id = request.chat_id or user_info.get("chat_id")

    if effective_chat_id:
        chat = continue_chat(
            effective_chat_id, request.message, assistant_id,
            owui_client=per_user_client, tenant_config=tenant_config,
        )
        if not chat:
            logger.warning("continue_chat failed for %s — falling back to new chat", effective_chat_id)
            update_cached_chat_id(user_info["email"], None)
            chat = None  # fall through to get_or_create_chat below
    if not effective_chat_id or chat is None:
        chat = get_or_create_chat(
            user_info["user_id"], assistant_id, request.message,
            tenant_config=tenant_config, owui_client=per_user_client,
        )
        if not chat:
            raise HTTPException(status_code=500, detail="Chat creation failed")

    update_cached_chat_id(user_info["email"], chat["chat_id"])

    assistant_response = chat.get("assistant_response", "")
    if not assistant_response:
        logger.warning("Returning empty assistant_response for chat %s", chat["chat_id"])

    return ChatResponse(
        assistant_response=assistant_response,
        chat_id=chat["chat_id"],
        user_id=user_info["user_id"],
        assistant_id=assistant_id,
        tenant_id=request.tenant_id,
        timestamp=datetime.utcnow().isoformat() + "Z",
        follow_ups=chat.get("follow_ups", []),
    )
