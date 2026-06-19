"""User provisioning service.

Provisions non-admin OpenWebUI users and caches their JWT tokens to disk —
ONE file per user under ``USERS_DIR`` (spec 011), keyed by
``(client_phone, tenant_id)``. A request reads/writes only its own user's
file, so different users never contend (the single-file ``token_store.json``
+ one global lock is gone).

- Token is reused until TOKEN_EXPIRY_SECONDS elapses; then re-auth triggers
  is_new_session=True.
- Per-user access is serialized by a per-user lock here; the same user's
  concurrent requests are additionally serialized upstream by the proxy's
  per-(client_phone, tenant_id) request lock (spec 010).
"""
from typing import Dict, Optional
import os
import re
import json
import time
import threading
import hmac
import hashlib
from pathlib import Path

import requests

from src.client.openwebui_client import OpenWebUIClient
from src.config import users_dir
from src.utils.logger import logger

# Per-user locks: different users don't contend; one small guard protects the
# registry itself (same pattern as api.py's _user_locks).
_locks: Dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()

_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _user_lock(email: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(email)
        if lock is None:
            lock = threading.Lock()
            _locks[email] = lock
        return lock


def _expiry_seconds() -> int:
    try:
        return int(os.getenv("TOKEN_EXPIRY_SECONDS", "3500"))
    except ValueError:
        return 3500


def _user_file(email: str) -> Path:
    """Path to this user's token file: ``USERS_DIR/<sanitized-email>.json``."""
    return users_dir() / f"{_SAFE.sub('-', email)}.json"


def _load_user(email: str) -> dict:
    """Return this user's cached data, or {} if missing/unreadable.

    A corrupt file affects only this one user (treated as 'not provisioned').
    """
    try:
        with open(_user_file(email), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_user(email: str, data: dict) -> None:
    """Atomically write this user's token file (temp file + os.replace)."""
    directory = users_dir()
    try:
        os.makedirs(directory, exist_ok=True)
        path = _user_file(email)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except OSError as e:
        logger.error("Failed to write token file for %s: %s", email, e)


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

    with _user_lock(email):
        entry = _load_user(email)
        if entry and not force and time.time() < entry.get("expires_at", 0):
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
            # Preserve any existing chat mappings for this user.
            entry = {**entry, "user_id": user_id, "token": token, "expires_at": expires_at}
            _save_user(email, entry)
            logger.info("Provisioned and cached token for %s (expires_at=%.0f)", client_phone, expires_at)
            return {"user_id": user_id, "email": email, "token": token, "is_new_session": True}

        except Exception as exc:
            logger.error("Failed to provision user %s: %s", client_phone, exc)
            return None


def get_owui_chat_id(email: str, external_chat_id: str) -> Optional[str]:
    """Return the OWUI chat_id mapped to the given external chat_id, or None."""
    with _user_lock(email):
        entry = _load_user(email)
        if not entry:
            return None
        for mapping in entry.get("chats", []):
            if mapping.get("external_chat_id") == external_chat_id:
                return mapping.get("owui_chat_id")
        return None


def store_chat_mapping(email: str, external_chat_id: str, owui_chat_id: str) -> None:
    """Persist the mapping between an external chat_id and the OWUI chat_id."""
    with _user_lock(email):
        entry = _load_user(email)
        if not entry:
            return
        chats = entry.setdefault("chats", [])
        for mapping in chats:
            if mapping.get("external_chat_id") == external_chat_id:
                mapping["owui_chat_id"] = owui_chat_id
                _save_user(email, entry)
                return
        chats.append({"external_chat_id": external_chat_id, "owui_chat_id": owui_chat_id})
        _save_user(email, entry)
