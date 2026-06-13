"""OpenWebUI client wrapper.
Provides basic methods to call OpenWebUI REST endpoints.
"""
import os
import requests
from typing import Any, Dict, Optional


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

    def login(self, email: str, password: str) -> Dict[str, Any]:
        resp = self._post("/api/v1/auths/signin", {
            "email": email,
            "password": password,
        })
        token = resp.get("token")
        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        return resp

    def get_chat(self, chat_id: str) -> Dict[str, Any]:
        resp = self.session.get(f"{self.base_url}/api/v1/chats/{chat_id}")
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _chat_inner(chat_response: Dict[str, Any]) -> Dict[str, Any]:
        return chat_response.get("chat", chat_response) if isinstance(chat_response, dict) else chat_response

    def with_token(self, token: str) -> "OpenWebUIClient":
        """Return a new client instance authenticated with the given bearer token."""
        new_client = OpenWebUIClient(self.base_url)
        new_client.session.headers.update({"Authorization": f"Bearer {token}"})
        return new_client

    def chat_completion(self, payload: dict) -> Dict[str, Any]:
        """Call /api/chat/completions (OpenAI-compatible direct endpoint)."""
        return self._post("/api/chat/completions", payload)

    def chat_completion_sync(self, payload: dict) -> Dict[str, Any]:
        """POST /api/chat/completions and return the JSON response.

        When chat_id is included, OWUI processes the request asynchronously and
        returns {status: True, task_ids: [...]}. The caller must poll the chat
        history to read the completed assistant message.
        """
        url = f"{self.base_url}/api/chat/completions"
        resp = self.session.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()
