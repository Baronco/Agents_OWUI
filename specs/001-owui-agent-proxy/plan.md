# Implementation Plan: OWUI Agent Proxy

**Branch**: `001-owui-agent-proxy` | **Date**: 2026-06-03 | **Spec**: specs/001-owui-agent-proxy/spec.md

**Input**: Feature specification from `specs/001-owui-agent-proxy/spec.md`

## Summary

Build a Python intermediary API that accepts `username`, `tenant_id`, and a user message from a web plugin, resolves the corresponding Open WebUI assistant, and proxies the request through Open WebUI.

This implementation will reuse the architectural patterns from the reviewed `openwebui-client` repository: a reusable Open WebUI client abstraction and a message builder to manage conversation payloads. The new proxy will add tenant-to-assistant routing, non-admin user provisioning, and chat lifecycle management on top of Open WebUI's REST API.

The existing `main.py` already provides a minimal baseline for calling `localhost:3000/api/chat/completions` with `OWUI_API_KEY` and handling tool-based `server:0` responses. We will preserve that progress, adapt it to the feature proxy, and centralize the ecommerce tool bearer usage via `ECOMMERCE_API_KEY`.

Key local Open WebUI endpoints identified from `owui_openapi.json`:
- `/api/v1/auths/signup` — create non-admin user accounts
- `/api/v1/auths/signin` — authenticate users if session tokens are necessary
- `/api/v1/chats/new` — create new chat sessions
- `/api/v1/chats/{id}` — retrieve or update chat sessions
- `/api/chat/completions` — request assistant responses

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: `requests`, `fastapi` or `flask` for API routing, `pydantic` for validation, and the repository's own Open WebUI client wrapper.

**Storage**: Primary state in Open WebUI; optional local persistence for conversation metadata if Open WebUI does not explicitly store full history via the available endpoints.

**Testing**: `pytest` for unit and integration tests.

**Target Platform**: Server-side Python service interacting with `localhost:3000` Open WebUI.

**Project Type**: API proxy/service

**Performance Goals**: Maintain response latency under 3 seconds for valid requests when Open WebUI is available.

**Constraints**: No admin-level Open WebUI user operations; minimal payload overhead; robust validation for `username`, `tenant_id`, and assistant mapping.

**Scale/Scope**: Prototype support for one plugin flow with extensible tenant-assistant mapping.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Architecture separates concerns: proxy API, Open WebUI client, user provisioning, tenant mapping, and chat persistence.
- No constitution violations are apparent in this plan.

## Project Structure

### Documentation (this feature)

```text
specs/001-owui-agent-proxy/
├── spec.md
├── plan.md
├── research.md
└── checklists/
    └── requirements.md
```

### Source Code (repository root)

```text
src/
├── api.py
├── client/
│   ├── openwebui_client.py
│   ├── proxy_client.py
│   └── message_builder.py
├── services/
│   ├── tenant_routing.py
│   ├── user_provisioning.py
│   └── chat_management.py
└── tests/
    ├── unit/
    └── integration/
```

**Structure Decision**: Use a single Python API project with a dedicated Open WebUI client layer and a small tests directory for unit and integration coverage.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Custom tenant routing | Required to map `tenant_id` to the correct assistant | A generic Open WebUI client cannot service tenant-specific assistant selection by itself |
| User provisioning layer | Required to create/reuse non-admin accounts for chat sessions | Anonymous or admin-only flows cannot meet the requested identity requirements |

## Implementation Plan

### Phase 1: Foundation

- Build a reusable Open WebUI client wrapper around the `openwebui-client` design.
  - Wrap `/api/chat/completions`, `/api/models`, and relevant chat endpoints.
  - Implement `OpenWebUIMessageBuilder` for consistent payload construction.
- Implement tenant-to-assistant resolution using configuration or environment settings.
- Implement non-admin user provisioning with `/api/v1/auths/signup` and a safe credential pattern.
- Add the intermediary API endpoint that accepts `username`, `tenant_id`, and `message`.

### Phase 2: Chat Lifecycle

- Create new chat sessions with `/api/v1/chats/new`.
- Retrieve or update chat state using `/api/v1/chats/{id}`.
- Forward user messages to `/api/chat/completions` using the current conversation context.
- Preserve assistant and user exchanges either through Open WebUI chat state or proxy-side storage.

### Phase 3: Stability and UX

- Add clear error handling for invalid tenant mappings, user provisioning failures, and Open WebUI availability issues.
- Ensure responses include assistant text, `chat_id`, and metadata for subsequent requests.
- Keep output format consistent with the existing project style.

### Phase 4: Testing

- Unit test proxy routing, user creation, and request payload construction.
- Integration test the end-to-end flow against a local Open WebUI instance.
- Validate that the current `main.py` approach can be adapted to the new proxy path.

## Research Findings

- The reviewed `openwebui-client` repo provides a strong client pattern but does not implement tenant routing or user provisioning.
- Its `OpenWebUIClient` and `OpenWebUIMessageBuilder` abstractions are reusable for our chat and message management.
- Our feature will need a custom layer for `/api/v1/auths/signup`, tenant mapping, and chat lifecycle control.
- If Open WebUI does not persist both user and assistant history automatically, the proxy must maintain minimal chat state.
