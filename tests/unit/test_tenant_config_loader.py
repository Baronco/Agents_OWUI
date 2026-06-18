"""Unit tests for the JSON-backed tenant/formatter config loader (spec 009, US2/US3)."""
import json

import pytest

from src.services import tenant_config_loader as loader


def _write(tmp_path, data):
    path = tmp_path / "tenants.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def _valid_data():
    return {
        "tenants": [
            {
                "tenant_id": "t1",
                "model": "model-1",
                "tool_ids": ["server:0"],
                "title_generation": True,
            },
            {
                "tenant_id": "t2",
                "model": "model-2",
            },
        ],
        "formatter": {
            "model": "formatter-model",
            "tool_ids": ["format_reponse"],
            "title_generation": False,
        },
    }


def test_load_config_happy_path(tmp_path):
    path = _write(tmp_path, _valid_data())
    result = loader.load_config(path=path)

    assert result["tenants"]["t1"] == {
        "model": "model-1",
        "tool_ids": ["server:0"],
        "title_generation": True,
    }
    # t2 omitted tool_ids/title_generation -> defaults applied
    assert result["tenants"]["t2"] == {
        "model": "model-2",
        "tool_ids": [],
        "title_generation": True,
    }
    assert result["formatter"] == {
        "model": "formatter-model",
        "tool_ids": ["format_reponse"],
        "title_generation": False,
    }


# --- US3: fail-fast validation -------------------------------------------------


def test_missing_file_raises_config_error(tmp_path):
    missing_path = str(tmp_path / "does-not-exist.json")
    with pytest.raises(loader.ConfigError, match=missing_path.replace("\\", "\\\\")):
        loader.load_config(path=missing_path)


def test_invalid_json_raises_config_error(tmp_path):
    path = tmp_path / "tenants.json"
    path.write_text('{"tenants": [,], "formatter": {}}', encoding="utf-8")
    with pytest.raises(loader.ConfigError) as exc_info:
        loader.load_config(path=str(path))
    message = str(exc_info.value)
    assert str(path) in message


def test_duplicate_tenant_id_raises_config_error(tmp_path):
    data = _valid_data()
    data["tenants"].append({"tenant_id": "t1", "model": "model-3"})
    path = _write(tmp_path, data)
    with pytest.raises(loader.ConfigError, match="t1"):
        loader.load_config(path=path)


def test_tenant_missing_model_raises_config_error(tmp_path):
    data = _valid_data()
    del data["tenants"][0]["model"]
    path = _write(tmp_path, data)
    with pytest.raises(loader.ConfigError, match="t1"):
        loader.load_config(path=path)


def test_tenant_missing_tenant_id_raises_config_error(tmp_path):
    data = _valid_data()
    del data["tenants"][1]["tenant_id"]
    path = _write(tmp_path, data)
    with pytest.raises(loader.ConfigError, match="index 1"):
        loader.load_config(path=path)


def test_missing_formatter_section_raises_config_error(tmp_path):
    data = _valid_data()
    del data["formatter"]
    path = _write(tmp_path, data)
    with pytest.raises(loader.ConfigError, match="formatter"):
        loader.load_config(path=path)


def test_formatter_with_empty_tool_ids_raises_config_error(tmp_path):
    data = _valid_data()
    data["formatter"]["tool_ids"] = []
    path = _write(tmp_path, data)
    with pytest.raises(loader.ConfigError, match="tool_ids"):
        loader.load_config(path=path)
