"""Loads and validates the tenant/formatter configuration from a JSON file
(``config/tenants.json`` by default), replacing the Python-source constants
used before spec 009.

Read once, at import time of ``tenant_routing.py`` — see that module and
``specs/009-config-externalization/research.md`` (R3) for why. Any
``ConfigError`` raised here propagates uncaught through that import, so a
broken file fails the process at startup (spec 009, US3) instead of
degrading per-request.
"""
import json
from pathlib import Path
from typing import Optional

from src.config import BASE_DIR

_DEFAULT_PATH = BASE_DIR / "config" / "tenants.json"


class ConfigError(Exception):
    """Raised when ``config/tenants.json`` is missing, malformed, or invalid."""


def _tenant_entry(raw: dict, label: str, file_path: Path) -> dict:
    if "model" not in raw:
        raise ConfigError(
            f"{file_path}: tenant entry {label} is missing the required field 'model'."
        )
    return {
        "model": raw["model"],
        "tool_ids": raw.get("tool_ids", []),
        "title_generation": raw.get("title_generation", True),
    }


def _formatter_entry(raw: dict, file_path: Path) -> dict:
    if "model" not in raw:
        raise ConfigError(f"{file_path}: 'formatter' section is missing the required field 'model'.")
    tool_ids = raw.get("tool_ids", [])
    if not tool_ids:
        raise ConfigError(
            f"{file_path}: 'formatter' section requires a non-empty 'tool_ids' list "
            "(the formatter is useless without its tool)."
        )
    return {
        "model": raw["model"],
        "tool_ids": tool_ids,
        "title_generation": raw.get("title_generation", False),
    }


def load_config(path: Optional[str] = None) -> dict:
    """Load, parse, and validate the tenant/formatter config file.

    Returns ``{"tenants": {tenant_id: TenantConfig}, "formatter": TenantConfig}``.
    Raises ``ConfigError`` naming the file and the specific problem if the
    file is missing, not valid JSON, has a duplicate ``tenant_id``, or any
    entry is missing a required field.
    """
    file_path = Path(path) if path is not None else _DEFAULT_PATH

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_text = f.read()
    except FileNotFoundError:
        raise ConfigError(f"Tenant config file not found: {file_path}") from None

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{file_path}: invalid JSON ({exc}).") from exc

    if "formatter" not in data:
        raise ConfigError(f"{file_path}: missing required top-level 'formatter' section.")

    tenants: dict = {}
    for index, entry in enumerate(data.get("tenants", [])):
        if "tenant_id" not in entry:
            raise ConfigError(
                f"{file_path}: tenant entry at index {index} is missing the required field 'tenant_id'."
            )
        tenant_id = entry["tenant_id"]
        if tenant_id in tenants:
            raise ConfigError(f"{file_path}: duplicate tenant_id '{tenant_id}'.")
        tenants[tenant_id] = _tenant_entry(entry, label=f"'{tenant_id}'", file_path=file_path)

    formatter = _formatter_entry(data["formatter"], file_path=file_path)
    return {"tenants": tenants, "formatter": formatter}
