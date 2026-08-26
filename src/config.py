"""Configuration handling for the proxy.
Loads environment variables and provides defaults.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def get_env(key: str, default: str = "") -> str:
    return os.getenv(key, default)

# Example configuration values
OPENWEBUI_BASE_URL = get_env("OPENWEBUI_BASE_URL", "http://localhost:3000")


def tenants_config_path() -> Path:
    """Path to the tenant config file.

    Env-configurable (``TENANTS_CONFIG_PATH``) so the file can live on a
    mounted volume in Docker; defaults to ``<repo>/config/tenants.json`` for
    local runs. Resolved per call so a process started with a different env
    sees the right path (the loader re-reads on every request anyway).
    """
    override = os.getenv("TENANTS_CONFIG_PATH")
    return Path(override) if override else BASE_DIR / "config" / "tenants.json"


def users_dir() -> Path:
    """Directory holding per-user token files (one JSON per phone+tenant).

    Env-configurable (``USERS_DIR``) so it can live on a mounted volume in
    Docker; defaults to ``<repo>/users`` for local runs.
    """
    override = os.getenv("USERS_DIR")
    return Path(override) if override else BASE_DIR / "users"
