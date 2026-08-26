"""Tests for demo/users.py - the multi-user registry (username <-> API
key <-> profile mapping) used by local_api.py and slack_bot.py."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def users_mod(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "users"):
        if mod in sys.modules:
            del sys.modules[mod]
    import users as u
    importlib.reload(u)
    u.storage.set_active_profile(None)
    return u


class TestAddUser:
    def test_add_user_returns_record_and_plaintext_key(self, users_mod):
        record, api_key = users_mod.add_user("alex")
        assert record["username"] == "alex"
        assert record["profile"] == "alex"  # defaults to username
        assert record["role"] == "member"
        assert api_key.startswith("hlo_")
        assert "key_hash" not in record
        assert "key_salt" not in record

    def test_add_user_custom_profile_and_role(self, users_mod):
        record, _key = users_mod.add_user("alex", profile="household", role="owner")
        assert record["profile"] == "household"
        assert record["role"] == "owner"

    def test_duplicate_username_raises(self, users_mod):
        users_mod.add_user("alex")
        with pytest.raises(users_mod.UserError):
            users_mod.add_user("alex")

    def test_empty_username_raises(self, users_mod):
        with pytest.raises(users_mod.UserError):
            users_mod.add_user("   ")

    def test_invalid_role_raises(self, users_mod):
        with pytest.raises(users_mod.UserError):
            users_mod.add_user("alex", role="admin")

    def test_persists_across_reload(self, users_mod):
        users_mod.add_user("alex")
        assert "alex" in users_mod.load_users()


class TestVerifyApiKey:
    def test_correct_key_resolves_user(self, users_mod):
        _record, api_key = users_mod.add_user("alex")
        resolved = users_mod.verify_api_key(api_key)
        assert resolved is not None
        assert resolved["username"] == "alex"

    def test_wrong_key_returns_none(self, users_mod):
        users_mod.add_user("alex")
        assert users_mod.verify_api_key("hlo_totally-wrong-key") is None

    def test_empty_key_returns_none(self, users_mod):
        users_mod.add_user("alex")
        assert users_mod.verify_api_key("") is None

    def test_distinguishes_between_users(self, users_mod):
        _r1, key1 = users_mod.add_user("alex")
        _r2, key2 = users_mod.add_user("sam")
        assert users_mod.verify_api_key(key1)["username"] == "alex"
        assert users_mod.verify_api_key(key2)["username"] == "sam"

    def test_plaintext_key_never_stored(self, users_mod):
        _record, api_key = users_mod.add_user("alex")
        raw = users_mod.users_file().read_text(encoding="utf-8")
        assert api_key not in raw


class TestRotateKey:
    def test_rotate_issues_new_working_key(self, users_mod):
        _record, old_key = users_mod.add_user("alex")
        new_key = users_mod.rotate_user_key("alex")
        assert new_key != old_key
        assert users_mod.verify_api_key(new_key)["username"] == "alex"

    def test_old_key_stops_working_after_rotate(self, users_mod):
        _record, old_key = users_mod.add_user("alex")
        users_mod.rotate_user_key("alex")
        assert users_mod.verify_api_key(old_key) is None

    def test_rotate_unknown_user_raises(self, users_mod):
        with pytest.raises(users_mod.UserError):
            users_mod.rotate_user_key("nobody")


class TestRemoveUser:
    def test_remove_deletes_user(self, users_mod):
        _record, api_key = users_mod.add_user("alex")
        users_mod.remove_user("alex")
        assert "alex" not in users_mod.load_users()
        assert users_mod.verify_api_key(api_key) is None

    def test_remove_unknown_user_raises(self, users_mod):
        with pytest.raises(users_mod.UserError):
            users_mod.remove_user("nobody")


class TestChannelLinking:
    def test_link_and_find_by_channel(self, users_mod):
        users_mod.add_user("alex")
        users_mod.link_channel("alex", "slack", "U0123ABC")
        found = users_mod.find_by_channel("slack", "U0123ABC")
        assert found is not None
        assert found["username"] == "alex"

    def test_find_by_channel_no_match_returns_none(self, users_mod):
        users_mod.add_user("alex")
        assert users_mod.find_by_channel("slack", "U9999") is None

    def test_link_unknown_user_raises(self, users_mod):
        with pytest.raises(users_mod.UserError):
            users_mod.link_channel("nobody", "slack", "U0123ABC")

    def test_link_id_compared_as_string(self, users_mod):
        users_mod.add_user("alex")
        users_mod.link_channel("alex", "telegram", 5551234)
        assert users_mod.find_by_channel("telegram", "5551234") is not None
        assert users_mod.find_by_channel("telegram", 5551234) is not None


class TestListUsers:
    def test_list_empty(self, users_mod):
        assert users_mod.list_users() == []

    def test_list_returns_public_records_only(self, users_mod):
        users_mod.add_user("alex")
        users_mod.add_user("sam")
        listed = users_mod.list_users()
        assert {u["username"] for u in listed} == {"alex", "sam"}
        for u in listed:
            assert "key_hash" not in u
            assert "key_salt" not in u
