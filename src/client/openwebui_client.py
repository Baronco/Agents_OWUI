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
        resp = self._post("/api/v1/auths/login", {
            "email": email,
            "password": password,
        })
        token = resp.get("token")
        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        return resp

    def get_chat(self, chat_id: str) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/api/v1/chats/{chat_id}", headers=self.session.headers)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _chat_inner(chat_response: Dict[str, Any]) -> Dict[str, Any]:
        return chat_response.get("chat", chat_response) if isinstance(chat_response, dict) else chat_response

    def chat_completion(self, payload: dict) -> Dict[str, Any]:
        """Call /api/chat/completions (OpenAI-compatible direct endpoint)."""
        return self._post("/api/chat/completions", payload)
