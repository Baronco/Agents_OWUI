"""Unit tests for per-user token storage (spec 011, US3).

Each provisioned user gets its own file under USERS_DIR, keyed by
(client_phone, tenant_id). A request reads/writes only that user's file.
Runs fully offline: USERS_DIR points at a temp dir and the OWUI client is a
stub, so no network or real OpenWebUI is involved.
"""
import json
import os

import pytest

from src.services import user_provisioning as up


class _StubClient:
    """Stands in for OpenWebUIClient: create_user returns a fake user+token."""
    def __init__(self, user_id="u-stub", token="tok-stub"):
        self._user_id = user_id
        self._token = token
        self.created = []

    def create_user(self, name, email, password, **kwargs):
        self.created.append(email)
        return {"user_id": self._user_id, "token": self._token}


@pytest.fixture
def users_dir(tmp_path, monkeypatch):
    """Point USERS_DIR at a fresh temp dir for each test."""
    d = tmp_path / "users"
    monkeypatch.setenv("USERS_DIR", str(d))
    monkeypatch.setenv("USER_PASSWORD_SECRET", "test-secret")
    return d


def _files(d):
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def test_provision_creates_one_file_per_user(users_dir):
    client = _StubClient(user_id="u1", token="tok1")
    result = up.provision_user("+573001110001", "tenantA", owui_client=client)

    assert result is not None
    assert result["user_id"] == "u1"
    assert result["token"] == "tok1"

    files = _files(users_dir)
    assert len(files) == 1, f"expected exactly one user file, got {files}"

    content = json.loads((users_dir / files[0]).read_text(encoding="utf-8"))
    assert content["user_id"] == "u1"
    assert content["token"] == "tok1"
    assert "expires_at" in content


def test_two_users_two_isolated_files(users_dir):
    up.provision_user("+573001110001", "tenantA", owui_client=_StubClient("u1", "tok1"))
    up.provision_user("+573002220002", "tenantB", owui_client=_StubClient("u2", "tok2"))

    files = _files(users_dir)
    assert len(files) == 2, f"expected two user files, got {files}"

    blobs = [(_users := (users_dir / f).read_text(encoding="utf-8")) for f in files]
    joined = "\n".join(blobs)
    # Each token appears, and no single file mixes both users.
    assert "tok1" in joined and "tok2" in joined
    for f in files:
        c = json.loads((users_dir / f).read_text(encoding="utf-8"))
        assert {c["user_id"], c["token"]} in ({"u1", "tok1"}, {"u2", "tok2"})


def test_chat_mapping_roundtrip_touches_only_one_user(users_dir):
    email_a = up._generate_email("+573001110001", "tenantA")
    up.provision_user("+573001110001", "tenantA", owui_client=_StubClient("u1", "tok1"))
    up.provision_user("+573002220002", "tenantB", owui_client=_StubClient("u2", "tok2"))

    file_b = up._user_file(up._generate_email("+573002220002", "tenantB"))
    before_b = file_b.read_text(encoding="utf-8")

    up.store_chat_mapping(email_a, "ext-1", "owui-1")
    assert up.get_owui_chat_id(email_a, "ext-1") == "owui-1"

    # The other user's file is untouched.
    assert file_b.read_text(encoding="utf-8") == before_b


def test_missing_dir_and_user_handled_gracefully(users_dir):
    # USERS_DIR doesn't exist yet (no provisioning happened).
    assert not os.path.isdir(users_dir)
    # Unknown user -> None, no crash, no dir required.
    assert up.get_owui_chat_id(up._generate_email("+570000000000", "tenantX"), "ext") is None
    # Provisioning then creates the dir on demand.
    up.provision_user("+573001110001", "tenantA", owui_client=_StubClient("u1", "tok1"))
    assert os.path.isdir(users_dir)
