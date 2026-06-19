"""Concurrency tests for the /proxy/chat handler (spec 010, US1).

Two coupled properties:

1. The handler must be dispatched to Starlette's thread pool, not run on the
   event loop, so a request for one client/tenant cannot block the whole
   server while another's is in flight. Starlette decides this purely from
   whether the endpoint is a coroutine function: ``async def`` runs on the
   single event loop (and, since this handler does only blocking I/O with no
   ``await``, blocks it for the request's full duration); a plain ``def`` is
   run via ``run_in_threadpool``. We assert that property directly
   (test_handler_runs_in_threadpool_not_event_loop), because Starlette's
   ``TestClient`` spins up an independent portal per threaded request and so
   structurally cannot reproduce a live single-loop server's blocking — the
   live-server behavior is validated manually in quickstart.md (Caso 1).
2. Requests for the SAME client/tenant must serialize their
   provisioning-and-chat-creation work — today the per-client lock only
   wraps a log line, so the race is real and observable even under
   TestClient (test_same_client_requests_serialize).

These two fixes must land together: enabling true concurrency (property 1)
is what makes property 2's race reachable on a live server.
"""
import inspect
import threading
import time

from fastapi.testclient import TestClient

import api as proxy_api


def _patch_collaborators(monkeypatch, get_or_create):
    """Stub everything the handler calls so no real network/socket happens."""
    monkeypatch.setattr(proxy_api, "resolve_assistant", lambda t: "asistente-de-ventas")
    monkeypatch.setattr(proxy_api, "resolve_tenant_config", lambda t: {})
    monkeypatch.setattr(
        proxy_api, "provision_user",
        lambda *a, **k: {"user_id": "u1", "email": "e@proxy.local", "token": "tok", "is_new_session": True},
    )
    monkeypatch.setattr(proxy_api, "get_owui_chat_id", lambda *a, **k: None)
    monkeypatch.setattr(proxy_api, "store_chat_mapping", lambda *a, **k: None)
    monkeypatch.setattr(proxy_api, "get_or_create_chat", get_or_create)
    monkeypatch.setattr(
        proxy_api, "run_formatter",
        lambda *a, **k: {
            "messageType": "text", "body": "hola", "escalate": False,
            "buttons": "", "listSections": "", "listButtonText": "", "quote": "",
        },
    )


def _post(client, phone, tenant="a0000001-0000-4000-8000-000000000001", chat_id="x"):
    return client.post("/proxy/chat", json={
        "tenant_id": tenant, "client_phone": phone, "chat_id": chat_id, "message": "hola",
    })


def test_handler_runs_in_threadpool_not_event_loop():
    # Starlette runs `async def` endpoints on the single event loop and plain
    # `def` endpoints via run_in_threadpool. Since proxy_chat does only
    # blocking I/O (HTTP, socket.io connect, a threading.Event.wait of up to
    # 180s) with no `await`, declaring it `async def` blocks the whole server
    # per request. It MUST be a plain `def` so independent clients/tenants can
    # be served concurrently (spec 010 FR-001).
    assert not inspect.iscoroutinefunction(proxy_api.proxy_chat), (
        "proxy_chat is a coroutine function — it will run on the event loop and "
        "block all concurrent requests. It must be a plain `def` so Starlette "
        "dispatches it to its thread pool."
    )


def test_same_client_requests_serialize(monkeypatch):
    # Counts how many requests are simultaneously inside the
    # provisioning-and-chat-creation section. With a correctly-scoped
    # per-client lock this never exceeds 1 for the same client/tenant.
    state = {"inside": 0, "max_inside": 0}
    state_lock = threading.Lock()

    def fake_get_or_create(*a, **k):
        with state_lock:
            state["inside"] += 1
            state["max_inside"] = max(state["max_inside"], state["inside"])
        time.sleep(0.3)  # hold the section long enough to overlap if unguarded
        with state_lock:
            state["inside"] -= 1
        return {"chat_id": "c1", "assistant_response": "hola", "output": [], "follow_ups": []}

    _patch_collaborators(monkeypatch, fake_get_or_create)
    client = TestClient(proxy_api.app)

    # Same phone + tenant for both -> must serialize.
    threads = [
        threading.Thread(target=_post, args=(client, "+573009999999")),
        threading.Thread(target=_post, args=(client, "+573009999999")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert state["max_inside"] == 1, (
        "two same-client requests were inside the provisioning-and-chat-creation "
        "section at the same time — the per-client lock does not guard it."
    )
