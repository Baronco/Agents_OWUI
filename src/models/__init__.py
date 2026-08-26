"""Data model entities for the OWUI Agent Proxy.
Only lightweight definitions; actual persistence handled elsewhere.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class UserIdentity:
    username: str
    tenant_id: str
    openwebui_user_id: Optional[str] = None
    email: str = ""
    password: str = ""
    assistant_id: Optional[str] = None
    created_at: datetime = datetime.utcnow()

@dataclass
class OpenWebUIUser:
    user_id: str
    username: str
    email: str
    password: str
    is_admin: bool = False

@dataclass
class ChatSession:
    chat_id: str
    tenant_id: str
    user_identity: UserIdentity
    assistant_id: str
    status: str = "active"
    created_at: datetime = datetime.utcnow()
    updated_at: datetime = datetime.utcnow()

@dataclass
class ConversationMessage:
    message_id: Optional[str]
    chat_id: str
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = datetime.utcnow()

from typing import TypedDict

class TenantConfig(TypedDict, total=False):
    model: str
    tool_ids: list[str]
    system_prompt: str
