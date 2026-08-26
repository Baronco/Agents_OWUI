"""Utility to build OpenWebUI message payloads.
Ensures consistent structure for chat completions.
"""

def build_completion_payload(chat_id: str, assistant_msg_id: str, message_content: str, model: str, session_id: str) -> dict:
    """Return full payload for /api/chat/completions endpoint per contract Step 3."""
    import time
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "chat_id": chat_id,
        "id": assistant_msg_id,
        "messages": [
            {"role": "user", "content": message_content},
        ],
        "model": model,
        "stream": False,
        "session_id": session_id,
        "background_tasks": {
            "title_generation": True,
            "tags_generation": False,
            "follow_up_generation": True,
        },
        "features": {
            "code_interpreter": False,
            "web_search": False,
            "image_generation": False,
            "memory": False,
        },
        "variables": {
            "{{USER_NAME}}": "",
            "{{USER_LANGUAGE}}": "es-ES",
            "{{CURRENT_DATETIME}}": now,
            "{{CURRENT_TIMEZONE}}": "America/Santiago",
        },
    }