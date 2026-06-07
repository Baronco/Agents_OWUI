# Implementation Plan: Fix Chat Creation & Completion Flow

**Branch**: `002-fix-chat-creation` | **Date**: 2026-06-06 | **Spec**: specs/002-fix-chat-creation/spec.md

**Input**: Feature specification from `specs/002-fix-chat-creation/spec.md`

## Summary

Fix the intermediary API's chat creation and completion flow so that assistant replies are properly triggered and persisted. The root cause identified from research (GitHub discussion #11800) and code analysis is that the 4-step backend-controlled flow is partially implemented but has critical gaps:

1. **User message not passed to chat creation** — `chat_management.py` creates chats with empty `content: ""` in messages, so completions have no context.
2. **Incomplete completion payload** — `message_builder.py` returns a minimal `{chat_id, message}` dict, but `/api/chat/completions` expects a full payload with `messages[]`, `model`, `session_id`, and feature flags.
3. **Missing client method** — `OpenWebUIClient` has no `chat_completion()` method that sends to the right endpoint with proper payload structure.
4. **Broken test** — `chat_test.py` sends empty JSON `{}` to `/api/v1/chats/new` which the ChatForm schema rejects (requires `chat` object).
5. **Tool execution flow** — `main.py` has a working tool-call loop but it's not integrated with the chat management flow.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: `fastapi`, `requests`, `pydantic`, `uuid`, `dotenv`

**Storage**: In-memory `_chat_store` dict (chat_management.py) and `_user_cache` dict (user_provisioning.py). SQLite placeholder exists in `src/persistence/chat_store.py` but unused.

**Testing**: `pytest` with existing `tests/unit/test_placeholder.py`; separate `chat_test.py`, `signup_test.py`, `login_test.py` as standalone scripts.

**Target Platform**: Server-side Python service interacting with `localhost:3000` Open WebUI instance.

**Project Type**: API proxy/service

**Performance Goals**: Chat completion round-trip under 10 seconds (SC-001). Error responses within 3 seconds (SC-004).

**Constraints**: Must use only existing Open WebUI REST endpoints (no WebSocket). Must work with non-admin user tokens. Chat must appear in Open WebUI UI after completion.

**Scale/Scope**: Single-threaded prototype supporting one plugin flow with extensible tenant mapping.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Constitution Gates:**
- Code Quality (Principle I): Existing codebase has clear structure with separate modules for client, services, models. Plan preserves this separation. PASS
- Test-First (Principle II): Plan includes unit tests for all new/modified methods and integration test for end-to-end flow. Integration test will validate against live OWUI. PASS
- UX Consistency (Principle III): API contract (ChatRequest/ChatResponse in api.py) stays consistent. Only internal fixes to client and services layer. PASS
- Performance (Principle IV): Spec defines SC-001 (10s) and SC-004 (3s). Plan tracks these. PASS
- Maintainability (Principle V): No new modules needed; only fixes to existing ones. No structural debt. PASS

**Gate: PASS** — No violations. Proceeding to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/002-fix-chat-creation/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── proxy-api.md     # Phase 1 output
└── checklists/
    └── requirements.md
```

### Source Code (repository root)

```text
src/
├── api.py                        # MODIFY: pass message content through chat lifecycle
├── config.py                     # (no changes needed)
├── client/
│   ├── openwebui_client.py       # MODIFY: add chat_completion() method, fix payload structures
│   └── message_builder.py        # MODIFY: build full completion payload per spec FR-006
├── services/
│   ├── tenant_routing.py         # (no changes needed)
│   ├── user_provisioning.py      # (no changes needed)
│   └── chat_management.py        # MODIFY: accept message content, fix 4-step flow
├── models/
│   └── __init__.py               # (no changes needed)
├── persistence/
│   └── chat_store.py             # (no changes needed)
├── utils/
│   └── logger.py                 # (no changes needed)
└── tests/
    ├── unit/
    │   └── test_placeholder.py   # REPLACE with real tests
    └── integration/
        └── test_chat_flow.py     # NEW: end-to-end integration test

main.py                          # (no changes - standalone tool-call demo)
chat_test.py                     # REPLACE: fix to use proper ChatForm payload
signup_test.py                   # (existing standalone test)
login_test.py                    # (existing standalone test)
```

**Structure Decision**: Single Python API project preserving existing module layout. Only modify files that directly impact the broken chat flow. No new modules needed.

## Complexity Tracking

No constitution violations to justify. All changes are targeted fixes within existing patterns.

## Implementation Plan

### Phase 0: Research

- **R1**: Validate the exact request/response format for `POST /api/v1/chats/new` by reading existing OWUI source or testing against live instance.
- **R2**: Validate the exact request format for `POST /api/chat/completions` — determine what `session_id` format is expected and how feature flags work.
- **R3**: Determine how `POST /api/chat/completed` interacts with the session — does it require the same `session_id` generated at chat creation?
- **R4**: Determine how the stored chat token (after user signup) affects subsequent API calls. Does the admin API key work for all operations, or does each operation need the user-specific session token?

### Phase 1: Core Fixes (Chat Lifecycle)

**1a — Fix `openwebui_client.py`:**
- Add `chat_completion()` method that calls `POST /api/chat/completions` with proper payload including `chat_id`, `id` (assistant msg id), `messages[]`, `model`, `stream`, `session_id`, `background_tasks`, `features`, `variables`.
- Ensure `inject_assistant_message()` correctly uses `POST /api/v1/chats/{id}` to update an existing chat (as currently implemented — verify this works).
- Ensure `complete_chat()` correctly calls `POST /api/chat/completed`.

**1b — Fix `message_builder.py`:**
- Replace `build_completion_payload()` with a function that builds the full payload structure required by `/api/chat/completions`.
- Include: `chat_id`, assistant message `id`, `messages` array with history, `model`, `stream: false`, `session_id`, `background_tasks`, `features`, `variables`.

**1c — Fix `chat_management.py`:**
- Modify `get_or_create_chat()` to accept the actual `user_message_content` parameter.
- Set `user_message["content"]` to the actual message content in both `messages[]` and `history.messages{}`.
- Set `payload["messages"][0]["content"]` to the actual message content.
- Generate `session_id` once per chat and persist it locally.

**1d — Fix `api.py`:**
- Pass `request.message` through to `get_or_create_chat()` so the message content is in the chat from creation.
- Ensure the response includes the `followUps` array if present in the completion response.

### Phase 2: Testing & Verification

**2a — Fix `chat_test.py`:**
- Send proper `ChatForm` payload with `chat` object containing `title`, `models`, `messages`, `history`.
- Test the raw API call to verify OWUI accepts the structure.

**2b — Add unit tests (`tests/unit/`):**
- Test `build_completion_payload()` structure matches expected format.
- Test `get_or_create_chat()` with and without message content.
- Test `inject_assistant_message()` payload construction.

**2c — Add integration test (`tests/integration/test_chat_flow.py`):**
- Test full end-to-end flow: user provision → chat create → assistant inject → completion → completed → fetch.
- Validate the final chat contains both user and assistant messages.
- Test multi-turn: second message appended to same chat, assistant responds with context.

### Phase 3: Auth Context Fix (Per-User Token)
**⚠️ CRITICAL BUG**: Two separate `OpenWebUIClient` instances exist — `api.py`'s gets the user token, `chat_management.py`'s retains the admin API key.

**3a — Fix `chat_management.py`:**
- Modify `get_or_create_chat()` and `continue_chat()` to accept an optional `client: OpenWebUIClient` parameter.
- When a `client` is passed, use it instead of the module-level global instance for all Open WebUI API calls.

**3b — Fix `api.py`:**
- Pass `self.client` (the instance with the user's bearer token set by `provision_user()`) to both `get_or_create_chat()` and `continue_chat()`.

**3c — Verify:**
- Confirm `create_user()` updates `self.session.headers` with the user's bearer token.
- Trace that all subsequent chat API calls (`create_chat_with_initial_message`, `inject_assistant_message`, `chat_completion`, `complete_chat`) use the user-scoped token.
- Update integration test to validate `user_id` in created chats matches the provisioned user.

## Research Findings

(To be filled after Phase 0)