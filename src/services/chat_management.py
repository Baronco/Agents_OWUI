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
import uuid
import time
import re

import json

from src.client.openwebui_client import AuthExpiredError, OpenWebUIClient
from src.client.owui_socket import await_completion
from src.services.tenant_routing import TenantConfig, resolve_formatter_config
from src.utils.logger import logger
from src.utils.timing import RequestTiming

_DETAILS_BLOCK_RE = re.compile(r'<details[^>]*>.*?</details>', re.DOTALL)

# Wraps the sales agent's raw text before handing it to the formatter, so the
# formatter model can't mistake it for a user message to converse with (it's
# literal content to format, not a request). Also makes the boundaries of the
# text explicit, since it may itself contain markdown/code fences.
_FORMATTER_INPUT_TEMPLATE = (
    "El mensaje del usuario recibido para formatear usando la herramienta "
    "disponible es el siguiente:\n```\n{text}\n```"
)

# Max time to wait for OWUI's async (socket-delivered) completion.
_RESULT_TIMEOUT_S = 180


def _strip_details_blocks(content: str) -> str:
    """Remove OWUI tool-trace <details> blocks for the widget-facing answer."""
    return _DETAILS_BLOCK_RE.sub('', content).strip()


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
            "web_search": False,
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
            if timing is not None:
                with timing.phase("persist_ms"):
                    current_chat = c.get_chat(chat_id)
            else:
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


# ---------------------------------------------------------------------------
# Structured response (spec 007): formatter agent + tool-result extraction
# ---------------------------------------------------------------------------

def _first_output_text(fco: dict) -> Optional[str]:
    """Return the text payload of a function_call_output item."""
    out = fco.get("output")
    if isinstance(out, list):
        for piece in out:
            if isinstance(piece, dict) and isinstance(piece.get("text"), str):
                return piece["text"]
    if isinstance(out, str):
        return out
    return None


def extract_tool_result(output, tool_name: str) -> Optional[Dict]:
    """Recover the structured object returned by ``tool_name`` from an OWUI
    completion ``output`` array.

    Walks the ``function_call`` entries matching ``tool_name`` in order and
    pairs each with its ``function_call_output`` (by ``call_id``). Returns the
    LAST successfully-parsed dict that is NOT an error result
    (``{"error": true, ...}``). Tolerant of unexpected shapes → None.
    """
    if not isinstance(output, list):
        return None

    call_ids = [
        item.get("call_id")
        for item in output
        if isinstance(item, dict)
        and item.get("type") == "function_call"
        and item.get("name") == tool_name
    ]
    if not call_ids:
        return None

    outputs_by_call: Dict[str, str] = {}
    for item in output:
        if isinstance(item, dict) and item.get("type") == "function_call_output":
            text = _first_output_text(item)
            if text is not None:
                outputs_by_call[item.get("call_id")] = text

    last_ok: Optional[Dict] = None
    for cid in call_ids:
        text = outputs_by_call.get(cid)
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict) and not parsed.get("error"):
            last_ok = parsed
    return last_ok


_FORMAT_CALL_RE = re.compile(r"format_response\s*\(\s*(\{.*\})\s*\)", re.DOTALL)
_VALID_TYPES = ("text", "buttons", "list")


def parse_structured_from_text(text: str) -> Optional[Dict]:
    """Recover the structured object when the formatter emits it as plain text.

    Handles ``format_response({...})``, fenced code blocks, and bare JSON
    objects. Returns the parsed dict or None.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s).strip()

    m = _FORMAT_CALL_RE.search(s)
    if m:
        candidate = m.group(1)
    else:
        i, j = s.find("{"), s.rfind("}")
        candidate = s[i:j + 1] if (i != -1 and j > i) else None
    if not candidate:
        return None

    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _to_json_string(value) -> str:
    """Normalize a field to a JSON string (the canonical contract shape)."""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return ""


def normalize_structured(d: dict) -> Optional[Dict]:
    """Coerce a parsed structure into the canonical 7-field WhatsApp object.

    Tolerates the common model drift (e.g. ``listSections``/``buttons`` returned
    as arrays instead of JSON strings, ``listSections`` as bare rows without the
    section wrapper). Returns None if ``messageType`` is missing/invalid.
    """
    if not isinstance(d, dict):
        return None
    mt = d.get("messageType")
    if mt not in _VALID_TYPES:
        return None

    body = d.get("body")
    body = body if isinstance(body, str) else ("" if body is None else str(body))

    escalate = d.get("escalate", False)
    if not isinstance(escalate, bool):
        escalate = str(escalate).strip().lower() in ("true", "1", "yes", "sí", "si")

    list_sections = d.get("listSections", "")
    if isinstance(list_sections, list) and list_sections:
        first = list_sections[0]
        # bare rows (no section wrapper) → wrap into a single section
        if isinstance(first, dict) and "rows" not in first:
            list_sections = [{"title": "", "rows": list_sections}]

    list_button_text = d.get("listButtonText", "")
    list_button_text = list_button_text if isinstance(list_button_text, str) else ""

    return {
        "messageType": mt,
        "body": body,
        "escalate": escalate,
        "buttons": _to_json_string(d.get("buttons", "")),
        "listSections": _to_json_string(list_sections),
        "listButtonText": list_button_text,
        "quote": _to_json_string(d.get("quote", "")),
    }


def _extract_from_persisted_chat(full: dict) -> Optional[Dict]:
    """Fallback: parse the persisted chat's current message ``output``.

    The persisted chat always carries the ``function_call_output`` even when the
    socket ``done`` event didn't include the full ``output`` array.
    """
    inner = full.get("chat", full) if isinstance(full, dict) else {}
    history = (inner or {}).get("history", {}) or {}
    messages = history.get("messages", {}) or {}
    current_id = history.get("currentId") or history.get("current_id")
    msg = messages.get(current_id) if current_id else None
    if not isinstance(msg, dict):
        return None
    return extract_tool_result(msg.get("output"), "format_response")


def text_fallback(body: str) -> Dict:
    """Valid `text` structured object built from plain text (FR-009)."""
    return {
        "messageType": "text",
        "body": body or "",
        "escalate": False,
        "buttons": "",
        "listSections": "",
        "listButtonText": "",
        "quote": "",
    }


def run_formatter(
    text: str,
    user_id: str,
    owui_client: OpenWebUIClient,
    timing: Optional[RequestTiming] = None,
) -> Optional[Dict]:
    """Run the global formatter agent on the sales agent's text.

    Creates a chat with the formatter model and recovers the structured object
    from its reply (real tool call or plain-text JSON). Returns the normalized
    structured dict, or None if it couldn't be recovered (caller applies
    text_fallback).

    Like the main sales flow, the formatter chat is persisted in OWUI (a fresh
    chat per call). Never raises on formatter failure — degrades to None.
    """
    formatter_config = resolve_formatter_config()
    wrapped_text = _FORMATTER_INPUT_TEMPLATE.format(text=text)

    def _create():
        return get_or_create_chat(
            user_id,
            formatter_config["model"],
            wrapped_text,
            tenant_config=formatter_config,
            owui_client=owui_client,
        )

    try:
        if timing is not None:
            with timing.phase("format_ms"):
                chat = _create()
        else:
            chat = _create()
    except AuthExpiredError:
        # Token expired mid-formatting (rare — just used for the sales turn).
        # Degrade to fallback instead of re-running the whole request.
        logger.warning("Formatter call hit AuthExpiredError — degrading to text fallback")
        return None

    if not chat:
        return None

    # Primary path: the formatter invokes format_response as a real tool call.
    structured = extract_tool_result(chat.get("output"), "format_response")
    if structured is None:
        # Safety net only: the model wrote the structure as text instead of
        # invoking the tool. This means the tool was NOT used — investigate the
        # formatter's Function Calling / system prompt if you see this warning.
        structured = parse_structured_from_text(chat.get("assistant_response", ""))
        if structured is not None:
            logger.warning(
                "Formatter did NOT invoke format_response — recovered structure from "
                "text output (chat %s). Fix the formatter so it calls the tool.",
                chat.get("chat_id"),
            )
    if structured is not None:
        structured = normalize_structured(structured)
    return structured
