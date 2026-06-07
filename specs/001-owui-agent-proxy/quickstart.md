# Quickstart: OWUI Agent Proxy

## Prerequisites

- Python 3.13 installed
- Local Open WebUI instance running at `http://localhost:3000`
- Open WebUI API key available as `OWUI_API_KEY`
- Optional: `ECOMMERCE_API_KEY` if ecommerce tool integrations are needed

## Setup

1. Create a virtual environment in the repository root:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install required packages:

```bash
pip install requests
```

3. Configure environment variables for Open WebUI and the ecommerce tool.
   The repository already includes `example.env` with placeholders for both `OWUI_API_KEY` and `ECOMMERCE_API_KEY`.

```powershell
$env:OWUI_API_KEY = "your-openwebui-key"
$env:OWUI_BASE_URL = "http://localhost:3000"
$env:ECOMMERCE_API_KEY = "your-ecommerce-key"
```

## Running the Proxy

1. Implement the proxy service based on the plan in `specs/001-owui-agent-proxy/plan.md`.
2. Start the API service:

```bash
python src/api.py
```

3. Send a request to the proxy endpoint with `username`, `tenant_id`, and `message`.

Example payload:

```json
{
  "username": "usuario1",
  "tenant_id": "tenant-a",
  "message": "Hola, ¿qué opciones de audífonos tienes?"
}
```

## Test Flow

1. Verify tenant routing resolves to a valid assistant.
2. Ensure non-admin user provisioning is attempted for new users.
3. Confirm a chat session is created and that the assistant response is returned.
4. Check that the response payload includes `chat_id` and assistant text.

## Notes

- If Open WebUI does not persist full conversation history, the proxy will store minimal session metadata locally.
- Review `specs/001-owui-agent-proxy/research.md` for the Open WebUI client reuse strategy.
