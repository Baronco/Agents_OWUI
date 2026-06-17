"""OpenWebUI client wrapper.
Provides basic methods to call OpenWebUI REST endpoints.
"""
import os
import requests
from typing import Any, Dict


class AuthExpiredError(Exception):
    """Raised when Open WebUI rejects the bearer token (HTTP 401).

    Callers catch this to trigger a single lazy re-authentication + retry,
    instead of paying an upfront token-validation round-trip on every request.
    """


class OpenWebUIClient:
    def __init__(self, base_url: str = "http://localhost:3000"):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        # Count of OWUI HTTP round-trips made by this (request-scoped) client.
        self.round_trips = 0
        api_key = os.getenv("OWUI_API_KEY")
        if api_key:
            self.session.headers.update({"Authorization": f"Bearer {api_key}"})

    def _check_auth(self, resp: requests.Response) -> None:
        if resp.status_code == 401:
            raise AuthExpiredError(f"OWUI rejected token for {resp.request.method} {resp.url}")

    def _post(self, path: str, json: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        self.round_trips += 1
        resp = self.session.post(url, json=json)
        self._check_auth(resp)
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
        self.round_trips += 1
        resp = self.session.get(f"{self.base_url}/api/v1/chats/{chat_id}")
        self._check_auth(resp)
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

    @staticmethod
    def _with_native_fc(payload: dict) -> dict:
        """Force native function calling whenever tools are requested.

        Without ``params.function_calling == "native"`` Open WebUI runs a
        separate prompt-based tool pre-pass — a full extra LLM round-trip on
        every message just to decide whether a tool is needed. Native FC passes
        the tool specs inline so the model decides in a single pass.
        See specs/005-reduce-api-latency/contracts/owui-completion.md.
        """
        if payload.get("tool_ids"):
            params = dict(payload.get("params") or {})
            params.setdefault("function_calling", "native")
            payload = {**payload, "params": params}
        return payload

    def chat_completion(self, payload: dict, timeout: int = 120) -> Dict[str, Any]:
        """POST /api/chat/completions (OpenAI-compatible) and return the JSON.

        Enables native function calling when ``tool_ids`` is present and counts
        the round-trip.
        """
        payload = self._with_native_fc(payload)
        url = f"{self.base_url}/api/chat/completions"
        self.round_trips += 1
        resp = self.session.post(url, json=payload, timeout=timeout)
        self._check_auth(resp)
        resp.raise_for_status()
        return resp.json()
