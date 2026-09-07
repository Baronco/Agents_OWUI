"""Configuration handling for the proxy.
Loads environment variables and provides defaults.
"""

import os


def get_env(key: str, default: str = "") -> str:
    """Return the environment value for ``key`` or ``default`` when absent."""
    return os.getenv(key, default)


OPENWEBUI_BASE_URL = get_env("OPENWEBUI_BASE_URL", "http://localhost:3000")
