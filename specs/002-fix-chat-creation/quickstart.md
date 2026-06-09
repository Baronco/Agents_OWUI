# Quickstart: Fix Chat Creation & Completion Flow

## Prerequisites

- Python 3.13+
- Open WebUI instance running at `http://localhost:3000`
- Admin API key for Open WebUI (optional — user signup may not require it depending on OWUI config)

## Setup

```bash
# Clone and enter the repo (already done if you're here)
cd agents-owui

# Install dependencies
uv sync  # or: pip install -r requirements.txt

# Configure environment
cp example.env .env
# Edit .env to set:
#   OWUI_BASE_URL=http://localhost:3000
#   OWUI_API_KEY=your-admin-api-key (optional, for admin operations)

# Verify Open WebUI is accessible
python signup_test.py
# Expected: status 200, response contains user_id and token
```

## Running the Proxy

```bash
# Start the FastAPI server
uvicorn src.api:app --reload --port 8000
```

## Testing the Fix

### Test 1: Raw Chat Creation
```bash
python chat_test.py
```
Expected: status 200, response includes `id` (chat UUID).

### Test 2: Full End-to-End Flow
```bash
# Via curl
curl -X POST http://localhost:8000/proxy/chat \
  -H "Content-Type: application/json" \
  -d '{
    "username": "test_user",
    "tenant_id": "a0000001-0000-4000-8000-000000000001",
    "message": "Estoy buscando audífonos, ¿cuáles tienes disponibles?"
  }'
```

Expected response (200):
```json
{
    "assistant_response": "Tenemos estas opciones...",
    "chat_id": "uuid",
    "user_id": "uuid",
    "assistant_id": "asistente-de-ventas",
    "tenant_id": "a0000001-0000-4000-8000-000000000001",
    "timestamp": "2026-06-06T23:30:00Z",
    "follow_ups": ["...", "..."]
}
```

### Test 3: Multi-Turn Conversation
```bash
# First message (creates chat)
curl -X POST ... -d '{"username":"test","tenant_id":"a00...","message":"Hola"}'
# Response includes chat_id: "abc-123"

# Follow-up (continues chat)
curl -X POST ... -d '{"username":"test","tenant_id":"a00...","message":"¿Qué más tienen?","chat_id":"abc-123"}'
```

### Test 4: Integration Tests
```bash
pytest tests/ -v
```

## Verifying the Fix

1. Run the full e2e flow and note the `chat_id` from the response
2. Open Open WebUI at `http://localhost:3000` and log in with the provisioned user credentials
3. Verify the chat appears in the user's chat list with both user and assistant messages
4. Verify the assistant response contains the expected output (including tool call results if applicable)
5. For multi-turn: repeat and verify the second exchange preserves context

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `422 Validation Error` on chat create | ChatForm payload missing required `chat` property | Ensure message content is passed to chat creation |
| Assistant response is empty | Empty message content in completion payload | Verify message content flows through all 4 steps |
| Chat not appearing in UI | Missing `POST /api/chat/completed` call | Ensure completed endpoint is called after completion |
| `session_id` errors | Session mismatch between steps | Generate session_id once, persist in _chat_store |
| Tool not executing | Tool not enabled in tenant config | Add `tool_ids` to TenantConfiguration mapping |