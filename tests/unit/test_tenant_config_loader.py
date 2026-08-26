"""Unit tests for the JSON-backed tenant config loader (spec 009, US2/US3; spec 014, US2).

Since spec 014 the schema contains only the tenant list: a top-level
``formatter`` section is no longer required, and a legacy one is ignored with
a logged warning.
"""
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
    # Spec 014: no formatter key in the result
    assert "formatter" not in result


def test_config_without_formatter_section_is_valid(tmp_path):
    # The happy path above already covers this; explicit case for the spec-014
    # contract so a regression is named precisely.
    path = _write(tmp_path, {"tenants": []})
    result = loader.load_config(path=path)

    assert result == {"tenants": {}}


def test_legacy_formatter_section_warns_and_is_ignored(tmp_path, monkeypatch):
    warnings = []

    class _FakeLogger:
        def warning(self, msg, *args):
            warnings.append(msg % args if args else msg)

    monkeypatch.setattr(loader, "logger", _FakeLogger())

    data = _valid_data()
    data["formatter"] = {"model": "old-formatter", "tool_ids": ["format_reponse"]}
    path = _write(tmp_path, data)

    result = loader.load_config(path=path)

    assert "formatter" not in result
    assert result["tenants"]["t1"]["model"] == "model-1"
    assert any("formatter" in w for w in warnings)


# --- US3: fail-fast validation -------------------------------------------------


def test_missing_file_raises_config_error(tmp_path):
    missing_path = str(tmp_path / "does-not-exist.json")
    with pytest.raises(loader.ConfigError, match=missing_path.replace("\\", "\\\\")):
        loader.load_config(path=missing_path)


def test_invalid_json_raises_config_error(tmp_path):
    path = tmp_path / "tenants.json"
    path.write_text('{"tenants": [,]}', encoding="utf-8")
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
