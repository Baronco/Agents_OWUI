"""Chat management service.
Handles creation and retrieval of chat sessions via the OpenWebUI backend API.
Implements the full backend-controlled flow described in:
https://github.com/open-webui/open-webui/discussions/11800
"""
from typing import Dict, Optional
import uuid
import time

from src.client.openwebui_client import OpenWebUIClient
from src.client.message_builder import build_completion_payload
from src.services.tenant_routing import TenantConfig
from src.utils.logger import logger

client = OpenWebUIClient()

# Simple in-memory store for demo; replace with DB as needed
_chat_store: Dict[str, Dict] = {}


def _resolve_client(owui_client: Optional[OpenWebUIClient] = None) -> OpenWebUIClient:
    """Return the passed client if provided, otherwise the module-level default."""
    return owui_client if owui_client is not None else client


def get_or_create_chat(
    user_id: str,
    assistant_id: str,
    message_content: str = "",
    tenant_config: Optional[TenantConfig] = None,
    owui_client: Optional[OpenWebUIClient] = None,
) -> Optional[Dict[str, str]]:
    """Return existing chat for the user if present, otherwise create a new one.

    The creation flow follows OpenWebUI's backend-controlled pattern:
    1. Create a new chat that already contains the initial user message.
    2. Inject an empty assistant placeholder message.
    3. Trigger the assistant completion.
    4. Mark the assistant reply as completed.

    Args:
        user_id: The Open WebUI user ID.
        assistant_id: The model/assistant name to use.
        message_content: The actual user message text to include in the chat.
        tenant_config: Optional TenantConfig with model, tools, system_prompt.
        owui_client: Optional OpenWebUIClient instance (with user-scoped bearer token).
    """
    c = _resolve_client(owui_client)

    # Check existing chat mapping
    for chat in _chat_store.values():
        if chat["user_id"] == user_id and chat["assistant_id"] == assistant_id:
            logger.info("Reusing existing chat %s", chat["chat_id"])
            return chat

    try:
        # --- 1. Generate IDs and timestamps ---
        now_ms = int(time.time() * 1000)
        user_msg_id = str(uuid.uuid4())
        assistant_msg_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        model = (tenant_config or {}).get("model", assistant_id)
        system_prompt = (tenant_config or {}).get("system_prompt", "")

        # --- 2. Build the initial user message with actual content ---
        messages = []
        history_messages = {}

        # Prepend system prompt if configured
        if system_prompt:
            system_msg = {
                "id": str(uuid.uuid4()),
                "role": "user",
                "content": system_prompt,
                "timestamp": now_ms,
                "models": [model],
            }
            messages.append(system_msg)
            history_messages[system_msg["id"]] = system_msg

        user_message = {
            "id": user_msg_id,
            "role": "user",
            "content": message_content,
            "timestamp": now_ms,
            "models": [model],
        }
        messages.append(user_message)
        history_messages[user_msg_id] = user_message

        # --- 3. Create chat with that initial user message ---
        resp = c.create_chat_with_initial_message(
            user_id=user_id,
            title="New Chat",
            model=model,
            user_message=user_message,
            additional_messages=messages,
            additional_history=history_messages,
        )
        chat_id = resp.get("chat_id") or resp.get("id")
        if not chat_id:
            logger.error("OpenWebUI create chat response missing ID: %s", resp)
            return None

        # --- 4. Build the empty assistant placeholder message ---
        assistant_message = {
            "id": assistant_msg_id,
            "role": "assistant",
            "content": "",
            "parentId": user_msg_id,
            "modelName": model,
            "modelIdx": 0,
            "timestamp": now_ms,
            "models": [model],
        }

        c.inject_assistant_message(chat_id, assistant_message)

        # --- 5. Trigger assistant reply with proper payload ---
        payload = build_completion_payload(
            chat_id=chat_id,
            assistant_msg_id=assistant_msg_id,
            message_content=message_content,
            model=model,
            session_id=session_id,
        )
        tool_ids = (tenant_config or {}).get("tool_ids")
        completion_resp = _process_completion_with_tools(
            chat_id=chat_id,
            assistant_msg_id=assistant_msg_id,
            initial_payload=payload,
            session_id=session_id,
            model=model,
            tool_ids=tool_ids,
            owui_client=c,
        )
        assistant_text = _extract_assistant_text(completion_resp)
        follow_ups = _extract_follow_ups(completion_resp)

        # --- 6. Mark completion ---
        c.complete_chat(
            chat_id=chat_id,
            assistant_msg_id=assistant_msg_id,
            session_id=session_id,
            model=model,
        )

        # --- 7. Store locally and return ---
        chat = {
            "chat_id": chat_id,
            "user_id": user_id,
            "assistant_id": assistant_id,
            "session_id": session_id,
            "last_message_id": assistant_msg_id,
            "assistant_response": assistant_text,
            "follow_ups": follow_ups,
        }
        _chat_store[chat_id] = chat
        logger.info(
            "Created new chat %s for user %s with assistant_id %s", chat_id, user_id, assistant_id
        )
        return chat

    except Exception as exc:
        logger.error("Failed to create chat: %s", exc)
        return None


def continue_chat(
    chat_id: str,
    message_content: str,
    assistant_id: str,
    owui_client: Optional[OpenWebUIClient] = None,
) -> Optional[Dict[str, str]]:
    """Append a new user message to an existing chat and trigger a new assistant reply.

    Implements multi-turn flow:
    1. Retrieve existing chat state from local store.
    2. Append the new user message with parentId set to the last assistant message.
    3. Inject a new empty assistant placeholder.
    4. Trigger completion with full history.
    5. Mark completed.
    """
    c = _resolve_client(owui_client)
    existing = _chat_store.get(chat_id)
    if not existing:
        logger.error("Chat %s not found in local store", chat_id)
        return None

    try:
        now_ms = int(time.time() * 1000)
        new_user_msg_id = str(uuid.uuid4())
        new_assistant_msg_id = str(uuid.uuid4())
        session_id = existing.get("session_id", str(uuid.uuid4()))
        model = assistant_id

        # Get the current chat from OWUI
        current_chat = c.get_chat(chat_id)

        # Build the new user message
        new_user_message = {
            "id": new_user_msg_id,
            "role": "user",
            "content": message_content,
            "parentId": existing.get("last_message_id"),
            "timestamp": now_ms,
            "models": [model],
        }

        # Append to both messages[] and history.messages{}
        current_chat.setdefault("messages", []).append(new_user_message)
        current_chat.setdefault("history", {}).setdefault("messages", {})[new_user_msg_id] = new_user_message
        current_chat["history"]["current_id"] = new_user_msg_id

        # Push updated chat back
        c._post(f"/api/v1/chats/{chat_id}", current_chat)

        # Inject new empty assistant message
        new_assistant_message = {
            "id": new_assistant_msg_id,
            "role": "assistant",
            "content": "",
            "parentId": new_user_msg_id,
            "modelName": model,
            "modelIdx": 0,
            "timestamp": now_ms,
            "models": [model],
        }
        c.inject_assistant_message(chat_id, new_assistant_message)

        # Trigger completion with full history
        all_messages = []
        if "history" in current_chat and "messages" in current_chat["history"]:
            for msg_id, msg in current_chat["history"]["messages"].items():
                all_messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

        payload = build_completion_payload(
            chat_id=chat_id,
            assistant_msg_id=new_assistant_msg_id,
            message_content=message_content,
            model=model,
            session_id=session_id,
        )
        # Replace the single-message messages with full history
        payload["messages"] = all_messages

        completion_resp = _process_completion_with_tools(
            chat_id=chat_id,
            assistant_msg_id=new_assistant_msg_id,
            initial_payload=payload,
            session_id=session_id,
            model=model,
            owui_client=c,
        )

        # Mark completed
        c.complete_chat(
            chat_id=chat_id,
            assistant_msg_id=new_assistant_msg_id,
            session_id=session_id,
            model=model,
        )

        assistant_text = _extract_assistant_text(completion_resp)
        follow_ups = _extract_follow_ups(completion_resp)

        # Update local store
        existing["last_message_id"] = new_assistant_msg_id
        existing["session_id"] = session_id
        existing["assistant_response"] = assistant_text
        existing["follow_ups"] = follow_ups

        return existing

    except Exception as exc:
        logger.error("Failed to continue chat %s: %s", chat_id, exc)
        return None


def persist_message(chat_id: str, role: str, content: str) -> None:
    """Persist a message; placeholder that could store in SQLite.
    Currently just logs the operation.
    """
    logger.info("Persisting %s message for chat %s", role, chat_id)


def _extract_assistant_text(completion_resp: dict) -> str:
    """Extract the assistant text from a chat completion response."""
    if "choices" in completion_resp and len(completion_resp["choices"]) > 0:
        return completion_resp["choices"][0].get("message", {}).get("content", "")
    if "message" in completion_resp:
        return completion_resp["message"].get("content", "")
    return ""


def _extract_follow_ups(completion_resp: dict) -> list:
    """Extract follow-up questions from a chat completion response."""
    return completion_resp.get("followUps", [])


def _extract_tool_calls(completion_resp: dict) -> list:
    """Extract tool_calls from a chat completion response."""
    if "choices" in completion_resp and len(completion_resp["choices"]) > 0:
        return completion_resp["choices"][0].get("message", {}).get("tool_calls", [])
    return []


def _execute_tool(tool_name: str, arguments: dict) -> str:
    """Execute a tool via the ecommerce API and return the result as JSON string."""
    import os, json, requests

    ecommerce_base = os.getenv("ECOMMERCE_BASE_URL", "https://api-development-5d8c.up.railway.app")
    ecommerce_key = os.getenv("ECOMMERCE_API_KEY", "")

    tool_map = {
        "search_catalog": ("POST", "/v1/catalog/search", "body"),
        "list_catalog_products": ("GET", "/v1/catalog/products", "query"),
        "get_catalog_product": ("GET", "/v1/catalog/products/{product_id}", "path+query"),
        "lookup_catalog_inventory": ("POST", "/v1/catalog/inventory-lookup", "body"),
        "compare_catalog_products": ("POST", "/v1/catalog/comparisons", "body"),
        "suggest_cross_sell_products": ("POST", "/v1/catalog/cross-sell-suggestions", "body"),
    }

    if tool_name not in tool_map:
        return json.dumps({"error": f"Tool '{tool_name}' not registered"}, ensure_ascii=False)

    method, path_template, _ = tool_map[tool_name]
    path = path_template
    for key in list(arguments.keys()):
        placeholder = f"{{{key}}}"
        if placeholder in path_template:
            path = path.replace(placeholder, str(arguments[key]))
            arguments.pop(key)

    url = f"{ecommerce_base}{path}"
    headers = {
        "Authorization": f"Bearer {ecommerce_key}",
        "Content-Type": "application/json",
    }

    try:
        if method == "GET":
            resp = requests.get(url, params=arguments, headers=headers, timeout=15)
        else:
            resp = requests.post(url, json=arguments, headers=headers, timeout=15)
        resp.raise_for_status()
        return json.dumps(resp.json(), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _process_completion_with_tools(
    chat_id: str,
    assistant_msg_id: str,
    initial_payload: dict,
    session_id: str,
    model: str,
    tool_ids: Optional[list] = None,
    owui_client: Optional[OpenWebUIClient] = None,
) -> dict:
    """Send a completion request and handle any tool_calls in the response.
    Returns the final completion response after all tool calls are resolved.
    """
    c = _resolve_client(owui_client)
    payload = dict(initial_payload)
    max_iterations = 8

    for iteration in range(max_iterations):
        if tool_ids:
            payload["tool_ids"] = tool_ids
        resp = c.chat_completion(payload)

        tool_calls = _extract_tool_calls(resp)
        if not tool_calls:
            return resp

        # Process each tool call
        assistant_msg = resp.get("choices", [{}])[0].get("message", {})
        payload["messages"].append({
            "role": "assistant",
            "content": assistant_msg.get("content"),
            "tool_calls": tool_calls,
        })

        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            import json
            tool_args = json.loads(tc["function"]["arguments"])
            logger.info("Executing tool: %s with args: %s", tool_name, tool_args)
            tool_result = _execute_tool(tool_name, tool_args)
            payload["messages"].append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": tool_result,
            })

    return resp