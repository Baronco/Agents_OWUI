# Tasks: Fix Chat Creation & Completion Flow

**Input**: Design documents from `specs/002-fix-chat-creation/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Test tasks are included for integration-level verification (not unit-level TDD). Tests validate the fix works against a live Open WebUI instance.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `tests/` at repository root
- This is a fix-only feature — all changes are modifications to existing files

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify existing project infrastructure is ready; no new project initialization needed.

- [x] T001 Verify project dependencies installed (`uv sync` or `pip install -r requirements.txt`)
- [x] T002 Verify Open WebUI instance is accessible at configured `OWUI_BASE_URL`
- [x] T003 [P] Verify existing test scripts run without import errors: `python signup_test.py`, `python login_test.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Understand the existing codebase structure and confirm the exact payload structures needed for OWUI endpoints.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 [P] Read existing `src/client/openwebui_client.py` and `src/client/message_builder.py` to confirm current method signatures and payload structures
- [x] T005 [P] Read existing `src/services/chat_management.py` to confirm the `get_or_create_chat()` current signature and flow
- [x] T006 [P] Read existing `src/api.py` to confirm the `proxy_chat()` handler flow and `ChatRequest`/`ChatResponse` model fields

**Checkpoint**: Foundation ready - codebase understood, modification plan confirmed

---

## Phase 3: User Story 1 - Complete Chat Lifecycle with Assistant Reply (Priority: P1) 🎯 MVP

**Goal**: Fix the core chat lifecycle so that a single user message triggers a complete assistant reply that is persisted in Open WebUI.

**Independent Test**: Send a single user message via `POST /proxy/chat` with username, tenant_id, and message. Verify:
1. Status 200 with `assistant_response` containing the assistant's reply text
2. Response includes a valid `chat_id` (UUID)
3. The chat is visible in Open WebUI UI with both messages

### Implementation for User Story 1

- [x] T007 [P] [US1] Replace `build_completion_payload()` in `src/client/message_builder.py` with a function that builds the full `/api/chat/completions` payload per contract Step 3 (includes `chat_id`, `id`, `messages[]`, `model`, `stream`, `session_id`, `background_tasks`, `features`, `variables`)
- [x] T008 [P] [US1] Add `chat_completion()` method to `OpenWebUIClient` in `src/client/openwebui_client.py` that calls `POST /api/chat/completions` with the full payload from message_builder
- [x] T009 [US1] Modify `get_or_create_chat()` in `src/services/chat_management.py` to accept a `message_content: str` parameter and use it for `user_message["content"]` in both `messages[]` and `history.messages{}`, and for `payload["messages"][0]["content"]`
- [x] T010 [US1] Modify `get_or_create_chat()` in `src/services/chat_management.py` to generate and persist `session_id` per chat, and use the new `message_builder` + `chat_completion()` methods instead of inline payload construction
- [x] T011 [US1] Modify `proxy_chat()` in `src/api.py` to pass `request.message` through to `get_or_create_chat()` and capture `followUps` from the completion response into the `ChatResponse`
- [x] T012 [US1] Fix `chat_test.py` to send a proper `ChatForm` payload with `chat` object containing `title`, `models`, `messages`, `history` per contract Step 1
- [x] T013 [US1] Create integration test `tests/integration/test_chat_flow.py` that validates the full US1 flow: user provision → chat create → assistant inject → completion → completed → fetch

**Checkpoint**: At this point, User Story 1 should be fully functional. Send a message, get an assistant reply, see it in OWUI.

---

## Phase 4: User Story 2 - Multi-Turn Conversation Continuation (Priority: P2)

**Goal**: Support follow-up messages to an existing chat, with the assistant responding with full conversation context.

**Independent Test**: 
1. Send a first message → get `chat_id` back
2. Send a second message with the same `chat_id` referencing the first reply
3. Verify the assistant's second response acknowledges prior context
4. Verify both exchanges are persisted under the same `chat_id`

### Implementation for User Story 2

- [x] T014 [P] [US2] Add `continue_chat()` method to `src/services/chat_management.py` that appends a new user message to an existing chat (with `parentId` set to the last assistant message), injects a new empty assistant message, triggers completion, and marks completed
- [x] T015 [US2] Modify `proxy_chat()` in `src/api.py` to accept optional `chat_id` in the request, and route to `continue_chat()` instead of `get_or_create_chat()` when `chat_id` is provided
- [x] T016 [US2] Add the `continue_chat()` response fields (repeated from US1 but for the new exchange) to the `ChatResponse` in `src/api.py`
- [x] T017 [US2] Extend `tests/integration/test_chat_flow.py` with a US2 multi-turn test: send message, send follow-up with chat_id, verify both exchanges

**Checkpoint**: At this point, User Story 1 AND User Story 2 should both work. Multi-turn conversations are supported.

---

## Phase 5: User Story 3 - Tenant to Assistant Mapping with Tools & System Prompt (Priority: P2)

**Goal**: Make tenant configuration include model name, tool IDs, and system prompt. Apply these settings when creating chats.

**Independent Test**: 
1. Configure two tenants with different models and system prompts in `tenant_routing.py`
2. Send identical messages for each tenant
3. Verify each chat uses the correct model and includes the configured system prompt in history
4. For the tool-enabled tenant: verify a tool-triggering prompt returns tool call results

### Implementation for User Story 3

- [x] T018 [US3] Extend `TENANT_ASSISTANT_MAP` in `src/services/tenant_routing.py` to a richer structure that includes `model`, `tool_ids`, and `system_prompt` per tenant (e.g., `Dict[str, TenantConfig]`)
- [x] T019 [US3] Add a `TenantConfig` dataclass or TypedDict in `src/models/__init__.py` with fields: `model: str`, `tool_ids: list[str]`, `system_prompt: str`
- [x] T020 [US3] Modify `resolve_assistant()` in `src/services/tenant_routing.py` to return the full `TenantConfig` dict instead of just a string
- [x] T021 [US3] Modify `get_or_create_chat()` in `src/services/chat_management.py` to accept and use `tenant_config` for model selection and system prompt injection (prepend system prompt as first message in history)
- [x] T022 [US3] Modify `proxy_chat()` in `src/api.py` to pass tenant config through to chat management
- [x] T023 [US3] Integrate tool execution from `main.py` into the chat management flow: when assistant returns `tool_calls` in completion, execute tools via the ecommerce API and feed results back through another completion round
- [x] T024 [US3] Extend `tests/integration/test_chat_flow.py` with a US3 test: configure two tenants, send identical messages, verify different model/system prompt behavior

**Checkpoint**: All three user stories should be functional. Tenant-specific model, tools, and system prompts are applied.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and documentation updates.

- [x] T025 [P] Run `python chat_test.py` and verify it returns status 200 with a valid chat ID
- [x] T026 [P] Run `pytest tests/ -v` and verify all tests pass
- [x] T027 Run the quickstart.md manual validation (curl the proxy, verify in OWUI UI)
- [x] T028 Update `AGENTS.md` to reference the completed tasks

---

## Phase 7: Bug Fix — Per-User Auth Token for Chat Operations (Priority: P0 — Blocker)

**⚠️ CRITICAL BUG**: `api.py` and `chat_management.py` each create their own global `client = OpenWebUIClient()` instance. When `provision_user()` calls `client.create_user()`, it updates the auth header in `api.py`'s client instance with the user's bearer token. However, `chat_management.py` has a **separate** `OpenWebUIClient` instance that **never receives the user token** — it retains the `OWUI_API_KEY` (admin key). As a result, all chat operations (`create_chat_with_initial_message`, `chat_completion`, etc.) are executed under the **admin account** instead of the end user's account.

**Root cause**: The user's bearer token (returned from `POST /api/v1/auths/signup` as `"token"`) is stored in `api.py`'s client session, but `chat_management.py`'s client session never gets updated.

**Fix**: Make `chat_management.py` accept and use the `OpenWebUIClient` instance from `api.py` so that the user's bearer token flows through to all chat API calls.

- [x] T029 [P] [BUG] Modify `get_or_create_chat()`, `continue_chat()`, and `provision_user()` to accept an optional `owui_client: OpenWebUIClient` parameter. When provided, use it instead of the module-level global client instance.
- [x] T030 [BUG] Modify `proxy_chat()` in `src/api.py` to pass its own `client` instance (which has the user's bearer token after `provision_user()`) to `provision_user()`, `get_or_create_chat()`, and `continue_chat()`.
- [x] T031 [BUG] Verify the fix: trace that `client.create_user()` sets `self.session.headers` with the user's token, and that all subsequent `create_chat_with_initial_message`, `inject_assistant_message`, `chat_completion`, and `complete_chat` calls use that same session (i.e., the user's token, not `OWUI_API_KEY`).
- [x] T032 [BUG] Update `tests/integration/test_chat_flow.py` to validate that chats are created under the correct user identity (e.g., by fetching the chat and verifying `user_id` matches the provisioned user).

**Checkpoint**: Chats are created and persisted under the end user's account, not the admin account.

---

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - US1 (Phase 3) must complete before US2 (Phase 4) — US2 builds on US1's fixed chat lifecycle
  - US3 (Phase 5) can start in parallel with US2 after US1 completes (they modify different files)
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (P1)**: No dependencies on other stories — the MVP
- **US2 (P2)**: Depends on US1 — must have working chat lifecycle before multi-turn
- **US3 (P2)**: Depends on US1 — must have working chat lifecycle before tenant config matters

### Within Each Phase

- Models before services
- Services before endpoint integration
- Core implementation before test extension
- Story complete before moving to next priority

### Parallel Opportunities

- T001, T002, T003 (Phase 1) can run in parallel
- T004, T005, T006 (Phase 2) can run in parallel
- T007, T008 (Phase 3) can run in parallel (different files)
- T014 (Phase 4) and T018-T020 (Phase 5) can start in parallel after US1 completes

---

## Parallel Example: User Story 1

```bash
# Launch parallel file modifications together:
Task: "Replace build_completion_payload() in src/client/message_builder.py"
Task: "Add chat_completion() method in src/client/openwebui_client.py"

# Then sequential:
Task: "Modify get_or_create_chat() in src/services/chat_management.py"
Task: "Modify proxy_chat() in src/api.py"
Task: "Fix chat_test.py"
Task: "Create integration test in tests/integration/test_chat_flow.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1 (ALL of T007-T013)
4. **STOP and VALIDATE**: Run `python chat_test.py` and the integration test
5. Deploy/demo if ready — the core fix is delivered

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Chat create + assistant reply works (MVP!)
3. Add User Story 2 → Multi-turn conversations work
4. Add User Story 3 → Tenant config with model/tools/system prompt
5. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Phase 1 + Phase 2 together
2. Once Phase 2 is done:
   - Developer A: User Story 1 (Phase 3) — ALL of it (critical path)
3. After US1 completes:
   - Developer A: User Story 2 (Phase 4)
   - Developer B: User Story 3 (Phase 5)
4. Final polish and validation together

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
- US2 and US3 are both P2 — if capacity is limited, prioritize US2 (multi-turn) over US3 (tenant config)