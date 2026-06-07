import os, requests, json, uuid, time
base = os.getenv('OWUI_BASE_URL','http://localhost:3000')

user_msg_id = str(uuid.uuid4())
now_ms = int(time.time() * 1000)

user_message = {
    "id": user_msg_id,
    "role": "user",
    "content": "Estoy buscando audífonos, ¿cuáles tienes disponibles?",
    "timestamp": now_ms,
    "models": ["asistente-de-ventas"],
}

payload = {
    "chat": {
        "title": "Test Chat",
        "models": ["asistente-de-ventas"],
        "messages": [user_message],
        "history": {
            "current_id": user_msg_id,
            "messages": {
                user_msg_id: user_message
            },
        },
    }
}

resp = requests.post(f"{base.rstrip('/')}/api/v1/chats/new", json=payload)
print('status', resp.status_code)
print('body', resp.text)