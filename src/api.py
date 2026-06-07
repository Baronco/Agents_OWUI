"""FastAPI entry point for the OWUI Agent Proxy.
Provides the POST /proxy/chat endpoint as defined in the contract.
"""
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

from src.services.tenant_routing import resolve_assistant, resolve_tenant_config
from src.services.user_provisioning import provision_user
from src.services.chat_management import get_or_create_chat, continue_chat, persist_message
from src.client.openwebui_client import OpenWebUIClient
from src.utils.logger import logger

app = FastAPI()
client = OpenWebUIClient()

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
    logger.info("Received proxy chat request for user %s tenant %s", request.username, request.tenant_id)

    assistant_id = resolve_assistant(request.tenant_id)
    if not assistant_id:
        raise HTTPException(status_code=404, detail="Unknown tenant mapping")

    tenant_config = resolve_tenant_config(request.tenant_id)

    user_info = provision_user(request.username, request.tenant_id, owui_client=client)
    if not user_info:
        raise HTTPException(status_code=500, detail="User provisioning failed")

    if request.chat_id:
        chat = continue_chat(request.chat_id, request.message, assistant_id, owui_client=client)
        if not chat:
            raise HTTPException(status_code=500, detail="Chat continuation failed")
    else:
        chat = get_or_create_chat(user_info["user_id"], assistant_id, request.message, tenant_config=tenant_config, owui_client=client)
        if not chat:
            raise HTTPException(status_code=500, detail="Chat creation failed")

    persist_message(chat["chat_id"], "user", request.message)
    persist_message(chat["chat_id"], "assistant", chat.get("assistant_response", ""))

    return ChatResponse(
        assistant_response=chat.get("assistant_response", ""),
        chat_id=chat["chat_id"],
        user_id=user_info["user_id"],
        assistant_id=assistant_id,
        tenant_id=request.tenant_id,
        timestamp=datetime.utcnow().isoformat() + "Z",
        follow_ups=chat.get("follow_ups", []),
    )
