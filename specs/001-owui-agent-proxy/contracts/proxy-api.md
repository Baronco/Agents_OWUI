# API Contract: OWUI Agent Proxy

## Endpoint

`POST /proxy/chat`

### Request

Content-Type: `application/json`

```json
{
  "username": "string",
  "tenant_id": "string",
  "message": "string"
}
```

### Response

Content-Type: `application/json`

```json
{
  "assistant_response": "string",
  "chat_id": "string",
  "user_id": "string",
  "assistant_id": "string",
  "tenant_id": "string",
  "timestamp": "string"
}
```

### Errors

- `400 Bad Request`
  - Missing `username`, `tenant_id`, or `message`
  - Invalid input format
- `404 Not Found`
  - Unknown `tenant_id` mapping
- `502 Bad Gateway`
  - Open WebUI unavailable
- `500 Internal Server Error`
  - User provisioning failed
  - Chat creation failed

## Behavior

- Validate `username`, `tenant_id`, and `message`.
- Resolve the appropriate assistant for the `tenant_id`.
- Provision or reuse a non-admin Open WebUI user account.
- Create or continue a chat session in Open WebUI.
- Persist the user and assistant messages where supported.
- Return a stable response payload with the assistant text and session metadata.
