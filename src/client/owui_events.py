"""Best-effort status event emission to Open WebUI chats (spec 020, US3).

When ``ENABLE_FORWARD_USER_INFO_HEADERS=True``, Open WebUI forwards
``X-OpenWebUI-Chat-Id`` / ``X-OpenWebUI-Message-Id`` to the tool server. The
batch endpoint uses them to post ``status`` events so the parent chat shows
per-sub-agent progress. Emission is best-effort: any failure is logged and
never affects the batch result.
"""

import requests

from src.utils.logger import logger

_EVENT_TIMEOUT_S = 5


def emit_status(
    base_url: str,
    token: str,
    chat_id: str,
    message_id: str,
    data: dict,
    timeout: int = _EVENT_TIMEOUT_S,
) -> bool:
    """POST a ``status`` event to the chat message; return success as a bool.

    Never raises: connection errors, timeouts, and non-2xx responses are logged
    at debug level and return ``False``.
    """
    if not base_url or not token or not chat_id or not message_id:
        return False
    url = f"{base_url.rstrip('/')}/api/v1/chats/{chat_id}/messages/{message_id}/event"
    try:
        resp = requests.post(
            url,
            json={"type": "status", "data": data},
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        if resp.status_code >= 400:
            logger.debug("Status event rejected for chat %s (HTTP %s)", chat_id, resp.status_code)
            return False
        return True
    except Exception as exc:
        logger.debug("Status event for chat %s failed: %s", chat_id, exc)
        return False
