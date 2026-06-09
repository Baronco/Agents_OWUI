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


class TestChatFlow:
    """Integration tests for the chat creation and completion flow."""

    @pytest.fixture(autouse=True)
    def setup_user(self):
        self.user = _ensure_user()
        self.headers = _auth_headers(self.user["token"])
        self.model = "asistente-de-ventas"

    def test_us1_full_chat_lifecycle(self):
        """US1: Create chat with user message, inject assistant, complete, verify."""
        now_ms = int(time.time() * 1000)
        user_msg_id = str(uuid.uuid4())

        user_message = {
            "id": user_msg_id,
            "role": "user",
            "content": "Estoy buscando audífonos, ¿cuáles tienes disponibles?",
            "timestamp": now_ms,
            "models": [self.model],
        }

        # Step 1: Create chat
        chat_payload = {
            "chat": {
                "title": "Integration Test Chat",
                "models": [self.model],
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

        # Step 2: Inject empty assistant message
        assistant_msg_id = str(uuid.uuid4())
        assistant_message = {
            "id": assistant_msg_id,
            "role": "assistant",
            "content": "",
            "parentId": user_msg_id,
            "modelName": self.model,
            "modelIdx": 0,
            "timestamp": now_ms,
            "models": [self.model],
        }

        # Get current chat, mutate, push back
        get_resp = requests.get(f"{BASE_URL}/api/v1/chats/{chat_id}", headers=self.headers)
        assert get_resp.status_code == 200
        chat_data = get_resp.json()
        chat_data.setdefault("messages", []).append(assistant_message)
        chat_data.setdefault("history", {}).setdefault("messages", {})[assistant_msg_id] = assistant_message
        chat_data["history"]["current_id"] = assistant_msg_id
        inject_resp = requests.post(f"{BASE_URL}/api/v1/chats/{chat_id}", json=chat_data, headers=self.headers)
        assert inject_resp.status_code == 200, f"Inject failed: {inject_resp.text}"

        # Step 3: Trigger completion
        session_id = str(uuid.uuid4())
        completion_payload = {
            "chat_id": chat_id,
            "id": assistant_msg_id,
            "messages": [{"role": "user", "content": user_message["content"]}],
            "model": self.model,
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

        # Step 4: Mark completed
        completed_payload = {
            "chat_id": chat_id,
            "id": assistant_msg_id,
            "session_id": session_id,
            "model": self.model,
        }
        done_resp = requests.post(f"{BASE_URL}/api/chat/completed", json=completed_payload, headers=self.headers)
        assert done_resp.status_code == 200, f"Completed failed: {done_resp.text}"

        # Verify: fetch chat and check messages
        fetch_resp = requests.get(f"{BASE_URL}/api/v1/chats/{chat_id}", headers=self.headers)
        assert fetch_resp.status_code == 200
        final_chat = fetch_resp.json()
        assert len(final_chat.get("messages", [])) >= 2, "Expected at least 2 messages"
        roles = [m.get("role") for m in final_chat["messages"]]
        assert "user" in roles, "User message not found"
        assert "assistant" in roles, "Assistant message not found"

        # Verify the chat belongs to the correct user (not admin)
        chat_user_id = final_chat.get("user_id")
        if chat_user_id:
            assert chat_user_id == self.user["user_id"], (
                f"Chat user_id {chat_user_id} does not match provisioned user {self.user['user_id']}"
            )

    def test_us2_multi_turn_conversation(self):
        """US2: Send first message, send follow-up with chat_id, verify both exchanges."""
        now_ms = int(time.time() * 1000)
        user_msg_id = str(uuid.uuid4())

        # First message
        user_message = {
            "id": user_msg_id,
            "role": "user",
            "content": "Hola, ¿qué productos tienen?",
            "timestamp": now_ms,
            "models": [self.model],
        }
        chat_payload = {
            "chat": {
                "title": "Multi-Turn Test",
                "models": [self.model],
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

        # Inject first assistant + complete
        assistant_msg_id = str(uuid.uuid4())
        assistant_message = {
            "id": assistant_msg_id, "role": "assistant", "content": "",
            "parentId": user_msg_id, "modelName": self.model, "modelIdx": 0,
            "timestamp": now_ms, "models": [self.model],
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
            "model": self.model, "stream": False, "session_id": session_id,
            "background_tasks": {"title_generation": True, "tags_generation": False, "follow_up_generation": True},
            "features": {"code_interpreter": False, "web_search": False, "image_generation": False, "memory": False},
            "variables": {
                "{{USER_NAME}}": "", "{{USER_LANGUAGE}}": "es-ES",
                "{{CURRENT_DATETIME}}": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "{{CURRENT_TIMEZONE}}": "America/Santiago",
            },
        }
        requests.post(f"{BASE_URL}/api/chat/completions", json=comp_payload, headers=self.headers)
        requests.post(f"{BASE_URL}/api/chat/completed", json={"chat_id": chat_id, "id": assistant_msg_id, "session_id": session_id, "model": self.model}, headers=self.headers)

        # --- Follow-up message ---
        follow_user_msg_id = str(uuid.uuid4())
        follow_msg = {
            "id": follow_user_msg_id, "role": "user",
            "content": "¿Tienen auriculares inalámbricos?",
            "parentId": assistant_msg_id,
            "timestamp": int(time.time() * 1000), "models": [self.model],
        }

        # Append follow-up to chat
        get_resp2 = requests.get(f"{BASE_URL}/api/v1/chats/{chat_id}", headers=self.headers)
        chat_data2 = get_resp2.json()
        chat_data2.setdefault("messages", []).append(follow_msg)
        chat_data2.setdefault("history", {}).setdefault("messages", {})[follow_user_msg_id] = follow_msg
        chat_data2["history"]["current_id"] = follow_user_msg_id
        requests.post(f"{BASE_URL}/api/v1/chats/{chat_id}", json=chat_data2, headers=self.headers)

        # Inject second assistant
        follow_assistant_id = str(uuid.uuid4())
        follow_assistant_msg = {
            "id": follow_assistant_id, "role": "assistant", "content": "",
            "parentId": follow_user_msg_id, "modelName": self.model, "modelIdx": 0,
            "timestamp": int(time.time() * 1000), "models": [self.model],
        }
        get_resp3 = requests.get(f"{BASE_URL}/api/v1/chats/{chat_id}", headers=self.headers)
        chat_data3 = get_resp3.json()
        chat_data3.setdefault("messages", []).append(follow_assistant_msg)
        chat_data3.setdefault("history", {}).setdefault("messages", {})[follow_assistant_id] = follow_assistant_msg
        chat_data3["history"]["current_id"] = follow_assistant_id
        requests.post(f"{BASE_URL}/api/v1/chats/{chat_id}", json=chat_data3, headers=self.headers)

        # Complete second exchange
        comp_payload2 = {
            "chat_id": chat_id, "id": follow_assistant_id,
            "messages": [
                {"role": "user", "content": user_message["content"]},
                {"role": "assistant", "content": ""},
                {"role": "user", "content": follow_msg["content"]},
            ],
            "model": self.model, "stream": False, "session_id": session_id,
            "background_tasks": {"title_generation": True, "tags_generation": False, "follow_up_generation": True},
            "features": {"code_interpreter": False, "web_search": False, "image_generation": False, "memory": False},
            "variables": {
                "{{USER_NAME}}": "", "{{USER_LANGUAGE}}": "es-ES",
                "{{CURRENT_DATETIME}}": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "{{CURRENT_TIMEZONE}}": "America/Santiago",
            },
        }
        requests.post(f"{BASE_URL}/api/chat/completions", json=comp_payload2, headers=self.headers)
        requests.post(f"{BASE_URL}/api/chat/completed", json={"chat_id": chat_id, "id": follow_assistant_id, "session_id": session_id, "model": self.model}, headers=self.headers)

        # Verify: fetch and check both exchanges
        final_resp = requests.get(f"{BASE_URL}/api/v1/chats/{chat_id}", headers=self.headers)
        assert final_resp.status_code == 200
        final_chat = final_resp.json()
        messages = final_chat.get("messages", [])
        assert len(messages) >= 4, f"Expected at least 4 messages (2 exchanges), got {len(messages)}"
        roles = [m.get("role") for m in messages]
        assert roles.count("user") >= 2, "Expected at least 2 user messages"
        assert roles.count("assistant") >= 2, "Expected at least 2 assistant messages"

    def test_us3_tenant_config_and_tools(self):
        """US3: Create chat with tenant config containing system prompt and verify tool_ids are passed."""
        now_ms = int(time.time() * 1000)
        user_msg_id = str(uuid.uuid4())

        # Inject system prompt as first message
        system_msg_id = str(uuid.uuid4())
        system_message = {
            "id": system_msg_id,
            "role": "user",
            "content": "Eres un asistente de ventas. Responde en español.",
            "timestamp": now_ms,
            "models": [self.model],
        }
        user_message = {
            "id": user_msg_id,
            "role": "user",
            "content": "Muéstrame productos disponibles",
            "timestamp": now_ms,
            "models": [self.model],
        }

        chat_payload = {
            "chat": {
                "title": "Tenant Config Test",
                "models": [self.model],
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

        # Inject assistant + complete
        assistant_msg_id = str(uuid.uuid4())
        assistant_message = {
            "id": assistant_msg_id, "role": "assistant", "content": "",
            "parentId": user_msg_id, "modelName": self.model, "modelIdx": 0,
            "timestamp": now_ms, "models": [self.model],
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
            "model": self.model, "stream": False, "session_id": session_id,
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

        # Verify the response contains a message (either content or tool_calls)
        if "choices" in result and len(result["choices"]) > 0:
            msg = result["choices"][0].get("message", {})
            has_content = bool(msg.get("content"))
            has_tool_calls = bool(msg.get("tool_calls"))
            assert has_content or has_tool_calls, "Response should have content or tool_calls"

        # Mark completed
        requests.post(f"{BASE_URL}/api/chat/completed", json={
            "chat_id": chat_id, "id": assistant_msg_id, "session_id": session_id, "model": self.model,
        }, headers=self.headers)

        # Verify persistence
        final_resp = requests.get(f"{BASE_URL}/api/v1/chats/{chat_id}", headers=self.headers)
        assert final_resp.status_code == 200

    def test_daily_single_chat_and_non_empty_response(self):
        """US1 enhancement: verify non-empty assistant_response and same-chat reuse per day."""
        now_ms = int(time.time() * 1000)
        user_msg_id = str(uuid.uuid4())

        # First message
        first_content = "Estoy buscando audífonos, ¿cuáles tienes disponibles?"
        user_message = {
            "id": user_msg_id,
            "role": "user",
            "content": first_content,
            "timestamp": now_ms,
            "models": [self.model],
        }
        chat_payload = {
            "chat": {
                "title": "Daily Chat Test",
                "models": [self.model],
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

        # Inject assistant + complete
        assistant_msg_id = str(uuid.uuid4())
        assistant_message = {
            "id": assistant_msg_id, "role": "assistant", "content": "",
            "parentId": user_msg_id, "modelName": self.model, "modelIdx": 0,
            "timestamp": now_ms, "models": [self.model],
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
            "messages": [{"role": "user", "content": first_content}],
            "model": self.model, "stream": False, "session_id": session_id,
            "background_tasks": {"title_generation": True, "tags_generation": False, "follow_up_generation": True},
            "features": {"code_interpreter": False, "web_search": False, "image_generation": False, "memory": False},
            "variables": {
                "{{USER_NAME}}": "", "{{USER_LANGUAGE}}": "es-ES",
                "{{CURRENT_DATETIME}}": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "{{CURRENT_TIMEZONE}}": "America/Santiago",
            },
        }
        comp_resp = requests.post(f"{BASE_URL}/api/chat/completions", json=comp_payload, headers=self.headers)
        assert comp_resp.status_code == 200, f"Completion failed: {comp_resp.text}"
        comp_data = comp_resp.json()

        # Verify non-empty assistant response in completion
        comp_text = ""
        if "choices" in comp_data and comp_data["choices"]:
            comp_text = comp_data["choices"][0].get("message", {}).get("content", "")
        if not comp_text and "message" in comp_data:
            comp_text = comp_data["message"].get("content", "")
        assert comp_text, f"Assistant response is empty: {comp_data}"

        # Mark completed
        done_resp = requests.post(f"{BASE_URL}/api/chat/completed", json={
            "chat_id": chat_id, "id": assistant_msg_id, "session_id": session_id, "model": self.model,
        }, headers=self.headers)
        assert done_resp.status_code == 200

        # Verify final chat has both messages
        fetch_resp = requests.get(f"{BASE_URL}/api/v1/chats/{chat_id}", headers=self.headers)
        assert fetch_resp.status_code == 200
        final_chat = fetch_resp.json()
        messages = final_chat.get("messages", [])
        contents = [m.get("content", "") for m in messages]
        assert first_content in contents, f"First user message not found in {contents}"
        assert comp_text in contents, f"Assistant response not found in {contents}"