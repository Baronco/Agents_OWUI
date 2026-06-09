# Feature Specification: OWUI Agent Proxy

**Feature Branch**: `001-owui-agent-proxy`

**Created**: 2026-06-03

**Status**: Draft

**Input**: User description: "Necesito que me ayudes a construir una app que va a ser intermediaria entre un plugin web y la API de Open WebUI (`localhost:3000/openapi.json`). Esta nueva API recibirá un nombre de usuario y un tenant id para identificar con qué asistente debe comunicarse el usuario. El primer borrador ya invoca al agente creado en Open WebUI y usa la tool correspondiente. Se busca crear primero el usuario en Open WebUI con correo y contraseña genéricos (sin ser admin), luego crear un nuevo chat y persistir la conversación del usuario y del asistente, usando solo APIs como se haría desde la misma interfaz de Open WebUI."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Agent Routing by Tenant (Priority: P1)

A web plugin sends a request to the intermediary API with `username` and `tenant_id`; the proxy resolves the correct Open WebUI assistant and routes the request through the Open WebUI API.

**Why this priority**: This is the core value of the feature. Without correct tenant-to-assistant routing, the intermediary API cannot behave as a transparent agent proxy.

**Independent Test**: Send a valid request with `username`, `tenant_id`, and a user message. Verify the proxy returns a valid assistant response and metadata identifying the mapped assistant.

**Acceptance Scenarios**:

1. **Given** a valid `username` and `tenant_id`, **When** the plugin calls the intermediary API, **Then** the system resolves the correct assistant mapping and forwards the request to Open WebUI.
2. **Given** a known tenant mapping, **When** the request is processed, **Then** the response from Open WebUI is returned to the caller with an associated chat identifier.

---

### User Story 2 - Non-Admin User Provisioning (Priority: P2)

Before starting the chat, the intermediary API creates or reuses a non-admin Open WebUI user account using a generic email and password for the incoming `username` and `tenant_id`.

**Why this priority**: The assistant session requires a recognized user identity in Open WebUI. Creating a generic user account first prevents admin-only or anonymous restrictions from blocking the chat.

**Independent Test**: Request a chat for a new `username` and `tenant_id`. Confirm the service creates a non-admin Open WebUI user account and returns a usable user identity or reuses an existing account.

**Acceptance Scenarios**:

1. **Given** a username that does not exist in Open WebUI, **When** the proxy handles the first request, **Then** it creates a non-admin user account with generic credentials.
2. **Given** an existing non-admin Open WebUI user for the same `username` and `tenant_id`, **When** the request arrives, **Then** the service reuses the existing account instead of creating a duplicate.

---

### User Story 3 - Chat Session Creation and Persistence (Priority: P3)

The intermediary API starts a new chat session in Open WebUI and persists the conversation history for both the user and the assistant.

**Why this priority**: Persisting the conversation ensures continuity and supports future chat retrieval, while matching the behavior of the Open WebUI interface through API calls.

**Independent Test**: Send a message, verify a chat session is created, then retrieve the stored history and confirm both the user message and assistant response are available.

**Acceptance Scenarios**:

1. **Given** valid user identity and assistant routing, **When** the proxy initiates a chat, **Then** a chat session is created and an identifier is returned.
2. **Given** an active chat session, **When** the user sends a follow-up message, **Then** the system persists the new user message and the subsequent assistant response.

---

### Edge Cases

- What happens when the Open WebUI API rejects generic user creation due to policy or duplicate users?
- How does the system behave if `tenant_id` cannot be mapped to an assistant or if the mapping is missing?
- How is the outcome handled when Open WebUI is available but chat persistence is not supported by the API?
- How does the proxy respond when required fields are missing or malformed in the incoming request?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST expose an intermediary API endpoint that accepts `username`, `tenant_id`, and user input.
- **FR-002**: The system MUST resolve the correct Open WebUI assistant or agent mapping based on `tenant_id`.
- **FR-003**: The system MUST provision or reuse a non-admin Open WebUI user account with a generic email and password before starting a chat session.
- **FR-004**: The system MUST create or continue a chat session in Open WebUI for the resolved assistant and user identity.
- **FR-005**: The system MUST persist both the user's messages and the assistant's responses for the chat session.
- **FR-006**: The system MUST return a clear response payload containing the assistant reply, chat identifier, and any user identity metadata needed to continue the session.
- **FR-007**: The system MUST surface user-visible errors when Open WebUI is unavailable, when user provisioning fails, or when tenant mapping is invalid.

### Key Entities *(include if feature involves data)*

- **UserIdentity**: Represents the incoming `username` and `tenant_id` values, plus the resolved Open WebUI user credentials and assistant mapping.
- **OpenWebUIUser**: Represents a non-admin user account in Open WebUI, including generic email, password, and status.
- **ChatSession**: Represents the active chat created in Open WebUI, including `chat_id`, `tenant_id`, state, and associated user identity.
- **ConversationMessage**: Represents a persisted message exchange with sender role (`user` or `assistant`), timestamp, and content.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least 90% of valid requests with `username` and `tenant_id` correctly map to an Open WebUI assistant and return a valid assistant response.
- **SC-002**: New connections for unknown usernames create a non-admin Open WebUI user account before the chat begins.
- **SC-003**: The intermediary API persists and returns user and assistant message history for active chat sessions.
- **SC-004**: The intermediary API responds to valid requests within 3 seconds when Open WebUI is available.
- **SC-005**: The system returns a clear, actionable error message when Open WebUI is unavailable or when tenant mapping is invalid.

## Assumptions

- Open WebUI at `localhost:3000/openapi.json` exposes endpoints sufficient to create users, start chats, and persist chat content or else the proxy will maintain the minimum required history externally.
- The feature will use a simple tenant-to-assistant resolution strategy, such as configuration-based mapping or tenant naming rules.
- Generic user credentials will be created without admin privileges and stored securely in the intermediary layer.
- The intermediary app is responsible for the API proxy, user provisioning, chat lifecycle, and persistence logic; web plugin UI behavior is out of scope.
