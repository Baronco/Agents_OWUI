"""Configuration handling for the proxy.
Loads environment variables and provides defaults.
"""

import os

from src.utils.logger import logger


def get_env(key: str, default: str = "") -> str:
    """Return the environment value for ``key`` or ``default`` when absent."""
    return os.getenv(key, default)


def parse_positive_int(raw: str, default: int) -> int:
    """Parse ``raw`` as a positive integer, falling back to ``default``.

    An empty, non-integer, or non-positive value logs a warning and returns
    ``default`` so a bad environment value never crashes startup.
    """
    text = (raw or "").strip()
    if not text:
        return default
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value <= 0:
        logger.warning("Invalid integer value %r — falling back to %d", raw, default)
        return default
    return value


OPENWEBUI_BASE_URL = get_env("OPENWEBUI_BASE_URL", "http://localhost:3000")

# Maximum number of sub-agents executed per POST /proxy/chat/batch call.
MAX_BATCH_SUBAGENTS_DEFAULT = 5
MAX_BATCH_SUBAGENTS = parse_positive_int(
    get_env("MAX_BATCH_SUBAGENTS", ""), MAX_BATCH_SUBAGENTS_DEFAULT
)
