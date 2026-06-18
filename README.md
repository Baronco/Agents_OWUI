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
3. Provision the tenant config (not in git — treated like `.env`, business data not source code):
   ```bash
   cp config/tenants.json.example config/tenants.json
   ```
   then edit it with the real tenant_id/model/tool_ids — see
   `specs/009-config-externalization/contracts/tenants-config-schema.md`.
4. Run the API server:
   ```bash
   uvicorn src. --host 0.0.0.0 --port 8000
   ```
5. Send a request to the proxy endpoint:
   ```bash
   curl -X POST http://localhost:8000/proxy/chat \
        -H "Content-Type: application/json" \
        -d '{"username": "alice", "tenant_id": "tenantA", "message": "Hello"}'
   ```

## Architecture

- **src/api.py** – FastAPI entry point exposing `POST /proxy/chat`.
- **src/client/** – Wrapper around OpenWebUI REST endpoints and payload builder.
- **src/services/** – Business logic for tenant routing, user provisioning, and chat management.
- **src/services/tenant_config_loader.py** – Loads and validates `config/tenants.json` (tenant list + the global formatter config) on every call (no caching, no restart needed to pick up changes); fails fast with a clear error on a missing/malformed file, both at startup and on the next request if it breaks later.
- **config/tenants.json** – Tenant‑to‑assistant mapping and the global formatter config. **Not committed** (gitignored, like `.env` — business data, not source code); copy `config/tenants.json.example` to get started. Edit this file (no Python changes needed) to add/change a tenant or rename an assistant — see `specs/009-config-externalization/contracts/tenants-config-schema.md` for the schema.
- **src/models/** – Light‑weight dataclasses representing core entities.
- **src/persistence/** – SQLite fallback for message persistence (currently a stub).
- **src/utils/logger.py** – Centralised logger.

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
