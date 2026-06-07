"""OpenWebUI client wrapper.
Provides basic methods to call OpenWebUI REST endpoints.
"""
import os
import requests
from typing import Any, Dict, List, Optional

class OpenWebUIClient:
    def __init__(self, base_url: str = "http://localhost:3000"):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        api_key = os.getenv("OWUI_API_KEY")
        if api_key:
            self.session.headers.update({"Authorization": f"Bearer {api_key}"})

    def _post(self, path: str, json: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        resp = self.session.post(url, json=json)
        resp.raise_for_status()
        return resp.json()

    def create_user(self, name: str, email: str, password: str, profile_image_url: str = "/user.png") -> Dict[str, Any]:
        resp = self._post("/api/v1/auths/signup", {
            "name": name,
            "email": email,
            "password": password,
            "profile_image_url": profile_image_url,
        })
        token = resp.get("token")
        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        return resp

    def create_chat(self) -> Dict[str, Any]:
        return self._post("/api/v1/chats/new", {})

    def get_chat(self, chat_id: str) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/api/v1/chats/{chat_id}", headers=self.session.headers)
        resp.raise_for_status()
        return resp.json()

    def create_chat_with_initial_message(
        self,
        user_id: str,
        title: str,
        model: str,
        user_message: dict,
        additional_messages: Optional[List[dict]] = None,
        additional_history: Optional[Dict[str, dict]] = None,
    ) -> Dict[str, Any]:
        messages = list(additional_messages) if additional_messages else [user_message]
        history_msgs = dict(additional_history) if additional_history else {}
        if user_message["id"] not in history_msgs:
            history_msgs[user_message["id"]] = user_message

        payload = {
            "chat": {
                "title": title,
                "models": [model],
                "messages": messages,
                "history": {
                    "current_id": user_message["id"],
                    "messages": history_msgs,
                },
                "user_id": user_id,
            }
        }
        return self._post("/api/v1/chats/new", payload)

    def inject_assistant_message(self, chat_id: str, assistant_message: dict) -> Dict[str, Any]:
        chat = self.get_chat(chat_id)
        chat.setdefault("messages", [])
        chat.setdefault("history", {}).setdefault("messages", {})
        chat["messages"].append(assistant_message)
        chat["history"]["messages"][assistant_message["id"]] = assistant_message
        chat["history"]["current_id"] = assistant_message["id"]
        return self._post(f"/api/v1/chats/{chat_id}", chat)

    def chat_completion(self, payload: dict) -> Dict[str, Any]:
        """Trigger assistant completion via POST /api/chat/completions."""
        return self._post("/api/chat/completions", payload)

    def complete_chat(self, chat_id: str, assistant_msg_id: str, session_id: str, model: str) -> Dict[str, Any]:
        payload = {
            "chat_id": chat_id,
            "id": assistant_msg_id,
            "session_id": session_id,
            "model": model,
        }
        return self._post("/api/chat/completed", payload)