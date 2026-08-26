"""Chat management service.

Stateless — all chat data lives in Open WebUI. No local caches or registries.

Tools run on the Open WebUI side. The proxy replicates the OWUI frontend:
- It POSTs /api/chat/completions with ``stream: true`` + ``user_message`` + the
  assistant message ``id`` + ``parent_id`` (+ ``chat_id`` when continuing) and a
  ``session_id`` taken from a live socket connection. OWUI then OWNS the chat:
  it creates/links the graph (parentId/childrenIds), runs the model's attached
  ``server:0`` tools server-side, and persists the assistant message.
- That call is asynchronous (returns ``{chat_id, task_id}``); the real answer is
  pushed over socket.io. The proxy connects as a socket client and waits for the
  assistant message's ``chat:completion`` ``done`` event.

See specs/005-reduce-api-latency/research.md (Finding 3) and src/client/owui_socket.py.
"""
from typing import Dict, Optional
from contextlib import nullcontext
import uuid
import time
import re

from src.client.openwebui_client import AuthExpiredError, OpenWebUIClient
from src.client.owui_socket import await_completion
from src.services.tenant_routing import TenantConfig
from src.utils.logger import logger
from src.utils.timing import RequestTiming

_DETAILS_BLOCK_RE = re.compile(r'<details[^>]*>.*?</details>', re.DOTALL)

# Max time to wait for OWUI's async (socket-delivered) completion.
_RESULT_TIMEOUT_S = 180


def _strip_details_blocks(content: str) -> str:
    """Remove OWUI tool-trace <details> blocks for the widget-facing answer."""
    return _DETAILS_BLOCK_RE.sub('', content).strip()


def _rest_content_fallback(c: OpenWebUIClient, chat_id: str) -> str:
    """Fetch the last assistant message via REST when the socket delivered no content.

    Reuses the existing get_chat + _walk_history_chain path already used by
    continue_chat. Raises on HTTP/network errors so callers can log and degrade.
    """
    fallback_chat = c.get_chat(chat_id)
    fallback_inner = c._chat_inner(fallback_chat)
    fallback_history = fallback_inner.get("history", {}) or {}
    fallback_messages = fallback_history.get("messages", {}) or {}
    tip_id = fallback_history.get("currentId") or fallback_history.get("current_id")
    if tip_id:
        chain = _walk_history_chain(fallback_messages, tip_id)
        assistant_msgs = [m["content"] for m in chain if m["role"] == "assistant" and m["content"]]
        if assistant_msgs:
            return assistant_msgs[-1]
    return ""


def _bearer(c: OpenWebUIClient) -> str:
    h = c.session.headers.get("Authorization", "") or ""
    return h[len("Bearer "):] if h.startswith("Bearer ") else h


def _walk_history_chain(history_messages: dict, tip_id: str) -> list:
    chain = []
    visited: set = set()
    node_id = tip_id
    while node_id and node_id not in visited:
        visited.add(node_id)
        msg = history_messages.get(node_id)
        if not msg:
            break
        chain.append(msg)
        node_id = msg.get("parentId")
    chain.reverse()
    result = []
    for m in chain:
        if m.get("role") not in ("user", "assistant"):
            continue
        content = m.get("content", "")
        if m["role"] == "assistant":
            content = _strip_details_blocks(content)
        if content:
            result.append({"role": m["role"], "content": content})
    return result


def _completion_payload(
    model: str,
    messages: list,
    chat_id: Optional[str],
    parent_id: Optional[str],
    user_message: dict,
    assistant_msg_id: str,
    session_id: Optional[str],
    tool_ids: Optional[list],
    title_generation_enabled: bool = True,
) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,  # required: OWUI only runs the tool loop in its streaming handler
        "id": assistant_msg_id,
        "parent_id": parent_id,
        "user_message": user_message,
        "session_id": session_id,
        "tool_ids": tool_ids or [],
        "features": {
            "code_interpreter": False,
            "web_search": True,
            "image_generation": False,
            "memory": False,
        },
        "background_tasks": {
            "title_generation": title_generation_enabled and bool(parent_id is None and not chat_id),
            "tags_generation": False,
            "follow_up_generation": False,
        },
    }
    if chat_id:
        payload["chat_id"] = chat_id
    return payload


# ---------------------------------------------------------------------------
# Chat lifecycle
# ---------------------------------------------------------------------------

def get_or_create_chat(
    user_id: str,
    assistant_id: str,
    message_content: str = "",
    tenant_config: Optional[TenantConfig] = None,
    owui_client: Optional[OpenWebUIClient] = None,
    timing: Optional[RequestTiming] = None,
) -> Optional[Dict[str, str]]:
    """Start a new chat. OWUI creates+links it, runs tools, and persists."""
    c = owui_client
    try:
        now_s = int(time.time())
        user_msg_id = str(uuid.uuid4())
        assistant_msg_id = str(uuid.uuid4())
        model = (tenant_config or {}).get("model", assistant_id)
        tool_ids = (tenant_config or {}).get("tool_ids")
        title_generation_enabled = (tenant_config or {}).get("title_generation", True)

        user_message = {
            "id": user_msg_id,
            "parentId": None,
            "childrenIds": [],
            "role": "user",
            "content": message_content,
            "timestamp": now_s,
            "models": [model],
        }

        def trigger(session_id):
            payload = _completion_payload(
                model, [{"role": "user", "content": message_content}],
                chat_id=None, parent_id=None, user_message=user_message,
                assistant_msg_id=assistant_msg_id, session_id=session_id, tool_ids=tool_ids,
                title_generation_enabled=title_generation_enabled,
            )
            return c.chat_completion(payload)

        def run():
            return await_completion(c.base_url, _bearer(c), assistant_msg_id, trigger, _RESULT_TIMEOUT_S)

        if timing is not None:
            with timing.phase("completion_ms"):
                chat_id, content, output = run()
        else:
            chat_id, content, output = run()

        if not chat_id:
            logger.error("OWUI completion did not return a chat_id")
            return None

        if not content:
            logger.warning("socket returned empty content for chat %s — trying REST fallback", chat_id)
            try:
                content = _rest_content_fallback(c, chat_id)
            except Exception as exc:
                logger.error("REST fallback for chat %s failed: %s", chat_id, exc)
            if not content:
                logger.error("socket and REST fallback both returned no content for chat %s", chat_id)

        logger.info("Created chat %s for user %s", chat_id, user_id)
        return {
            "chat_id": chat_id,
            "assistant_id": assistant_id,
            "last_message_id": assistant_msg_id,
            "assistant_response": _strip_details_blocks(content),
            "output": output,
            "follow_ups": [],
        }
    except AuthExpiredError:
        raise
    except Exception as exc:
        logger.error("Failed to create chat: %s", exc)
        return None


def continue_chat(
    chat_id: str,
    message_content: str,
    assistant_id: str,
    owui_client: Optional[OpenWebUIClient] = None,
    tenant_config: Optional[TenantConfig] = None,
    timing: Optional[RequestTiming] = None,
) -> Optional[Dict[str, str]]:
    """Continue an existing chat. OWUI appends+links, runs tools, and persists."""
    c = owui_client
    try:
        now_s = int(time.time())
        new_user_msg_id = str(uuid.uuid4())
        assistant_msg_id = str(uuid.uuid4())
        model = assistant_id
        tool_ids = (tenant_config or {}).get("tool_ids")

        try:
            # Single get_chat call, timed only when a RequestTiming is provided
            # (nullcontext keeps the un-timed path behavior-identical).
            persist_phase = timing.phase("persist_ms") if timing is not None else nullcontext()
            with persist_phase:
                current_chat = c.get_chat(chat_id)
        except AuthExpiredError:
            # OWUI returns 401 for chats that don't exist or that the user can't
            # access — indistinguishable from an expired token at the HTTP level.
            # Return None so the caller falls back to creating a new chat.
            logger.warning("Chat %s not accessible (OWUI 401) — falling back to new chat", chat_id)
            return None
        current_inner = c._chat_inner(current_chat)
        current_history = current_inner.get("history", {}) or {}
        history_messages = current_history.get("messages", {}) or {}
        last_id = current_history.get("currentId") or current_history.get("current_id")
        if not last_id:
            logger.error("Chat %s has no currentId in history", chat_id)
            return None

        completion_msgs = _walk_history_chain(history_messages, last_id)
        completion_msgs.append({"role": "user", "content": message_content})

        user_message = {
            "id": new_user_msg_id,
            "parentId": last_id,
            "childrenIds": [],
            "role": "user",
            "content": message_content,
            "timestamp": now_s,
            "models": [model],
        }

        def trigger(session_id):
            payload = _completion_payload(
                model, completion_msgs,
                chat_id=chat_id, parent_id=last_id, user_message=user_message,
                assistant_msg_id=assistant_msg_id, session_id=session_id, tool_ids=tool_ids,
            )
            return c.chat_completion(payload)

        def run():
            return await_completion(c.base_url, _bearer(c), assistant_msg_id, trigger, _RESULT_TIMEOUT_S)

        if timing is not None:
            with timing.phase("completion_ms"):
                _chat_id, content, output = run()
        else:
            _chat_id, content, output = run()

        if not content:
            logger.warning("socket returned empty content for chat %s — trying REST fallback", chat_id)
            try:
                content = _rest_content_fallback(c, chat_id)
            except Exception as exc:
                logger.error("REST fallback for chat %s failed: %s", chat_id, exc)
            if not content:
                logger.error("socket and REST fallback both returned no content for chat %s", chat_id)

        return {
            "chat_id": chat_id,
            "assistant_id": assistant_id,
            "last_message_id": assistant_msg_id,
            "assistant_response": _strip_details_blocks(content),
            "output": output,
            "follow_ups": [],
        }
    except AuthExpiredError:
        raise
    except Exception as exc:
        logger.error("Failed to continue chat %s: %s", chat_id, exc)
        return None
