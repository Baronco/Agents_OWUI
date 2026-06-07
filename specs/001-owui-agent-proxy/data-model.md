# Data Model

## Entities

### UserIdentity
- `username` (string): Application-level user identifier.
- `tenant_id` (string): Tenant identifier used for assistant mapping.
- `openwebui_user_id` (string|null): The corresponding Open WebUI user identifier.
- `email` (string): Generic email created for the Open WebUI account.
- `password` (string): Generic password created for the Open WebUI account (stored securely).
- `assistant_id` (string|null): Resolved assistant or model identifier for this tenant.
- `created_at` (string, timestamp): When the proxy record was created.

### OpenWebUIUser
- `user_id` (string): Open WebUI user identifier.
- `username` (string): The name used within the proxy.
- `email` (string): Generic email used for signup.
- `password` (string): Generic password for the Open WebUI account.
- `is_admin` (boolean): Must be `false` for proxy-created accounts.

### ChatSession
- `chat_id` (string): Open WebUI chat identifier returned from `/api/v1/chats/new`.
- `tenant_id` (string): Tenant identifier used to resolve assistant mapping.
- `user_identity` (UserIdentity): Link to the associated proxy user.
- `assistant_id` (string): The resolved assistant or model the session is using.
- `status` (string): Chat status such as `active`, `closed`, or `failed`.
- `created_at` (string, timestamp): Session creation time.
- `updated_at` (string, timestamp): Last activity time.

### ConversationMessage
- `message_id` (string|null): Optional message identifier assigned by the proxy or API.
- `chat_id` (string): Linked `ChatSession` identifier.
- `role` (string): `user` or `assistant`.
- `content` (string): The text content of the message.
- `timestamp` (string, timestamp): When the message was sent.

## Relationships

- `UserIdentity` 1..1 -> `ChatSession`
- `ChatSession` 1..* -> `ConversationMessage`

## Validation Rules

- `username` + `tenant_id` must be unique for provisioning purposes.
- `email` must satisfy Open WebUI signup requirements.
- `assistant_id` must resolve before a chat is created.
- `chat_id` is required for all persisted chat history.

## Persistence Strategy

- Dependency on Open WebUI chat storage for most session state.
- The proxy retains minimal metadata for tenant mapping and chat continuity.
- If Open WebUI does not expose complete conversation retrieval, the proxy can maintain the message sequence locally in a lightweight store.
