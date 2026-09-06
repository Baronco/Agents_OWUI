"""Concurrency test for the /proxy/chat handler (specs 016-017, agentic).

The handler must be dispatched to Starlette's thread pool, not run on the
event loop, so one agentic chat request cannot block the whole server while
another is in flight. Starlette decides this purely from whether the endpoint
is a coroutine function: ``async def`` runs on the single event loop (and,
since this handler does only blocking I/O with no ``await``, blocks it for the
request's full duration); a plain ``def`` is run via ``run_in_threadpool``.

The agentic contract no longer uses client_phone/tenant_id for a per-client
lock, so the old same-client serialization test does not apply here.
"""

import inspect

import api as proxy_api


def test_handler_runs_in_threadpool_not_event_loop():
    # proxy_chat does only blocking I/O (HTTP, socket.io connect, a
    # threading.Event.wait of up to 180s) with no `await`. Declaring it
    # `async def` would run it on the event loop and block all concurrent
    # requests. It MUST remain a plain `def` so Starlette dispatches it to its
    # thread pool (spec 010 FR-001 preserved).
    assert not inspect.iscoroutinefunction(proxy_api.proxy_chat), (
        "proxy_chat is a coroutine function — it will run on the event loop and "
        "block all concurrent requests. It must be a plain `def` so Starlette "
        "dispatches it to its thread pool."
    )


def test_agentic_handler_does_not_use_provisioning():
    # The agentic flow authenticates by the caller's bearer token passthrough;
    # the handler must not call provision_user for the agentic path.
    import inspect as _inspect

    src = _inspect.getsource(proxy_api.proxy_chat)
    assert "provision_user" not in src


def test_agentic_handler_does_not_read_tenants_json():
    # Spec 017: the chat path resolves the model and its tools per request and
    # must not touch tenant routing or the tenants JSON file. (The
    # `tenant_config` kwarg name is kept only as plumbing into chat_management.)
    import inspect as _inspect

    src = _inspect.getsource(proxy_api.proxy_chat)
    assert "resolve_default_agent" not in src
    assert "tenant_routing" not in src
    assert "load_config" not in src
