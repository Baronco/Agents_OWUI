"""Chat management service.
Handles creation and retrieval of chat sessions via the OpenWebUI backend API.
"""
from typing import Dict, Optional
import uuid
import time
import json as _json
import html as _html
import os

import re
import requests

from src.client.openwebui_client import OpenWebUIClient
from src.services.tenant_routing import TenantConfig
from src.utils.logger import logger

_FUNC_LAUNCH_RE = re.compile(r'<function_launch>(.*?)</function_launch>', re.DOTALL)
_DETAILS_BLOCK_RE = re.compile(r'<details[^>]*>.*?</details>', re.DOTALL)


def _parse_function_launches(content: str) -> list:
    """Extract (name, args_dict) pairs from <function_launch> XML blocks."""
    results = []
    for block in _FUNC_LAUNCH_RE.finditer(content):
        inner = block.group(1)
        name_match = re.search(r'<function_name>\s*(.*?)\s*</function_name>', inner, re.DOTALL)
        params_match = re.search(r'<parameters>\s*(.*?)\s*</parameters>', inner, re.DOTALL)
        if not name_match:
            continue
        name = name_match.group(1).strip()
        try:
            args = _json.loads(params_match.group(1).strip()) if params_match else {}
        except Exception:
            args = {}
        results.append((name, args))
    return results


def _strip_function_launches(content: str) -> str:
    """Remove <function_launch> XML blocks from content."""
    return _FUNC_LAUNCH_RE.sub('', content).strip()


def _strip_details_blocks(content: str) -> str:
    """Remove <details type="tool_calls"> HTML blocks from content."""
    return _DETAILS_BLOCK_RE.sub('', content).strip()


client = OpenWebUIClient()

_chat_store: Dict[str, Dict] = {}
_daily_chat_registry: Dict[str, str] = {}


def _daily_key(username: str, tenant_id: str) -> str:
    from datetime import date
    return f"{username}:{tenant_id}:{date.today().isoformat()}"


def resolve_daily_chat_id(username: str, tenant_id: str) -> Optional[str]:
    return _daily_chat_registry.get(_daily_key(username, tenant_id))


def register_daily_chat(username: str, tenant_id: str, chat_id: str) -> None:
    _daily_chat_registry[_daily_key(username, tenant_id)] = chat_id


def _resolve_client(owui_client: Optional[OpenWebUIClient] = None) -> OpenWebUIClient:
    return owui_client if owui_client is not None else client


# ---------------------------------------------------------------------------
# Tool execution + direct completion loop
# ---------------------------------------------------------------------------

def _execute_tool(tool_name: str, arguments: dict) -> str:
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
        return _json.dumps({"error": f"Tool '{tool_name}' not registered"}, ensure_ascii=False)
    method, path_template, _ = tool_map[tool_name]
    path = path_template
    for key in list(arguments.keys()):
        if f"{{{key}}}" in path_template:
            path = path.replace(f"{{{key}}}", str(arguments[key]))
            arguments.pop(key)
    url = f"{ecommerce_base}{path}"
    headers = {"Authorization": f"Bearer {ecommerce_key}", "Content-Type": "application/json"}
    try:
        if method == "GET":
            resp = requests.get(url, params=arguments, headers=headers, timeout=15)
        else:
            resp = requests.post(url, json=arguments, headers=headers, timeout=15)
        resp.raise_for_status()
        return _json.dumps(resp.json(), ensure_ascii=False)
    except Exception as e:
        return _json.dumps({"error": str(e)}, ensure_ascii=False)


def _build_tool_response(final_text: str, tool_trace: list) -> tuple:
    """Build OWUI-format content string and output array from accumulated tool trace.

    Returns (content, output_list).  If tool_trace is empty returns (final_text, []).
    tool_trace entries: {"call_id": str, "name": str, "args": dict, "result": str}
    """
    if not tool_trace:
        return final_text, []

    details_parts = []
    output = []

    for entry in tool_trace:
        call_id = entry["call_id"]
        name    = entry["name"]
        args    = entry["args"]    # dict
        result  = entry["result"]  # JSON string from _execute_tool

        args_json  = _json.dumps(args)
        # Wrap in outer quotes then HTML-escape → reproduces &quot;{...}&quot; format
        args_attr  = _html.escape(f'"{args_json}"')
        body_inner = _html.escape(f'"{result}"')

        details_parts.append(
            f'<details type="tool_calls" done="true"'
            f' id="{call_id}" name="{name}"'
            f' arguments="{args_attr}" files="" embeds="&quot;&quot;">\n'
            f'<summary>Tool Executed</summary>\n'
            f'{body_inner}\n'
            f'</details>'
        )
        output.append({
            "type": "function_call",
            "id": call_id,
            "call_id": call_id,
            "name": name,
            "arguments": args_json,
            "status": "completed",
        })
        output.append({
            "type": "function_call_output",
            "id": f"fco_{uuid.uuid4().hex[:24]}",
            "call_id": call_id,
            "output": [{"type": "input_text", "text": result}],
            "status": "completed",
        })

    output.append({
        "type": "message",
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "text": final_text}],
    })

    content = "\n".join(details_parts)
    if final_text:
        content += "\n" + final_text
    return content, output


def _resolve_assistant_response(
    owui_client: OpenWebUIClient,
    model: str,
    user_message_content: str,
    tool_ids: Optional[list] = None,
    history_msgs: Optional[list] = None,
) -> tuple:
    messages = list(history_msgs) if history_msgs else [{"role": "user", "content": user_message_content}]
    tool_trace: list = []
    for iteration in range(10):
        logger.info("Direct completion iteration %d", iteration + 1)
        payload = {"model": model, "messages": messages}
        if tool_ids:
            payload["tool_ids"] = tool_ids
        url = f"{owui_client.base_url}/api/chat/completions"
        resp = requests.post(url, headers=dict(owui_client.session.headers), json=payload, timeout=120)
        resp.raise_for_status()
        result = resp.json()
        if "choices" not in result or not result["choices"]:
            logger.warning("Direct completion returned no choices: %s", list(result.keys()))
            continue
        choice = result["choices"][0]
        finish = choice.get("finish_reason")
        message = choice.get("message", {})
        logger.info("Direct iteration %d: finish_reason=%s", iteration + 1, finish)
        if finish == "stop":
            content = message.get("content", "")
            # Some models return XML-style tool calls with finish_reason "stop"
            # instead of using structured tool_calls. Detect and execute them.
            xml_calls = _parse_function_launches(content)
            if xml_calls:
                logger.info("Detected %d XML-style tool call(s) in stop response", len(xml_calls))
                messages.append({"role": "assistant", "content": content})
                for tool_name, tool_args in xml_calls:
                    call_id = f"call_{uuid.uuid4().hex[:24]}"
                    logger.info("Executing XML-style tool: %s args: %s", tool_name, tool_args)
                    tool_result = _execute_tool(tool_name, tool_args)
                    tool_trace.append({
                        "call_id": call_id,
                        "name": tool_name,
                        "args": tool_args,
                        "result": tool_result,
                    })
                    messages.append({
                        "role": "user",
                        "content": (
                            f"<function_results>\n"
                            f"<function_name>{tool_name}</function_name>\n"
                            f"<result>\n{tool_result}\n</result>\n"
                            f"</function_results>"
                        ),
                    })
                continue
            logger.info("Direct completion finished. Content length: %d", len(content))
            return _build_tool_response(content, tool_trace)
        if finish == "tool_calls":
            tool_calls = message.get("tool_calls", [])
            messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": tool_calls})
            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                tool_args = _json.loads(tc["function"]["arguments"])
                logger.info("Executing tool: %s with args: %s", tool_name, tool_args)
                tool_result = _execute_tool(tool_name, tool_args)
                tool_trace.append({
                    "call_id": tc["id"],
                    "name": tool_name,
                    "args": tool_args,
                    "result": tool_result,
                })
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": tool_result})
            continue
        content = message.get("content", "")
        if content:
            logger.warning("Unexpected finish_reason=%s, returning content (len=%d)", finish, len(content))
            return _build_tool_response(content, tool_trace)
        if "content" in choice:
            return _build_tool_response(choice.get("content", ""), tool_trace)
    logger.warning("Max direct completion iterations reached")
    return _build_tool_response("", tool_trace)


# ---------------------------------------------------------------------------
# History chain walker
# ---------------------------------------------------------------------------

def _walk_history_chain(history_messages: dict, tip_id: str) -> list:
    """Walk parent chain from tip_id to root, return conversation messages in order."""
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
            # Strip both XML tool call format and HTML <details> blocks so the
            # model sees clean text when building continuation context.
            content = _strip_details_blocks(_strip_function_launches(content))
        if content:
            result.append({"role": m["role"], "content": content})
    return result


# ---------------------------------------------------------------------------
# Chat lifecycle
# ---------------------------------------------------------------------------

def get_or_create_chat(
    user_id: str,
    assistant_id: str,
    message_content: str = "",
    tenant_config: Optional[TenantConfig] = None,
    owui_client: Optional[OpenWebUIClient] = None,
) -> Optional[Dict[str, str]]:
    c = _resolve_client(owui_client)
    for chat in _chat_store.values():
        if chat["user_id"] == user_id and chat["assistant_id"] == assistant_id:
            logger.info("Reusing existing chat %s", chat["chat_id"])
            return chat
    try:
        now = int(time.time())
        user_msg_id = str(uuid.uuid4())
        assistant_msg_id = str(uuid.uuid4())
        model = (tenant_config or {}).get("model", assistant_id)
        tool_ids = (tenant_config or {}).get("tool_ids")

        # Get completion FIRST — no empty placeholder messages
        completion_msgs = [{"role": "user", "content": message_content}]
        assistant_content, tool_output = _resolve_assistant_response(
            c, model, message_content, tool_ids, completion_msgs
        )
        # Plain text (no HTML) for the API response
        assistant_text_plain = _strip_details_blocks(assistant_content)

        # Build complete message objects with proper parent/child chain
        user_message = {
            "id": user_msg_id,
            "parentId": None,
            "childrenIds": [assistant_msg_id],
            "role": "user",
            "content": message_content,
            "timestamp": now,
            "models": [model],
        }
        assistant_message = {
            "id": assistant_msg_id,
            "parentId": user_msg_id,
            "childrenIds": [],
            "role": "assistant",
            "content": assistant_content,  # includes <details> HTML when tools were used
            "timestamp": now,
            "models": [model],
            "done": True,
        }
        if tool_output:
            assistant_message["output"] = tool_output

        # Persist to OWUI with completed state — single POST, no subsequent patching
        title = (message_content[:60] + "…") if len(message_content) > 60 else message_content
        resp = c._post("/api/v1/chats/new", {
            "chat": {
                "title": title,
                "models": [model],
                "messages": [{"role": "user", "content": message_content}],
                "history": {
                    "currentId": assistant_msg_id,
                    "messages": {
                        user_msg_id: user_message,
                        assistant_msg_id: assistant_message,
                    },
                },
            }
        })
        chat_id = resp.get("chat_id") or resp.get("id")
        if not chat_id:
            logger.error("OWUI create chat response missing ID: %s", resp)
            return None

        chat = {
            "chat_id": chat_id,
            "user_id": user_id,
            "assistant_id": assistant_id,
            "last_message_id": assistant_msg_id,
            "assistant_response": assistant_text_plain,
            "follow_ups": [],
            "_messages": [user_message, assistant_message],
        }
        _chat_store[chat_id] = chat
        logger.info("Created chat %s for user %s", chat_id, user_id)
        return chat
    except Exception as exc:
        logger.error("Failed to create chat: %s", exc)
        return None


def continue_chat(
    chat_id: str,
    message_content: str,
    assistant_id: str,
    owui_client: Optional[OpenWebUIClient] = None,
    tenant_config: Optional[TenantConfig] = None,
) -> Optional[Dict[str, str]]:
    c = _resolve_client(owui_client)
    existing = _chat_store.get(chat_id)
    if not existing:
        logger.error("Chat %s not found in local store", chat_id)
        return None
    try:
        now = int(time.time())
        new_user_msg_id = str(uuid.uuid4())
        new_assistant_msg_id = str(uuid.uuid4())
        model = assistant_id
        tool_ids = (tenant_config or {}).get("tool_ids")

        # Fetch authoritative chat state from OWUI
        current_chat = c.get_chat(chat_id)
        current_inner = c._chat_inner(current_chat)
        current_history = current_inner.setdefault("history", {})
        history_messages = current_history.setdefault("messages", {})

        # Resolve the actual current tip from OWUI (may differ from our local store)
        current_last_id = (
            current_history.get("currentId")
            or current_history.get("current_id")
            or existing.get("last_message_id")
        )

        # Build completion context by walking the persisted chain
        completion_msgs = _walk_history_chain(history_messages, current_last_id)
        completion_msgs.append({"role": "user", "content": message_content})

        # Get completion before modifying chat state
        assistant_content, tool_output = _resolve_assistant_response(
            c, model, message_content, tool_ids=tool_ids, history_msgs=completion_msgs
        )
        assistant_text_plain = _strip_details_blocks(assistant_content)

        # Build new messages
        new_user_message = {
            "id": new_user_msg_id,
            "parentId": current_last_id,
            "childrenIds": [new_assistant_msg_id],
            "role": "user",
            "content": message_content,
            "timestamp": now,
            "models": [model],
        }
        new_assistant_message = {
            "id": new_assistant_msg_id,
            "parentId": new_user_msg_id,
            "childrenIds": [],
            "role": "assistant",
            "content": assistant_content,  # includes <details> HTML when tools were used
            "timestamp": now,
            "models": [model],
            "done": True,
        }
        if tool_output:
            new_assistant_message["output"] = tool_output

        # Extend the chain: last message → new user → new assistant
        if current_last_id and current_last_id in history_messages:
            prev = dict(history_messages[current_last_id])
            prev["childrenIds"] = [new_user_msg_id]
            history_messages[current_last_id] = prev
        history_messages[new_user_msg_id] = new_user_message
        history_messages[new_assistant_msg_id] = new_assistant_message
        current_history["currentId"] = new_assistant_msg_id
        current_history.pop("current_id", None)

        c._post(f"/api/v1/chats/{chat_id}", {"chat": current_inner})

        existing["last_message_id"] = new_assistant_msg_id
        existing["assistant_response"] = assistant_text_plain
        existing["follow_ups"] = []
        existing.setdefault("_messages", []).extend([new_user_message, new_assistant_message])
        return existing
    except Exception as exc:
        logger.error("Failed to continue chat %s: %s", chat_id, exc)
        return None


def persist_message(chat_id: str, role: str, content: str) -> None:
    logger.info("Persisting %s message for chat %s", role, chat_id)
