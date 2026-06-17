"""Open WebUI websocket (socket.io) listener.

Open WebUI runs tool-enabled chat completions ASYNCHRONOUSLY: the HTTP
/api/chat/completions call (with a chat_id) returns a quick ``{chat_id, task_id}``
ack and streams the real answer over socket.io to the user's room. To let OWUI
execute the model's attached tools server-side, the proxy connects as a socket
client (exactly like the browser) and waits for the assistant message's
``chat:completion`` ``done`` event.

Protocol (from the OWUI frontend + backend):
- connect to ``/ws/socket.io`` with ``auth={'token': <bearer>}`` → auto-joins
  the ``user:{user_id}`` room (open-webui socket/main.py connect handler);
- the server emits socket event ``'events'`` with ``{chat_id, message_id, data}``
  where ``data = {type, data}``; ``type == 'chat:completion'`` carries
  ``{done, content, output, choices}`` (open-webui Chat.svelte chatEventHandler).
"""
from contextlib import contextmanager
from typing import Iterator, Optional, Tuple
import threading

import socketio

from src.utils.logger import logger

_SOCKET_PATH = "/ws/socket.io"
_CONNECT_TIMEOUT_S = 10


def _ipv4(base_url: str) -> str:
    """Force IPv4 for localhost.

    websocket-client resolves ``localhost`` to ``::1`` (IPv6) first on Windows;
    if OWUI listens only on IPv4 the websocket TCP connect hangs until timeout.
    Plain HTTP (requests) is unaffected, so we only normalize the socket URL.
    """
    return base_url.replace("//localhost", "//127.0.0.1")


class _CompletionState:
    def __init__(self) -> None:
        self.content: str = ""
        self.output = None
        self.error = None
        self.done = threading.Event()
        self.sid: Optional[str] = None


def _make_client(assistant_msg_id: str, state: "_CompletionState") -> socketio.Client:
    sio = socketio.Client(reconnection=False, logger=False, engineio_logger=False)

    @sio.on("events")
    def _on_events(ev):  # noqa: ANN001 — socketio handler
        try:
            if not isinstance(ev, dict) or ev.get("message_id") != assistant_msg_id:
                return
            inner = ev.get("data") or {}
            etype = inner.get("type")
            data = inner.get("data") or {}
            if etype == "chat:completion":
                if isinstance(data.get("content"), str):
                    state.content = data["content"]
                elif data.get("choices"):
                    choice = (data["choices"] or [{}])[0]
                    piece = (
                        (choice.get("delta") or {}).get("content")
                        or (choice.get("message") or {}).get("content")
                        or ""
                    )
                    state.content += piece
                if data.get("output") is not None:
                    state.output = data["output"]
                if data.get("done"):
                    state.done.set()
            elif etype in ("message", "chat:message:delta"):
                state.content += data.get("content", "") or ""
            elif etype in ("replace", "chat:message"):
                state.content = data.get("content", "") or ""
            elif etype == "chat:message:error":
                state.error = data.get("error")
                state.done.set()
        except Exception as exc:  # never let a handler error break the socket
            logger.debug("socket events handler error: %s", exc)

    return sio


@contextmanager
def completion_listener(base_url: str, token: str, assistant_msg_id: str) -> Iterator[_CompletionState]:
    """Connect to OWUI's socket, listen for the assistant message's completion.

    OWUI's socket server accepts a single transport — ``websocket`` when
    ENABLE_WEBSOCKET_SUPPORT is on, else ``polling`` — so try websocket first and
    fall back to polling. Yields a state object; the caller triggers the HTTP
    completion (using ``state.sid`` as session_id) and waits on ``state.done``.
    """
    state = _CompletionState()
    connect_url = _ipv4(base_url)
    sio = None
    last_err: Optional[Exception] = None
    for transport in (["websocket"], ["polling"]):
        candidate = _make_client(assistant_msg_id, state)
        try:
            candidate.connect(
                connect_url,
                socketio_path=_SOCKET_PATH,
                transports=transport,
                auth={"token": token},
                wait_timeout=_CONNECT_TIMEOUT_S,
            )
            sio = candidate
            logger.info("Socket connected to OWUI (transport=%s, sid=%s)", transport[0], candidate.sid)
            break
        except Exception as exc:
            last_err = exc
            logger.warning("Socket connect via %s failed: %r", transport[0], exc)
            try:
                candidate.disconnect()
            except Exception:
                pass
    if sio is None:
        logger.error("Socket connect to %s%s failed on all transports", base_url, _SOCKET_PATH)
        raise last_err if last_err else ConnectionError("socket connect failed")

    state.sid = sio.sid
    try:
        yield state
    finally:
        try:
            sio.disconnect()
        except Exception:
            pass


def await_completion(
    base_url: str,
    token: str,
    assistant_msg_id: str,
    trigger,
    timeout: float,
) -> Tuple[Optional[str], str, object]:
    """Run the full socket round-trip.

    ``trigger(session_id)`` must POST the completion and return the ack dict
    (containing ``chat_id`` for new chats). Returns ``(chat_id, content, output)``.
    """
    with completion_listener(base_url, token, assistant_msg_id) as state:
        ack = trigger(state.sid) or {}
        chat_id = ack.get("chat_id") or ack.get("id")
        if not state.done.wait(timeout=timeout):
            logger.warning("Timed out waiting for socket completion of %s", assistant_msg_id)
        if state.error:
            logger.warning("OWUI reported completion error: %s", state.error)
        return chat_id, state.content, state.output
