---

description: "Generated tasks for OWUI Agent Proxy"
---

# Tasks: OWUI Agent Proxy

**Input**: Design documents from `/specs/001-owui-agent-proxy/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Create project structure per implementation plan in the repository root.
- [X] T002 Initialize Python project with `fastapi` and `requests` dependencies (add to `requirements.txt`).
- [X] T003 [P] Configure linting (`ruff`) and formatting (`black`) tools.

## Phase 2: Foundational (Blocking Prerequisites)

- [X] T004 Setup basic OpenWebUI client wrapper in `src/client/openwebui_client.py`.
- [X] T005 [P] Implement message builder in `src/client/message_builder.py`.
- [X] T006 [P] Add environment configuration management (`.env` handling) in `src/config.py`.
- [X] T007 Create base entity models (`UserIdentity`, `OpenWebUIUser`, `ChatSession`, `ConversationMessage`) in `src/models/__init__.py`.
- [X] T008 Configure error handling and logging infrastructure in `src/utils/logger.py`.
- [X] T009 Setup API routing skeleton in `src/api.py` with placeholder endpoint.

## Phase 3: User Story 1 – Agent Routing by Tenant (Priority: P1) 🎯 MVP

**Goal**: Route incoming requests to the correct OpenWebUI assistant based on `tenant_id`.

**Independent Test**: Send a valid request with `username`, `tenant_id`, and `message`; verify the response contains a correct `assistant_response` and the mapped `assistant_id`.

### Implementation for User Story 1

- [X] T010 [P] [US1] Add tenant‑assistant mapping logic in `src/services/tenant_routing.py`.
- [X] T011 [US1] Implement proxy endpoint in `src/api.py` (`POST /proxy/chat`) that validates input and invokes tenant routing.
- [X] T012 [US1] Wire tenant routing into the request flow in `src/api.py`.
- [X] T013 [US1] Return `assistant_id` and `assistant_response` in the JSON payload.

**Checkpoint**: User Story 1 should be fully functional and testable independently.

## Phase 4: User Story 2 – Non‑Admin User Provisioning (Priority: P2)

**Goal**: Provision or reuse a non‑admin OpenWebUI user before chat creation.

**Independent Test**: Request a chat for a new `username`/`tenant_id`; confirm a non‑admin user is created (or reused) and `user_id` is returned.

### Implementation for User Story 2

- [X] T014 [P] [US2] Implement user provisioning logic in `src/services/user_provisioning.py` (signup via `/api/v1/auths/signup`).
- [X] T015 [US2] Integrate provisioning step into `src/api.py` before chat creation.
- [X] T016 [US2] Store/retrieve generated credentials securely (e.g., using `keyring` or encrypted local store).

**Checkpoint**: User Story 2 should be independently testable after foundational tasks.

## Phase 5: User Story 3 – Chat Session Creation & Persistence (Priority: P3)

**Goal**: Create a new chat session, persist conversation history, and return chat metadata.

**Independent Test**: Send a message, verify a chat session is created, then send a follow‑up and confirm both messages are persisted and retrievable.

### Implementation for User Story 3

- [X] T017 [P] [US3] Implement chat session management in `src/services/chat_management.py` (create via `/api/v1/chats/new`, update via `/api/v1/chats/{id}`).
- [X] T018 [US3] Add persistence fallback (lightweight SQLite) in `src/persistence/chat_store.py` for environments where OpenWebUI lacks full history retrieval.
- [X] T019 [US3] Extend `src/api.py` to call chat management after user provisioning and routing.
- [X] T020 [US3] Ensure the response payload includes `assistant_response`, `chat_id`, `user_id`, `assistant_id`, `tenant_id`, and `timestamp`.

**Checkpoint**: User Story 3 should be fully functional and testable independently.

## Phase N: Polish & Cross‑Cutting Concerns

- [X] T021 [P] Update documentation in `README.md` with usage examples for the proxy API.
- [X] T022 [P] Add comprehensive logging for all proxy actions in `src/utils/logger.py`.
- [X] T023 [P] Write additional unit tests for utility functions in `tests/unit/`.
- [X] T024 [P] Perform security review of credential handling and sanitise inputs.
- [ ] T025 [P] Run performance benchmarks to ensure response latency < 3 s under load.

## Dependencies & Execution Order

- **Setup (Phase 1)** → **Foundational (Phase 2)** → **User Stories (Phases 3‑5)** → **Polish (Phase N)**
- All user stories depend only on the Foundational phase; they can be worked on in parallel once Phase 2 is complete.
