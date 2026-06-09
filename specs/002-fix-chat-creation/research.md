# Research Findings: Fix Chat Creation & Completion Flow

## Unknowns Resolved

### R1: Exact request format for `POST /api/v1/chats/new`

**Decision**: The endpoint accepts a `ChatForm` with a `chat` object (additionalProperties: true) and optional `folder_id`. The `chat` object must contain `title`, `models[]`, `messages[]`, and `history{}` with `current_id` and `messages{}` map.

**Rationale**: From the OpenAPI spec (ChatForm schema at line 26366), the required field is `chat` which is `additionalProperties: true`. The GitHub discussion #11800 (AngelosZaimis solution) confirms the expected structure with `title`, `models`, `messages` array, and `history` map. The existing chat export JSON confirms the nested message structure with `id`, `role`, `content`, `parentId`, `childrenIds`, `timestamp`, `models`.

**Alternatives considered**: Sending `{}` (empty JSON) which `chat_test.py` does — this fails because the `chat` property is required.

### R2: Exact request format for `POST /api/chat/completions`

**Decision**: The endpoint accepts an open JSON object (additionalProperties: true per OpenAPI spec line 22855). The required fields per discussion #11800 are:
- `chat_id` — string
- `id` — assistant message UUID
- `messages` — array of `{role, content}` objects (full conversation history)
- `model` — string (model name)
- `stream` — boolean (false for non-streaming)
- `session_id` — string (UUID generated per chat session)
- `background_tasks` — object with `title_generation`, `tags_generation`, `follow_up_generation` booleans
- `features` — object with `code_interpreter`, `web_search`, `image_generation`, `memory` booleans
- `variables` — object with template variables like `{{USER_NAME}}`, `{{USER_LANGUAGE}}`, etc.

**Rationale**: The OpenAPI spec specifies `additionalProperties: true` with no schema constraints, so all fields are convention-based. The discussion #11800 provides the only documented working payload structure.

**Alternatives considered**: Using the OpenAI-compatible `/ollama/v1/chat/completions` which follows the standard OpenAI format — but this bypasses Open WebUI's chat persistence and session management. The `/api/chat/completions` endpoint is the correct one for UI-compatible chats.

### R3: How `POST /api/chat/completed` interacts with the session

**Decision**: `POST /api/chat/completed` requires the same `session_id` generated at chat creation, plus `chat_id`, `id` (assistant message UUID), and `model`. This endpoint finalizes the assistant response so it becomes visible in the UI and persistable.

**Rationale**: The discussion #11800 shows this as the fourth step in the flow. The OpenAPI spec confirms the endpoint exists with `additionalProperties: true` request body. Without calling this endpoint, the assistant message remains in an incomplete/unpersisted state.

**Alternatives considered**: Skipping the completed call — but the discussion clearly states this is required for the assistant message to be retrievable.

### R4: Token/session handling for API calls

**Decision**: After user signup (`/api/v1/auths/signup`), the response includes a `token` that the `OpenWebUIClient.create_user()` method already attaches to the session headers. This token is used for all subsequent authenticated calls (chat creation, completions, etc.). The admin API key (`OWUI_API_KEY`) is NOT used for individual user chat operations — the user-specific token from signup/login is required.

**Rationale**: The `OpenWebUIClient.create_user()` already stores the returned `token` in `self.session.headers`. The existing `login_test.py` shows the login flow. The signup endpoint returns a bearer token scoped to the new user, which the Open WebUI backend uses to authorize chat operations for that user.

**Alternatives considered**: Using a single admin API key for all operations — but the signup endpoint returns a user-specific token, and subsequent chat operations need to be associated with the correct user identity.

## Key Code Issues Identified (from artifact analysis)

1. **`src/services/chat_management.py:get_or_create_chat()`** — Does not accept `message_content` parameter. Sets `content: ""` for the user message, creating a chat with empty context.

2. **`src/client/message_builder.py:build_completion_payload()`** — Returns `{chat_id, message}` which is not the correct format for `/api/chat/completions`. The endpoint expects a rich payload with `messages[]`, `model`, `session_id`, `features`, etc.

3. **`src/client/openwebui_client.py`** — Missing `chat_completion()` method. The `_post()` helper exists but no dedicated method wraps `/api/chat/completions` with the proper payload.

4. **`chat_test.py`** — Sends `{}` to `/api/v1/chats/new` which fails because `ChatForm` requires `chat` property.

5. **`src/api.py:proxy_chat()`** — Creates chat and sends completion separately but message content is only passed to `build_completion_payload()` and not to `get_or_create_chat()`. The chat gets created with empty messages, then a separate completion call is made.

## References

- GitHub Discussion #11800: https://github.com/open-webui/open-webui/discussions/11800
- AngelosZaimis solution (July 14, 2025): The 4-step flow with proper payload structures
- OpenAPI spec: `owui_openapi.json` — ChatForm (line 26366), ChatResponse (line 26771), completions (line 22848), completed (line 22985)
- Chat export: `chat-export-1780805265444.json` — confirmed message/history structure