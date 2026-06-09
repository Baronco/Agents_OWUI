# Research: Open WebUI Client Reuse for OWUI Agent Proxy

## Decision

Reuse the architectural patterns from the `openwebui-client` repository, but implement custom proxy logic for tenant routing, user provisioning, and chat lifecycle management.

## Rationale

The reviewed repository already defines a clean Python client layer for Open WebUI and a message builder for conversation payloads. Using those patterns reduces integration effort and keeps our implementation focused on the new proxy responsibilities.

## Alternatives Considered

- Build only raw Open WebUI API calls without a client abstraction.
  - Rejected because it adds low-level boilerplate and duplicates the client-style structure already available.
- Use the existing `main.py` approach as the only integration layer.
  - Rejected because it lacks the explicit tenant/assistant routing and user provisioning required by the feature.

## Findings from `openwebui-client`

### Reusable patterns

- `OpenWebUIClient`: persistent session, JSON headers, chat and file endpoints.
- `OpenWebUIMessageBuilder`: consistent creation of the `messages` list for user/assistant content.
- Support for both non-streaming and streaming chat completions.
- File upload lifecycle management for RAG-style requests.

### Gaps for our feature

- No tenant-to-assistant mapping layer.
- No user creation or signup flow for non-admin accounts.
- No explicit proxy API design for plugin requests.

### OpenAPI alignment

Our local OpenWebUI schema confirms the following endpoints are available and relevant:
- `/api/v1/auths/signup` for non-admin user provisioning.
- `/api/v1/auths/signin` for authentication where needed.
- `/api/v1/chats/new` for starting new chat sessions.
- `/api/v1/chats/{id}` for chat retrieval and updates.
- `/api/chat/completions` for the actual assistant response generation.

## Implementation fit

Reuse the client and message builder structure, while adding:
- `tenant_routing.py` for mapping `tenant_id` to assistant configuration.
- `user_provisioning.py` for generic user signup.
- `chat_management.py` for chat creation, retrieval, and persistence.
- A single API endpoint that accepts `username`, `tenant_id`, and a message from the web plugin.

## Next validation steps

- Confirm the exact tenant mapping semantics (assistant alias, model name, or tool identifier).
- Verify whether chat history must be fully reconstructed on each request or whether the Open WebUI chat endpoints persist it automatically.
- Decide whether to store minimal state locally in the proxy or rely entirely on Open WebUI session/chat storage.
