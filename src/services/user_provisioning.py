"""User provisioning service.
Creates or reuses a non‑admin OpenWebUI user via the client.
"""
from typing import Dict, Optional

import requests

from src.client.openwebui_client import OpenWebUIClient
from src.utils.logger import logger

_default_client = OpenWebUIClient()

# In‑memory cache for demo purposes
_user_cache: Dict[str, Dict[str, str]] = {}

def _generate_email(username: str, tenant_id: str) -> str:
    return f"{username}_{tenant_id}@proxy.local"

def _generate_password() -> str:
    # Simple placeholder – replace with secure generation
    return "ChangeMe123!"

def provision_user(
    username: str,
    tenant_id: str,
    owui_client: Optional[OpenWebUIClient] = None,
) -> Optional[Dict[str, str]]:
    """Provision a non‑admin OpenWebUI user or reuse an existing one.
    Returns a dict with at least ``user_id``.
    """
    c = owui_client if owui_client is not None else _default_client
    cache_key = f"{username}:{tenant_id}"
    if cache_key in _user_cache:
        logger.info("Reusing existing provisioned user for %s", cache_key)
        return _user_cache[cache_key]

    email = _generate_email(username, tenant_id)
    password = _generate_password()
    try:
        try:
            resp = c.create_user(name=username, email=email, password=password)
        except requests.HTTPError as signup_err:
            if signup_err.response.status_code == 400:
                logger.info("User already exists for %s, falling back to login", cache_key)
                resp = c.login(email=email, password=password)
            else:
                raise
        user_id = resp.get("user_id") or resp.get("id")
        if not user_id:
            logger.error("OpenWebUI response missing user identifier: %s", resp)
            return None
        user_info = {"user_id": user_id, "email": email, "password": password}
        _user_cache[cache_key] = user_info
        logger.info("Provisioned new OpenWebUI user %s for %s", user_id, cache_key)
        return user_info
    except Exception as exc:
        logger.error("Failed to provision user %s: %s", cache_key, exc)
        return None
