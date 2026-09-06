"""OpenWebUI client wrapper.
Provides basic methods to call OpenWebUI REST endpoints.
"""

import os
import requests
from typing import Any, Dict

from src.utils.logger import logger


class AuthExpiredError(Exception):
    """Raised when Open Web UI rejects the bearer token (HTTP 401).

    Callers catch this to trigger a single lazy re-authentication + retry,
    instead of paying an upfront token-validation round-trip on every request.
    """


class UnknownModelError(Exception):
    """Raised when Open Web UI has no model with the requested id (HTTP 404).

    Callers map this to a client error naming the unknown model id.
    """


class OpenWebUIClient:
    def __init__(self, base_url: str = "http://localhost:3000"):
        self.base_url = base_url.rstrip("/")
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

    def create_user(
        self, name: str, email: str, password: str, profile_image_url: str = "/user.png"
    ) -> Dict[str, Any]:
        resp = self._post(
            "/api/v1/auths/signup",
            {
                "name": name,
                "email": email,
                "password": password,
                "profile_image_url": profile_image_url,
            },
        )
        token = resp.get("token")
        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        return resp

    def login(self, email: str, password: str) -> Dict[str, Any]:
        resp = self._post(
            "/api/v1/auths/signin",
            {
                "email": email,
                "password": password,
            },
        )
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

    def get_model_tool_ids(self, model_id: str, token: str, timeout: int = 10) -> list:
        """Return the tool ids configured on the model in Open Web UI.

        Calls ``GET /api/v1/models/model?id=<model_id>`` with the given bearer
        token and reads ``meta.toolIds``. Used so the chat endpoint resolves
        tools live instead of reading them from a JSON config file.

        Raises ``UnknownModelError`` when the model does not exist (HTTP 404)
        and ``AuthExpiredError`` when the token is rejected (HTTP 401). On
        timeout/network failure logs a warning and returns ``[]`` so the caller
        can proceed (built-in tools still apply).
        """
        url = f"{self.base_url}/api/v1/models/model"
        self.round_trips += 1
        try:
            resp = self.session.get(
                url,
                params={"id": model_id},
                headers={"Authorization": f"Bearer {token}"},
                timeout=timeout,
            )
        except requests.RequestException as exc:
            logger.warning("Model tool lookup failed for %s: %s", model_id, exc)
            return []
        if resp.status_code == 404:
            raise UnknownModelError(f"Open WebUI has no model '{model_id}'")
        self._check_auth(resp)
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError:
            return []
        meta = data.get("meta", {}) if isinstance(data, dict) else {}
        tool_ids = meta.get("toolIds", []) if isinstance(meta, dict) else []
        return list(tool_ids) if isinstance(tool_ids, list) else []

    @staticmethod
    def _chat_inner(chat_response: Dict[str, Any]) -> Dict[str, Any]:
        return (
            chat_response.get("chat", chat_response)
            if isinstance(chat_response, dict)
            else chat_response
        )

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
