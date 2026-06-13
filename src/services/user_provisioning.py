"""User provisioning service.
Provisions non-admin OpenWebUI users and caches their JWT tokens and active
chat_id to a local JSON file (TOKEN_CACHE_PATH).

- Token is reused until TOKEN_EXPIRY_SECONDS elapses; then re-auth triggers
  is_new_session=True so the caller starts a fresh chat.
- chat_id is stored alongside the token so the same conversation thread is
  resumed on every request within the same session.
"""
from typing import Dict, Optional
import os
import json
import time
import threading
import hmac
import hashlib
import requests

from src.client.openwebui_client import OpenWebUIClient
from src.utils.logger import logger

_cache_lock = threading.Lock()


def _cache_path() -> str:
    return os.getenv("TOKEN_CACHE_PATH", "./token_store.json")


def _expiry_seconds() -> int:
    try:
        return int(os.getenv("TOKEN_EXPIRY_SECONDS", "3500"))
    except ValueError:
        return 3500


def _load_cache() -> dict:
    path = _cache_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache(data: dict) -> None:
    path = _cache_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError as e:
        logger.error("Failed to write token cache to %s: %s", path, e)


def _generate_email(username: str, tenant_id: str) -> str:
    return f"{username}_{tenant_id}@proxy.local"


def _generate_password(email: str) -> str:
    secret = os.getenv("USER_PASSWORD_SECRET", "")
    if not secret:
        raise RuntimeError("USER_PASSWORD_SECRET env var is required but not set")
    digest = hmac.new(secret.encode(), email.encode(), hashlib.sha256).hexdigest()
    return digest[:32]


def _ping_token(owui_client: OpenWebUIClient, token: str) -> bool:
    """Return True if the token is accepted by OWUI (quick validation call)."""
    try:
        temp = owui_client.with_token(token)
        resp = temp.session.get(f"{owui_client.base_url}/api/v1/auths/", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def provision_user(
    username: str,
    tenant_id: str,
    owui_client: OpenWebUIClient,
) -> Optional[Dict[str, str]]:
    """Provision a non-admin OpenWebUI user.

    Returns a dict with user_id, email, token, chat_id, and is_new_session.
    - chat_id: last active chat for this user (None on first request or after
      token expiry); caller should use this to resume the conversation.
    - is_new_session: True when re-auth occurred; caller must start a new chat.
    """
    email = _generate_email(username, tenant_id)
    password = _generate_password(email)
    expiry_secs = _expiry_seconds()

    with _cache_lock:
        cache = _load_cache()
        entry = cache.get(email)
        if entry and time.time() < entry["expires_at"]:
            token_ok = _ping_token(owui_client, entry["token"])
            if token_ok:
                logger.info("Reusing cached token for %s (expires in %.0fs)",
                            email, entry["expires_at"] - time.time())
                return {
                    "user_id": entry["user_id"],
                    "email": email,
                    "token": entry["token"],
                    "chat_id": entry.get("chat_id"),
                    "is_new_session": False,
                }
            logger.info("Cached token for %s is rejected by OWUI — re-authenticating", email)
            entry = None  # force re-auth below

        if entry:
            logger.info("Cached token for %s expired — re-authenticating", email)

        try:
            try:
                resp = owui_client.create_user(name=username, email=email, password=password)
            except requests.HTTPError as signup_err:
                if signup_err.response.status_code == 400:
                    logger.info("User %s already exists — falling back to signin", email)
                    resp = owui_client.login(email=email, password=password)
                else:
                    raise

            user_id = resp.get("user_id") or resp.get("id")
            token = resp.get("token")
            if not user_id or not token:
                logger.error("OpenWebUI response missing user_id or token: %s", list(resp.keys()))
                return None

            expires_at = time.time() + expiry_secs
            cache[email] = {"user_id": user_id, "token": token, "expires_at": expires_at, "chat_id": None}
            _save_cache(cache)
            logger.info("Provisioned and cached token for %s (expires_at=%.0f)", email, expires_at)
            return {"user_id": user_id, "email": email, "token": token, "chat_id": None, "is_new_session": True}

        except Exception as exc:
            logger.error("Failed to provision user %s: %s", email, exc)
            return None


def update_cached_chat_id(email: str, chat_id: str) -> None:
    """Persist the active chat_id for this user so the next request can resume it."""
    with _cache_lock:
        cache = _load_cache()
        if email in cache:
            cache[email]["chat_id"] = chat_id
            _save_cache(cache)
