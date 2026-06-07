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
3. Run the API server:
   ```bash
   uvicorn src.api:app --host 0.0.0.0 --port 8000
   ```
4. Send a request to the proxy endpoint:
   ```bash
   curl -X POST http://localhost:8000/proxy/chat \
        -H "Content-Type: application/json" \
        -d '{"username": "alice", "tenant_id": "tenantA", "message": "Hello"}'
   ```

## Architecture

- **src/api.py** – FastAPI entry point exposing `POST /proxy/chat`.
- **src/client/** – Wrapper around OpenWebUI REST endpoints and payload builder.
- **src/services/** – Business logic for tenant routing, user provisioning, and chat management.
- **src/models/** – Light‑weight dataclasses representing core entities.
- **src/persistence/** – SQLite fallback for message persistence (currently a stub).
- **src/utils/logger.py** – Centralised logger.

## Notes

- The tenant‑assistant mapping is currently hard‑coded in `src/services/tenant_routing.py`; replace with a proper configuration store for production.
- User credentials are generated with simple placeholders; integrate a secure password generator and secret storage for real deployments.
- Message persistence is logged; implement SQLite storage in `src/persistence/chat_store.py` if OpenWebUI does not retain full history.
