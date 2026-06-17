"""User provisioning service.
Provisions non-admin OpenWebUI users and caches their JWT tokens to a local
JSON file (TOKEN_CACHE_PATH).

- Token is reused until TOKEN_EXPIRY_SECONDS elapses; then re-auth triggers
  is_new_session=True.
- Chat session management is handled externally — chat_id is NOT cached here.
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


def _generate_email(client_phone: str, tenant_id: str) -> str:
    return f"{client_phone}_{tenant_id}@proxy.local"


def _generate_password(email: str) -> str:
    secret = os.getenv("USER_PASSWORD_SECRET", "")
    if not secret:
        raise RuntimeError("USER_PASSWORD_SECRET env var is required but not set")
    digest = hmac.new(secret.encode(), email.encode(), hashlib.sha256).hexdigest()
    return digest[:32]


def provision_user(
    client_phone: str,
    tenant_id: str,
    owui_client: OpenWebUIClient,
    force: bool = False,
) -> Optional[Dict[str, str]]:
    """Provision a non-admin OpenWebUI user.

    Returns a dict with user_id, email, token, and is_new_session.
    - is_new_session: True when re-auth occurred.

    The cached token is trusted while unexpired (no upfront validation
    round-trip). If the token is actually stale, the downstream OWUI call
    returns 401 and the caller re-invokes with ``force=True`` to re-authenticate
    and retry once.
    """
    email = _generate_email(client_phone, tenant_id)
    password = _generate_password(email)
    expiry_secs = _expiry_seconds()

    with _cache_lock:
        cache = _load_cache()
        entry = cache.get(email)
        if entry and not force and time.time() < entry["expires_at"]:
            logger.info("Reusing cached token for %s (expires in %.0fs)",
                        client_phone, entry["expires_at"] - time.time())
            return {
                "user_id": entry["user_id"],
                "email": email,
                "token": entry["token"],
                "is_new_session": False,
            }

        if entry and force:
            logger.info("Forced re-authentication for %s (token rejected by OWUI)", client_phone)
        elif entry:
            logger.info("Cached token for %s expired — re-authenticating", client_phone)

        try:
            try:
                resp = owui_client.create_user(name=client_phone, email=email, password=password)
            except requests.HTTPError as signup_err:
                if signup_err.response.status_code == 400:
                    logger.info("User %s already exists — falling back to signin", email)
                    resp = owui_client.login(email=email, password=password)
                else:
                    raise

            user_id = resp.get("user_id") or resp.get("id")
            token = resp.get("token")
            if not user_id or not token:
                logger.error("OpenWebUI response missing user_id or token for %s: %s", client_phone, list(resp.keys()))
                return None

            expires_at = time.time() + expiry_secs
            cache[email] = {"user_id": user_id, "token": token, "expires_at": expires_at}
            _save_cache(cache)
            logger.info("Provisioned and cached token for %s (expires_at=%.0f)", client_phone, expires_at)
            return {"user_id": user_id, "email": email, "token": token, "is_new_session": True}

        except Exception as exc:
            logger.error("Failed to provision user %s: %s", client_phone, exc)
            return None


def get_owui_chat_id(email: str, external_chat_id: str) -> Optional[str]:
    """Return the OWUI chat_id mapped to the given external chat_id, or None."""
    with _cache_lock:
        cache = _load_cache()
        entry = cache.get(email)
        if not entry:
            return None
        for mapping in entry.get("chats", []):
            if mapping.get("external_chat_id") == external_chat_id:
                return mapping.get("owui_chat_id")
        return None


def store_chat_mapping(email: str, external_chat_id: str, owui_chat_id: str) -> None:
    """Persist the mapping between an external chat_id and the OWUI chat_id."""
    with _cache_lock:
        cache = _load_cache()
        if email not in cache:
            return
        chats = cache[email].setdefault("chats", [])
        for mapping in chats:
            if mapping.get("external_chat_id") == external_chat_id:
                mapping["owui_chat_id"] = owui_chat_id
                _save_cache(cache)
                return
        chats.append({"external_chat_id": external_chat_id, "owui_chat_id": owui_chat_id})
        _save_cache(cache)
