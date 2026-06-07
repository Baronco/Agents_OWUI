# Feature Specification: Fix Chat Creation & Completion Flow

**Feature Branch**: `002-fix-chat-creation`

**Created**: 2026-06-06

**Status**: Draft

**Input**: User description: "necesito que trabajemos en una nueva spec mejoras porque la api no esta funcionando, hasta ahora logramos crear el usuario per nada que creamos el chat..."

## User Scenarios & Testing

### User Story 1 - Complete Chat Lifecycle with Assistant Reply (Priority: P1)

A web plugin sends a user message to the intermediary API. The API creates a chat in Open WebUI, triggers the assistant agent, and persists the full conversation including the assistant's reply.

**Why this priority**: The core functional gap is that chat creation succeeds but the assistant never replies and the conversation is never persisted. Fixing this end-to-end flow is the minimum viable fix.

**Independent Test**: Send a single user message via the intermediary API. Verify that a chat is created in Open WebUI, the assistant responds, and both the user message and assistant reply appear in the persisted chat history.

**Acceptance Scenarios**:

1. **Given** a valid tenant mapping and non-admin user, **When** the intermediary API receives a user message, **Then** it creates a new chat via `POST /api/v1/chats/new` with the user message in both `messages[]` and `history.messages{}`.
2. **Given** a newly created chat with a user message, **When** the API injects an empty assistant message with `parentId` pointing to the user message, **Then** the chat structure contains a placeholder assistant message in `messages[]` and `history.messages{}`.
3. **Given** the chat contains the injected assistant placeholder, **When** the API calls `POST /api/chat/completions` with the chat context, **Then** it returns a streaming or complete assistant response.
4. **Given** the assistant has finished generating a response, **When** the API calls `POST /api/chat/completed`, **Then** the assistant message is finalized and persisted.

---

### User Story 2 - Multi-Turn Conversation Continuation (Priority: P2)

The intermediary API supports multi-turn conversations: a user sends a follow-up message to an existing chat, and the assistant responds with awareness of the full conversation history.

**Why this priority**: Real-world usage requires back-and-forth conversations. Without multi-turn support, each message would start a new isolated chat.

**Independent Test**: Send a first message and verify a reply. Send a second message referencing the first reply. Verify the assistant's second response acknowledges prior context and that both exchanges are persisted under the same chat.

**Acceptance Scenarios**:

1. **Given** an existing chat with a complete user-assistant exchange, **When** the intermediary API receives a new user message for the same chat, **Then** it appends the user message to the chat's `messages[]` and `history.messages{}` with `parentId` set to the last assistant message.
2. **Given** a follow-up user message has been appended, **When** the API injects a new empty assistant message and triggers completion, **Then** the assistant response includes context from prior messages.

---

### User Story 3 - Tenant to Assistant Mapping with Tools & System Prompt (Priority: P2)

Administrators configure which assistant, tools, and system prompt each tenant uses. The intermediary API applies this configuration when routing requests.

**Why this priority**: The original spec already requires tenant-to-assistant mapping. This story ensures the mapping actually applies the correct model, tools, and system prompt to each chat.

**Independent Test**: Configure two tenants with different assistant models and tools. Send identical messages for each tenant. Verify each chat uses the correct model and tool configuration.

**Acceptance Scenarios**:

1. **Given** a tenant configuration specifying a model, tool set, and system prompt, **When** a request arrives for that tenant, **Then** the chat is created using the configured model and includes the system prompt in the message history.
2. **Given** a tenant configuration with tools enabled, **When** the assistant processes a request that triggers a tool call, **Then** the tool execution result appears in the chat output and is persisted.

---

### Edge Cases

- What happens when Open WebUI is unreachable during chat creation? The intermediary should return a clear error and not create orphan state.
- How does the system handle a chat completion call that times out or returns an error? The intermediate assistant placeholder should be cleaned up or flagged as failed.
- What happens when the `tenant_id` mapping references a model that no longer exists in Open WebUI? The system should fall back gracefully with an informative error.
- How does the system behave when the same user sends messages concurrently to the same chat? The system should serialize or reject concurrent writes to prevent history corruption.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST accept incoming requests with `username`, `tenant_id`, and `message_content` and optionally `chat_id` for continuation.
- **FR-002**: The system MUST support a configurable mapping from `tenant_id` to an assistant configuration including model name, tools list, and system prompt.
- **FR-003**: The system MUST route each request to the correct assistant using the tenant mapping and pass the system prompt as the first message in chat history.
- **FR-004**: The system MUST create a new chat in Open WebUI using `POST /api/v1/chats/new` with a `ChatForm` payload containing the user message in both `messages[]` and `history.messages{}`.
- **FR-005**: After chat creation, the system MUST inject an empty assistant message into the chat structure with `role: "assistant"`, `content: ""`, and `parentId` referencing the user message's ID, added to both `messages[]` and `history.messages{}`.
- **FR-006**: The system MUST call `POST /api/chat/completions` with the chat context including `chat_id`, `session_id`, message history, model name, and feature flags.
- **FR-007**: The system MUST call `POST /api/chat/completed` after the assistant finishes responding to finalize and persist the assistant message.
- **FR-008**: For multi-turn conversations, the system MUST append each new user message to the existing chat, chain `parentId` to the prior assistant message, and repeat the inject-complete-completed flow.
- **FR-009**: The system MUST return a response payload to the caller containing the assistant's reply text, the `chat_id`, and status indicators for each step of the flow.
- **FR-010**: The system MUST handle errors at each step (chat creation, completion, finalization) with descriptive messages and MUST clean up incomplete state when possible.
- **FR-011**: The system MUST generate or manage `session_id` values required by the completions endpoint, persisting them per chat session.
- **FR-012**: The system MUST support the assistant's use of configured tools during completion, including processing `function_call` outputs and feeding results back into the chat.
- **FR-013**: The system MUST include the `followUps` array from assistant responses in the response payload.

### Key Entities

- **TenantConfiguration**: Maps a `tenant_id` to an assistant model name, list of enabled tool IDs, and a system prompt text. Stored in a configuration file or database.
- **ChatSession**: Represents an active chat in Open WebUI, including `chat_id`, `user_id`, `session_id`, `tenant_id`, and the current message tree state.
- **ChatMessage**: A single message in the conversation with `id`, `role` (user/assistant), `content`, `parentId`, `childrenIds`, `timestamp`, `model`, and optional `output` (for tool calls).
- **UserIdentity**: Represents the external `username` and `tenant_id` along with the mapped Open WebUI user credentials and session token.

## Success Criteria

### Measurable Outcomes

- **SC-001**: At least 95% of valid chat requests result in a complete assistant reply persisted in Open WebUI within 10 seconds.
- **SC-002**: Multi-turn conversations maintain full message history across at least 10 exchanges without data loss.
- **SC-003**: Tenant configurations (model, tools, system prompt) are correctly applied in 100% of test cases.
- **SC-004**: The API returns a meaningful error message within 3 seconds when Open WebUI is unreachable or returns an error.
- **SC-005**: Tool call outputs from the assistant are correctly captured, persisted, and returned to the caller in the response payload.
- **SC-006**: Administrator can configure a new tenant mapping and have it take effect without restarting the intermediary service.

## Assumptions

- The intermediary API has admin-level access (API key/token) to Open WebUI with sufficient permissions to create chats and trigger completions on behalf of non-admin users.
- The Open WebUI instance exposes the endpoints `POST /api/v1/chats/new`, `POST /api/chat/completions`, `POST /api/chat/completed`, and `GET /api/v1/chats/{id}` as described in the OpenAPI spec.
- Each chat requires a unique `session_id` which the intermediary API must generate and manage per chat session.
- The proper flow for a successful assistant reply requires: (1) create chat with user message, (2) inject empty assistant message, (3) call completions, (4) call completed endpoint.
- Assistant models and tools referenced in tenant configurations exist and are enabled in the Open WebUI instance.
- The `followUps` array from assistant completion responses should be captured and relayed to the calling plugin.
- Tool execution that returns `function_call_output` types should be processed and the results should be fed back into subsequent completion calls if the tool chain requires it.