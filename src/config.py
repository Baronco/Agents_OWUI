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
