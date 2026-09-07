# OWUI Agent Proxy

This repository implements a Python proxy service that mediates between a web plugin and the OpenWebUI API.

## Quickstart

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set required environment variables (example defaults are in `src/config.py`):
   - `OWUI_API_KEY` – API key for OpenWebUI (if needed)
   - `OPENWEBUI_BASE_URL` – Base URL of the OpenWebUI instance (default `http://localhost:3000`)
3. (Optional, legacy) Provision the tenant config (not in git — treated like `.env`, business
   data not source code):
   ```bash
   cp config/tenants.json.example config/tenants.json
   ```
   The chat endpoint (spec 017) no longer reads it — the caller names the model per call.
4. Run the API server:
   ```bash
   uvicorn api:app --host 0.0.0.0 --port 8000
   ```
5. Send a request to the proxy endpoint (see `specs/018-subagent-session-id/contracts/proxy-chat.md`):
   ```bash
   curl -X POST http://localhost:8000/proxy/chat \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer <open-webui-token>" \
        -H "X-Subagent-Tools-Key: <service-api-key>" \
        -d '{"message": "Hello", "model_id": "asistente-de-ventas"}'
   ```
   The response carries the answer plus the live sub-agent session id:
   `{"assistant_response": "...", "subagent_chat_id": "..."}` — resend that id
   as `chat_id` to continue the same session.

## Docker

The proxy ships with a `Dockerfile` and `docker-compose.yml`. Per-environment
data (tenant config + per-user tokens) lives on a **persistent named volume**
mounted at `/data` with two folders — `config/` and `users/` — so it survives
container recreation and is editable without rebuilding the image. Secrets are
passed via `.env` (never baked into the image).

```bash
# 1. Build the image and create the volume
docker build -t owui-proxy .
docker volume create owui-proxy-data

# 2. Seed the tenant config onto the volume BEFORE first start.
#    (The proxy fails fast at startup if config is missing, so it can't be
#    copied in after a crash.)
cat config/tenants.json | docker run --rm -i -v owui-proxy-data:/data owui-proxy \
  sh -c "mkdir -p /data/config /data/users && cat > /data/config/tenants.json"

# 3. Run (compose creates container + volume together)
docker compose up -d
```

Notes:
- **`OPENWEBUI_BASE_URL` inside a container must NOT be `localhost`** (that's
  the container itself). Use `http://host.docker.internal:3000` or a service
  name on a shared Docker network.
- **`.env` values must be UNQUOTED** — `docker --env-file` does not strip
  quotes (unlike a shell), so quotes would become part of the value. Copy
  `.env.example` (already unquoted) and fill in real values.
- **Changing `USER_PASSWORD_SECRET` invalidates all previously provisioned
  users** (their derived passwords change), so they'd fail to sign in. Set it
  once and keep it stable.
- The container runs as a non-root `app` user. The `config/` volume folder is
  authoritative and must persist; the `users/` folder is a rebuildable token
  cache (losing it only forces a one-time re-login per client).
- Token storage is **one JSON file per user** under `users/`, keyed by
  `(client_phone, tenant_id)` — the same layout locally and in the container.

### Markdown / meta-learning endpoint variables (spec 015)

The `POST /learn` endpoint (markdown generator ported from GenFilesMCP) reads these from `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `OWUI_URL` | `http://localhost:8080` | Open WebUI base URL used for user-id lookup, upload, and knowledge filing. Point at the **same** instance as `OPENWEBUI_BASE_URL`; inside a container use `http://host.docker.internal:3000`. |
| `ENABLE_CREATE_KNOWLEDGE` | `true` | Whether the generated file is added to a knowledge collection. |
| `KNOWLEDGE_COLLECTION_NAME` | `My Generated Files` | Name of the knowledge collection that receives generated files. |
| `DOWNLOAD_HTML_BUTTON` | `false` | The `/learn` handler forces this to `false`, returning the raw structured result (never the HTML download-page). |

## Architecture

- **api.py** – FastAPI entry point exposing `POST /proxy/chat` — an agentic sub-agent call authenticated by the caller's bearer token and routed to the requested `model_id` (spec 017); the request body is `{message, model_id, chat_id?}` plus the `X-Subagent-Tools-Key` header, tools are resolved live from the model metadata, and the response is `{assistant_response, subagent_chat_id}` (spec 018 — the live session id, so parents need not run the `chat_id` tool). Also exposes `POST /learn` (spec 015), the agent's memory / meta-learning tool: it runs a caller-provided Python script to build a Markdown file, uploads it to Open WebUI, and optionally files it into a knowledge collection.
- **tools/** and **utils/** – Ported verbatim from the `GenFilesMCP` project to support `POST /learn` (`tools/markdown_tool.py` runs the script and uploads; `tools/shared.py` holds the response helpers relocated from the source's `api/shared.py` because the `api` name is taken by this module; `utils/http/*` talk to Open WebUI). Copied byte-for-byte; do not modify.
- **src/client/** – Wrapper around OpenWebUI REST endpoints and payload builder.
- **src/services/** – Business logic for tenant routing, user provisioning, and chat management.
- **src/services/tenant_config_loader.py** – Loads and validates `config/tenants.json` (tenant list + optional `default_agent`) on every call (no caching, no restart needed to pick up changes); fails fast with a clear error on a missing/malformed file, both at startup and on the next request if it breaks later.
- **config/tenants.json** – Legacy agent/tenant mapping. **Not committed** (gitignored, like `.env` — business data, not source code). `POST /proxy/chat` no longer reads it (spec 017 routes by per-call `model_id`); the file and loader remain for reference only.
- **src/models/** – Light‑weight dataclasses representing core entities.
- **src/persistence/** – SQLite fallback for message persistence (currently a stub).
- **src/utils/logger.py** – Centralised logger.
- **scripts/** – Manual debugging/diagnostic tools (e.g. `diag_socket.py`), NOT part of the running application — never imported by `api.py`/`src/`.

## Concurrency

`proxy_chat` is intentionally a **synchronous** (`def`, not `async def`) endpoint.
Every call it makes is blocking I/O (HTTP via `requests`, a socket.io connect, a
`threading.Event.wait` of up to 180s) with no `await`, so declaring it `async`
would run it on the single event loop and **block the entire server for each
request's full duration** — different clients/tenants could not be served at the
same time. As a plain `def`, Starlette dispatches it to its thread pool, so
independent clients run concurrently. **Do not re-add `async`** to this handler
without first making the whole call chain genuinely async. Requests sharing the
same `(client_phone, tenant_id)` are serialized through an in-process lock so
two near-simultaneous messages from one client can't race into duplicate chat
creation. See `specs/010-performance-efficiency-audit/`.

## Performance: native function calling

The proxy calls OpenWebUI's `/api/chat/completions` with `params.function_calling: "native"`
whenever `tool_ids` are configured. This is **required** for latency: without it, OpenWebUI
runs a prompt-based tool pre-pass — a full extra LLM round-trip on *every* message just to
decide whether a tool is needed — before generating the actual answer. Native function calling
passes the tool specs inline so the model decides in a single pass. See
`specs/005-reduce-api-latency/contracts/owui-completion.md`.

The proxy also avoids an upfront token-validation round-trip per request: the cached token is
trusted while unexpired, and a stale token is recovered lazily (a 401 triggers one
re-authentication + retry). Each request logs a `request_timing` line with a per-phase
breakdown (`provision_ms`, `completion_ms`, `tool_ms`, `persist_ms`, `total_ms`, `round_trips`).

## Notes

- User credentials are generated with simple placeholders; integrate a secure password generator and secret storage for real deployments.
- Message persistence is handled by OpenWebUI; the proxy is stateless and persists chats via the OpenWebUI chat API.
