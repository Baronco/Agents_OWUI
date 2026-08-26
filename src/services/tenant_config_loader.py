"""Loads and validates the tenant configuration from a JSON file
(``config/tenants.json`` by default), replacing the Python-source constants
used before spec 009.

Since spec 014 the schema contains only the tenant list: the former global
``formatter`` section is no longer required, and a legacy one is ignored with
a logged warning (never an error).

Read once, at import time of ``tenant_routing.py`` — see that module and
``specs/009-config-externalization/research.md`` (R3) for why. Any
``ConfigError`` raised here propagates uncaught through that import, so a
broken file fails the process at startup (spec 009, US3) instead of
degrading per-request.
"""
import json
from pathlib import Path
from typing import Optional

from src.config import tenants_config_path
from src.utils.logger import logger


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


def load_config(path: Optional[str] = None) -> dict:
    """Load, parse, and validate the tenant config file.

    Returns ``{"tenants": {tenant_id: TenantConfig}}``. Raises ``ConfigError``
    naming the file and the specific problem if the file is missing, not
    valid JSON, has a duplicate ``tenant_id``, or any entry is missing a
    required field. A legacy top-level ``formatter`` section is ignored with
    a warning (spec 014).
    """
    file_path = Path(path) if path is not None else tenants_config_path()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_text = f.read()
    except FileNotFoundError:
        raise ConfigError(f"Tenant config file not found: {file_path}") from None

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{file_path}: invalid JSON ({exc}).") from exc

    if "formatter" in data:
        logger.warning(
            "%s: legacy 'formatter' section ignored — the formatter assistant "
            "pass was removed (spec 014); delete it from the config file",
            file_path,
        )

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

    return {"tenants": tenants}
