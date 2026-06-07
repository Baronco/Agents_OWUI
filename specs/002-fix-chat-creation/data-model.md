# Data Model: Fix Chat Creation & Completion Flow

## Entities

### TenantConfiguration
Maps a tenant to its assistant configuration. Loaded from configuration file or environment at startup.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `tenant_id` | UUID string | Unique tenant identifier | Must match format `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `model` | string | Open WebUI model/assistant name | Must exist in OWUI; default: `"asistente-de-ventas"` |
| `tool_ids` | string[] | Tool identifiers enabled for this tenant | Optional; e.g. `["server:0"]` |
| `system_prompt` | string | System prompt prepended to chat | Optional; used as first message in history |

**State transitions**: Static configuration — loaded at startup, changes require restart (SC-006 requires hot-reload in future).

### UserIdentity
Represents an external user mapped to an Open WebUI account.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `username` | string | External username from plugin | Non-empty |
| `tenant_id` | UUID string | Tenant identifier | Must match a `TenantConfiguration` |
| `owui_user_id` | UUID string | Open WebUI user ID (after provisioning) | Returned from signup |
| `email` | string | Auto-generated email | Format: `{username}_{tenant_id}@proxy.local` |
| `password` | string | Auto-generated password | Default: `"ChangeMe123!"` |
| `token` | string | Bearer token from OWUI signup | Stored in session for API calls |
| `assistant_id` | string | Resolved assistant name from tenant | Via `resolve_assistant()` |

**State transitions**: Created on first request → cached in `_user_cache` → reused on subsequent requests for same `username:tenant_id` pair.

### ChatSession
Represents an active chat conversation in Open WebUI.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `chat_id` | UUID string | Open WebUI chat ID | Returned from `POST /api/v1/chats/new` |
| `user_id` | UUID string | OWUI user ID (who owns the chat) | Must match a provisioned user |
| `assistant_id` | string | Model name used for this chat | Must match tenant config |
| `session_id` | UUID string | Session UUID used for completions | Generated once per chat |
| `last_message_id` | UUID string | ID of the most recent message (for chaining parentId) | Updated after each exchange |
| `status` | enum: `active`, `completed`, `failed` | Current chat status | `active` by default |
| `message_count` | int | Number of exchanges | Incremented on each assistant reply |

**State transitions**: `active` → created → messages appended → `completed` on completion call. Failed operations leave chat in `active` state with error logged.

### ChatMessage
A single message in the conversation tree, mirroring the Open WebUI structure.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `id` | UUID string | Unique message identifier | Generated via `uuid.uuid4()` |
| `role` | enum: `user`, `assistant` | Message sender role | `user` for input, `assistant` for response |
| `content` | string | Message text content | Empty string `""` for injected assistant placeholder |
| `parentId` | UUID string (nullable) | Parent message ID for threading | `null` for first user message; assistant msg ID for follow-up user; user msg ID for assistant |
| `childrenIds` | UUID string[] | Child message IDs | Updated as conversation grows |
| `timestamp` | int | Unix timestamp in milliseconds | `int(time.time() * 1000)` |
| `models` | string[] | Models used for this message | Usually `[model_name]` |
| `modelName` | string | Specific model name | Same as model for assistant messages |
| `modelIdx` | int | Model index | Always `0` |
| `output` | array (optional) | Tool call output entries | Present when assistant executes tools |

**State transitions**: Messages are created in order: user message → assistant (empty placeholder) → assistant (with content after completion). Messages are immutable after finalization.

## Relationships

```text
UserIdentity (1) ─────────── has_many ────────▶ ChatSession (N)
TenantConfiguration (1) ─── configured_by ────▶ ChatSession (1)
ChatSession (1) ─────────── contains ─────────▶ ChatMessage (N)
ChatMessage ─────────────── parent/child ─────▶ ChatMessage (self-referential)
```

## State Machine: Chat Lifecycle

```text
[IDLE] → RECEIVE_MESSAGE → CREATE_CHAT → INJECT_ASSISTANT → COMPLETION → COMPLETED → [DONE]
                                    │              │                │
                                    ▼              ▼                ▼
                                [FAILED]       [FAILED]          [FAILED]
```

1. **IDLE**: Waiting for incoming request
2. **RECEIVE_MESSAGE**: Parse `username`, `tenant_id`, `message_content`, optional `chat_id`
3. **CREATE_CHAT**: `POST /api/v1/chats/new` with user message in payload
4. **INJECT_ASSISTANT**: `POST /api/v1/chats/{id}` with empty assistant placeholder
5. **COMPLETION**: `POST /api/chat/completions` to trigger assistant response
6. **COMPLETED**: `POST /api/chat/completed` to finalize
7. **DONE**: Return response to caller with `assistant_response`, `chat_id`, `followUps`

For multi-turn: After COMPLETED → append new user message → INJECT_ASSISTANT → COMPLETION → COMPLETED → DONE