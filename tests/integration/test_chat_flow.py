"""Integration tests for the OWUI Agent Proxy chat flow.
Tests the full backend-controlled flow against a live Open WebUI instance.

Requires:
- Open WebUI running at OWUI_BASE_URL (default http://localhost:3000)
- OWUI_API_KEY or a user signup-accessible instance
"""
import os
import uuid
import time
import pytest
import requests

BASE_URL = os.getenv("OWUI_BASE_URL", "http://localhost:3000").rstrip("/")
MODEL = "asistente-de-ventas"


def _ensure_user():
    """Provision a test user and return {user_id, token, email, password}."""
    username = f"test_{uuid.uuid4().hex[:8]}"
    email = f"{username}@proxy.local"
    password = "ChangeMe123!"
    resp = requests.post(
        f"{BASE_URL}/api/v1/auths/signup",
        json={"name": username, "email": email, "password": password, "profile_image_url": "/user.png"},
    )
    assert resp.status_code == 200, f"Signup failed: {resp.text}"
    data = resp.json()
    return {
        "username": username,
        "email": email,
        "password": password,
        "user_id": data.get("user_id") or data.get("id"),
        "token": data.get("token", ""),
    }


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _create_chat_with_exchange(headers: dict, user_content: str, assistant_content: str) -> str:
    """Create a chat in OWUI with one complete user+assistant exchange. Returns chat_id."""
    now = int(time.time())
    user_msg_id = str(uuid.uuid4())
    assistant_msg_id = str(uuid.uuid4())

    user_message = {
        "id": user_msg_id,
        "parentId": None,
        "childrenIds": [assistant_msg_id],
        "role": "user",
        "content": user_content,
        "timestamp": now,
        "models": [MODEL],
    }
    assistant_message = {
        "id": assistant_msg_id,
        "parentId": user_msg_id,
        "childrenIds": [],
        "role": "assistant",
        "content": assistant_content,
        "timestamp": now,
        "models": [MODEL],
        "done": True,
    }

    resp = requests.post(
        f"{BASE_URL}/api/v1/chats/new",
        json={
            "chat": {
                "title": user_content[:60],
                "models": [MODEL],
                "messages": [{"role": "user", "content": user_content}],
                "history": {
                    "currentId": assistant_msg_id,
                    "messages": {
                        user_msg_id: user_message,
                        assistant_msg_id: assistant_message,
                    },
                },
            }
        },
        headers=headers,
    )
    assert resp.status_code == 200, f"Chat creation failed: {resp.text}"
    chat_id = resp.json().get("id")
    assert chat_id, f"No chat ID in response: {resp.text}"
    return chat_id


class TestChatFlow:
    """Integration tests for the chat creation and completion flow."""

    @pytest.fixture(autouse=True)
    def setup_user(self):
        self.user = _ensure_user()
        self.headers = _auth_headers(self.user["token"])

    def test_us1_full_chat_lifecycle(self):
        """US1: Create chat with user message, inject assistant, complete, verify."""
        now_ms = int(time.time() * 1000)
        user_msg_id = str(uuid.uuid4())

        user_message = {
            "id": user_msg_id,
            "role": "user",
            "content": "Estoy buscando audífonos, ¿cuáles tienes disponibles?",
            "timestamp": now_ms,
            "models": [MODEL],
        }

        chat_payload = {
            "chat": {
                "title": "Integration Test Chat",
                "models": [MODEL],
                "messages": [user_message],
                "history": {
                    "current_id": user_msg_id,
                    "messages": {user_msg_id: user_message},
                },
            }
        }
        resp = requests.post(f"{BASE_URL}/api/v1/chats/new", json=chat_payload, headers=self.headers)
        assert resp.status_code == 200, f"Chat creation failed: {resp.text}"
        chat_id = resp.json().get("id")
        assert chat_id, f"No chat ID in response: {resp.text}"

        assistant_msg_id = str(uuid.uuid4())
        assistant_message = {
            "id": assistant_msg_id,
            "role": "assistant",
            "content": "",
            "parentId": user_msg_id,
            "modelName": MODEL,
            "modelIdx": 0,
            "timestamp": now_ms,
            "models": [MODEL],
        }

        get_resp = requests.get(f"{BASE_URL}/api/v1/chats/{chat_id}", headers=self.headers)
        assert get_resp.status_code == 200
        chat_data = get_resp.json()
        chat_data.setdefault("messages", []).append(assistant_message)
        chat_data.setdefault("history", {}).setdefault("messages", {})[assistant_msg_id] = assistant_message
        chat_data["history"]["current_id"] = assistant_msg_id
        inject_resp = requests.post(f"{BASE_URL}/api/v1/chats/{chat_id}", json=chat_data, headers=self.headers)
        assert inject_resp.status_code == 200, f"Inject failed: {inject_resp.text}"

        session_id = str(uuid.uuid4())
        completion_payload = {
            "chat_id": chat_id,
            "id": assistant_msg_id,
            "messages": [{"role": "user", "content": user_message["content"]}],
            "model": MODEL,
            "stream": False,
            "session_id": session_id,
            "background_tasks": {"title_generation": True, "tags_generation": False, "follow_up_generation": True},
            "features": {"code_interpreter": False, "web_search": False, "image_generation": False, "memory": False},
            "variables": {
                "{{USER_NAME}}": "",
                "{{USER_LANGUAGE}}": "es-ES",
                "{{CURRENT_DATETIME}}": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "{{CURRENT_TIMEZONE}}": "America/Santiago",
            },
        }
        comp_resp = requests.post(f"{BASE_URL}/api/chat/completions", json=completion_payload, headers=self.headers)
        assert comp_resp.status_code == 200, f"Completion failed: {comp_resp.text}"

        completed_payload = {
            "chat_id": chat_id,
            "id": assistant_msg_id,
            "session_id": session_id,
            "model": MODEL,
        }
        done_resp = requests.post(f"{BASE_URL}/api/chat/completed", json=completed_payload, headers=self.headers)
        assert done_resp.status_code == 200, f"Completed failed: {done_resp.text}"

        fetch_resp = requests.get(f"{BASE_URL}/api/v1/chats/{chat_id}", headers=self.headers)
        assert fetch_resp.status_code == 200
        final_chat = fetch_resp.json()
        inner = final_chat.get("chat", final_chat)
        history_msgs = list((inner.get("history", {}) or {}).get("messages", {}).values())
        assert len(history_msgs) >= 2, "Expected at least 2 messages"
        roles = [m.get("role") for m in history_msgs]
        assert "user" in roles, "User message not found"
        assert "assistant" in roles, "Assistant message not found"

        chat_user_id = final_chat.get("user_id")
        if chat_user_id:
            assert chat_user_id == self.user["user_id"], (
                f"Chat user_id {chat_user_id} does not match provisioned user {self.user['user_id']}"
            )

    def test_us2_multi_turn_conversation(self):
        """US2: Send first message, send follow-up with chat_id, verify both exchanges."""
        now_ms = int(time.time() * 1000)
        user_msg_id = str(uuid.uuid4())

        user_message = {
            "id": user_msg_id,
            "role": "user",
            "content": "Hola, ¿qué productos tienen?",
            "timestamp": now_ms,
            "models": [MODEL],
        }
        chat_payload = {
            "chat": {
                "title": "Multi-Turn Test",
                "models": [MODEL],
                "messages": [user_message],
                "history": {
                    "current_id": user_msg_id,
                    "messages": {user_msg_id: user_message},
                },
            }
        }
        resp = requests.post(f"{BASE_URL}/api/v1/chats/new", json=chat_payload, headers=self.headers)
        assert resp.status_code == 200, f"First chat creation failed: {resp.text}"
        chat_id = resp.json().get("id")
        assert chat_id

        assistant_msg_id = str(uuid.uuid4())
        assistant_message = {
            "id": assistant_msg_id, "role": "assistant", "content": "",
            "parentId": user_msg_id, "modelName": MODEL, "modelIdx": 0,
            "timestamp": now_ms, "models": [MODEL],
        }
        get_resp = requests.get(f"{BASE_URL}/api/v1/chats/{chat_id}", headers=self.headers)
        chat_data = get_resp.json()
        chat_data.setdefault("messages", []).append(assistant_message)
        chat_data.setdefault("history", {}).setdefault("messages", {})[assistant_msg_id] = assistant_message
        chat_data["history"]["current_id"] = assistant_msg_id
        requests.post(f"{BASE_URL}/api/v1/chats/{chat_id}", json=chat_data, headers=self.headers)

        session_id = str(uuid.uuid4())
        comp_payload = {
            "chat_id": chat_id, "id": assistant_msg_id,
            "messages": [{"role": "user", "content": user_message["content"]}],
            "model": MODEL, "stream": False, "session_id": session_id,
            "background_tasks": {"title_generation": True, "tags_generation": False, "follow_up_generation": True},
            "features": {"code_interpreter": False, "web_search": False, "image_generation": False, "memory": False},
            "variables": {
                "{{USER_NAME}}": "", "{{USER_LANGUAGE}}": "es-ES",
                "{{CURRENT_DATETIME}}": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "{{CURRENT_TIMEZONE}}": "America/Santiago",
            },
        }
        requests.post(f"{BASE_URL}/api/chat/completions", json=comp_payload, headers=self.headers)
        requests.post(f"{BASE_URL}/api/chat/completed", json={"chat_id": chat_id, "id": assistant_msg_id, "session_id": session_id, "model": MODEL}, headers=self.headers)

        follow_user_msg_id = str(uuid.uuid4())
        follow_msg = {
            "id": follow_user_msg_id, "role": "user",
            "content": "¿Tienen auriculares inalámbricos?",
            "parentId": assistant_msg_id,
            "timestamp": int(time.time() * 1000), "models": [MODEL],
        }

        get_resp2 = requests.get(f"{BASE_URL}/api/v1/chats/{chat_id}", headers=self.headers)
        chat_data2 = get_resp2.json()
        chat_data2.setdefault("messages", []).append(follow_msg)
        chat_data2.setdefault("history", {}).setdefault("messages", {})[follow_user_msg_id] = follow_msg
        chat_data2["history"]["current_id"] = follow_user_msg_id
        requests.post(f"{BASE_URL}/api/v1/chats/{chat_id}", json=chat_data2, headers=self.headers)

        follow_assistant_id = str(uuid.uuid4())
        follow_assistant_msg = {
            "id": follow_assistant_id, "role": "assistant", "content": "",
            "parentId": follow_user_msg_id, "modelName": MODEL, "modelIdx": 0,
            "timestamp": int(time.time() * 1000), "models": [MODEL],
        }
        get_resp3 = requests.get(f"{BASE_URL}/api/v1/chats/{chat_id}", headers=self.headers)
        chat_data3 = get_resp3.json()
        chat_data3.setdefault("messages", []).append(follow_assistant_msg)
        chat_data3.setdefault("history", {}).setdefault("messages", {})[follow_assistant_id] = follow_assistant_msg
        chat_data3["history"]["current_id"] = follow_assistant_id
        requests.post(f"{BASE_URL}/api/v1/chats/{chat_id}", json=chat_data3, headers=self.headers)

        comp_payload2 = {
            "chat_id": chat_id, "id": follow_assistant_id,
            "messages": [
                {"role": "user", "content": user_message["content"]},
                {"role": "assistant", "content": ""},
                {"role": "user", "content": follow_msg["content"]},
            ],
            "model": MODEL, "stream": False, "session_id": session_id,
            "background_tasks": {"title_generation": True, "tags_generation": False, "follow_up_generation": True},
            "features": {"code_interpreter": False, "web_search": False, "image_generation": False, "memory": False},
            "variables": {
                "{{USER_NAME}}": "", "{{USER_LANGUAGE}}": "es-ES",
                "{{CURRENT_DATETIME}}": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "{{CURRENT_TIMEZONE}}": "America/Santiago",
            },
        }
        requests.post(f"{BASE_URL}/api/chat/completions", json=comp_payload2, headers=self.headers)
        requests.post(f"{BASE_URL}/api/chat/completed", json={"chat_id": chat_id, "id": follow_assistant_id, "session_id": session_id, "model": MODEL}, headers=self.headers)

        final_resp = requests.get(f"{BASE_URL}/api/v1/chats/{chat_id}", headers=self.headers)
        assert final_resp.status_code == 200
        final_chat = final_resp.json()
        inner = final_chat.get("chat", final_chat)
        messages = list((inner.get("history", {}) or {}).get("messages", {}).values())
        assert len(messages) >= 4, f"Expected at least 4 messages (2 exchanges), got {len(messages)}"
        roles = [m.get("role") for m in messages]
        assert roles.count("user") >= 2, "Expected at least 2 user messages"
        assert roles.count("assistant") >= 2, "Expected at least 2 assistant messages"

    def test_us3_tenant_config_and_tools(self):
        """US3: Create chat with tenant config containing system prompt and verify tool_ids are passed."""
        now_ms = int(time.time() * 1000)
        user_msg_id = str(uuid.uuid4())

        system_msg_id = str(uuid.uuid4())
        system_message = {
            "id": system_msg_id,
            "role": "user",
            "content": "Eres un asistente de ventas. Responde en español.",
            "timestamp": now_ms,
            "models": [MODEL],
        }
        user_message = {
            "id": user_msg_id,
            "role": "user",
            "content": "Muéstrame productos disponibles",
            "timestamp": now_ms,
            "models": [MODEL],
        }

        chat_payload = {
            "chat": {
                "title": "Tenant Config Test",
                "models": [MODEL],
                "messages": [system_message, user_message],
                "history": {
                    "current_id": user_msg_id,
                    "messages": {
                        system_msg_id: system_message,
                        user_msg_id: user_message,
                    },
                },
            }
        }
        resp = requests.post(f"{BASE_URL}/api/v1/chats/new", json=chat_payload, headers=self.headers)
        assert resp.status_code == 200, f"Chat creation failed: {resp.text}"
        chat_id = resp.json().get("id")
        assert chat_id

        assistant_msg_id = str(uuid.uuid4())
        assistant_message = {
            "id": assistant_msg_id, "role": "assistant", "content": "",
            "parentId": user_msg_id, "modelName": MODEL, "modelIdx": 0,
            "timestamp": now_ms, "models": [MODEL],
        }
        get_resp = requests.get(f"{BASE_URL}/api/v1/chats/{chat_id}", headers=self.headers)
        chat_data = get_resp.json()
        chat_data.setdefault("messages", []).append(assistant_message)
        chat_data.setdefault("history", {}).setdefault("messages", {})[assistant_msg_id] = assistant_message
        chat_data["history"]["current_id"] = assistant_msg_id
        requests.post(f"{BASE_URL}/api/v1/chats/{chat_id}", json=chat_data, headers=self.headers)

        session_id = str(uuid.uuid4())
        comp_payload = {
            "chat_id": chat_id, "id": assistant_msg_id,
            "messages": [
                {"role": "user", "content": system_message["content"]},
                {"role": "user", "content": user_message["content"]},
            ],
            "model": MODEL, "stream": False, "session_id": session_id,
            "background_tasks": {"title_generation": True, "tags_generation": False, "follow_up_generation": True},
            "features": {"code_interpreter": False, "web_search": False, "image_generation": False, "memory": False},
            "variables": {
                "{{USER_NAME}}": "", "{{USER_LANGUAGE}}": "es-ES",
                "{{CURRENT_DATETIME}}": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "{{CURRENT_TIMEZONE}}": "America/Santiago",
            },
            "tool_ids": ["server:0"],
        }
        comp_resp = requests.post(f"{BASE_URL}/api/chat/completions", json=comp_payload, headers=self.headers)
        assert comp_resp.status_code == 200, f"Completion with tools failed: {comp_resp.text}"
        result = comp_resp.json()

        if "choices" in result and len(result["choices"]) > 0:
            msg = result["choices"][0].get("message", {})
            has_content = bool(msg.get("content"))
            has_tool_calls = bool(msg.get("tool_calls"))
            assert has_content or has_tool_calls, "Response should have content or tool_calls"

        requests.post(f"{BASE_URL}/api/chat/completed", json={
            "chat_id": chat_id, "id": assistant_msg_id, "session_id": session_id, "model": MODEL,
        }, headers=self.headers)

        final_resp = requests.get(f"{BASE_URL}/api/v1/chats/{chat_id}", headers=self.headers)
        assert final_resp.status_code == 200

    def test_us4_restart_resilience_continue_chat(self):
        """US4/T017: continue_chat works with a valid chat_id and no prior local state.

        Simulates a proxy restart by creating a chat directly via OWUI API (bypassing
        the proxy's chat management) and then verifying that continue_chat can pick it
        up using only the OWUI-stored history.
        """
        chat_id = _create_chat_with_exchange(
            self.headers,
            user_content="Hola, busco un teclado mecánico.",
            assistant_content="Hola! Tenemos varios modelos de teclados mecánicos disponibles.",
        )

        # Simulate restart: import continue_chat fresh with no local state
        from src.services.chat_management import continue_chat
        from src.client.openwebui_client import OpenWebUIClient

        owui_client = OpenWebUIClient()
        owui_client.session.headers.update({"Authorization": f"Bearer {self.user['token']}"})

        result = continue_chat(
            chat_id=chat_id,
            message_content="¿Cuánto cuestan?",
            assistant_id=MODEL,
            owui_client=owui_client,
        )

        assert result is not None, "continue_chat returned None — local state dependency not eliminated"
        assert result["chat_id"] == chat_id
        assert result["assistant_response"], "Expected non-empty assistant response"

        # Verify OWUI chat now has 4 messages (2 from setup + 2 from continue)
        fetch_resp = requests.get(f"{BASE_URL}/api/v1/chats/{chat_id}", headers=self.headers)
        assert fetch_resp.status_code == 200
        history = fetch_resp.json().get("chat", {}).get("history", {}).get("messages", {})
        assert len(history) >= 4, f"Expected ≥4 messages in history, got {len(history)}"

    def test_us1_session_isolation_distinct_chat_ids(self):
        """US1/T018: Two requests without chat_id for the same user return distinct chat_id values."""
        from src.services.chat_management import get_or_create_chat
        from src.client.openwebui_client import OpenWebUIClient

        owui_client = OpenWebUIClient()
        owui_client.session.headers.update({"Authorization": f"Bearer {self.user['token']}"})

        result1 = get_or_create_chat(
            user_id=self.user["user_id"],
            assistant_id=MODEL,
            message_content="Primera sesión: busco auriculares.",
            owui_client=owui_client,
        )
        result2 = get_or_create_chat(
            user_id=self.user["user_id"],
            assistant_id=MODEL,
            message_content="Segunda sesión: busco teclados.",
            owui_client=owui_client,
        )

        assert result1 is not None, "First get_or_create_chat returned None"
        assert result2 is not None, "Second get_or_create_chat returned None"
        assert result1["chat_id"] != result2["chat_id"], (
            "Both sessions returned the same chat_id — session reuse not eliminated"
        )
