"""
Hermes Life OS - Multi-User Registry
=======================================
Hermes already supports multiple *profiles* (storage.set_active_profile)
- separate data directories so several people can share one machine/install
without mixing data. This module adds the missing piece: a registry that
maps a **person** to their profile via their own personal API key, so one
running instance (the local REST API, a Slack workspace bot, etc.) can
serve a whole household or small team without everyone needing to know a
single shared secret or run their own separate process.

Registry file: ~/.hermes/life-os/users.json (always at the install root,
never inside a profile subfolder - it has to be readable before we know
which profile to switch to).

Each user record:
    {
        "username":  "alex",
        "profile":   "alex",              # storage profile this user owns
        "role":      "owner" | "member",  # owner can manage other users
        "key_hash":  "<hex>",             # PBKDF2-HMAC-SHA256 of their API key
        "key_salt":  "<hex>",
        "channels":  {"slack": "U0123", "telegram": "5551234"},
        "created_at": "2026-08-26T12:00:00Z",
    }

The plaintext API key is shown exactly once, at creation/rotation time,
and never stored - only its salted hash is. This mirrors how the local
REST API's single LIFE_OS_API_KEY already works, just extended to many
keys instead of one.

CLI:
    python demo/users.py add alex --profile alex --role owner
    python demo/users.py list
    python demo/users.py rotate alex
    python demo/users.py remove alex
    python demo/users.py link alex slack U0123ABC
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage

PBKDF2_ITERATIONS = 260_000
API_KEY_PREFIX = "hlo_"


class UserError(RuntimeError):
    pass


def users_file() -> Path:
    """Always at the install root (storage.HERMES_ROOT), independent of
    whichever profile happens to be active - the whole point of this
    registry is to resolve *which* profile a request belongs to, so it
    can't itself live inside one profile's folder."""
    return storage.HERMES_ROOT / "users.json"


def _generate_api_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def _hash_key(api_key: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", api_key.encode("utf-8"), salt, PBKDF2_ITERATIONS
    ).hex()


def load_users() -> Dict[str, dict]:
    path = users_file()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_users(users: Dict[str, dict]) -> None:
    path = users_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(users, indent=2, ensure_ascii=False), encoding="utf-8")


def add_user(username: str, profile: Optional[str] = None, role: str = "member") -> Tuple[dict, str]:
    """Creates a new user and returns (public_record, plaintext_api_key).
    The plaintext key is returned exactly once - store/show it now, it
    can't be recovered later (only rotate_user_key() can issue a new one).
    Raises UserError if the username already exists."""
    username = username.strip()
    if not username:
        raise UserError("Username cannot be empty.")
    users = load_users()
    if username in users:
        raise UserError(f"User '{username}' already exists. Use rotate to issue a new key.")
    if role not in ("owner", "member"):
        raise UserError("role must be 'owner' or 'member'.")

    api_key = _generate_api_key()
    salt = os.urandom(16)
    record = {
        "username": username,
        "profile": profile or username,
        "role": role,
        "key_hash": _hash_key(api_key, salt),
        "key_salt": salt.hex(),
        "channels": {},
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    users[username] = record
    save_users(users)
    return _public(record), api_key


def rotate_user_key(username: str) -> str:
    """Issues a brand new API key for an existing user, invalidating the
    old one immediately. Returns the new plaintext key (shown once)."""
    users = load_users()
    if username not in users:
        raise UserError(f"No such user: {username}")
    api_key = _generate_api_key()
    salt = os.urandom(16)
    users[username]["key_hash"] = _hash_key(api_key, salt)
    users[username]["key_salt"] = salt.hex()
    save_users(users)
    return api_key


def remove_user(username: str) -> None:
    users = load_users()
    if username not in users:
        raise UserError(f"No such user: {username}")
    del users[username]
    save_users(users)


def link_channel(username: str, channel: str, external_id: str) -> None:
    """Associates a chat-platform identity (Slack user ID, Telegram chat
    ID, Discord user ID, ...) with an existing Hermes user, so bots can
    resolve incoming messages to the right profile without the sender
    typing an API key. `channel` is a free-form label, e.g. 'slack'."""
    users = load_users()
    if username not in users:
        raise UserError(f"No such user: {username}")
    users[username].setdefault("channels", {})[channel] = str(external_id)
    save_users(users)


def find_by_channel(channel: str, external_id: str) -> Optional[dict]:
    """Looks up a user by a linked channel identity, e.g.
    find_by_channel('slack', 'U0123ABC'). Returns the public record
    (no key material) or None if nobody is linked to that identity."""
    external_id = str(external_id)
    for record in load_users().values():
        if record.get("channels", {}).get(channel) == external_id:
            return _public(record)
    return None


def list_users() -> List[dict]:
    return [_public(r) for r in load_users().values()]


def verify_api_key(api_key: str) -> Optional[dict]:
    """Checks `api_key` against every registered user (constant-effort
    comparison per user via hmac.compare_digest, so timing differences
    between users don't leak which one is 'closer' to matching). Returns
    the matching public record, or None if no user matches."""
    import hmac
    if not api_key:
        return None
    for record in load_users().values():
        salt = bytes.fromhex(record["key_salt"])
        candidate_hash = _hash_key(api_key, salt)
        if hmac.compare_digest(candidate_hash, record["key_hash"]):
            return _public(record)
    return None


def _public(record: dict) -> dict:
    """Strips key material before handing a record back to any caller
    that isn't save_users() itself - callers outside this module should
    never see key_hash/key_salt."""
    return {k: v for k, v in record.items() if k not in ("key_hash", "key_salt")}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Manage Hermes Life OS users (multi-user API/bot access).")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Register a new user and print their API key (shown once).")
    p_add.add_argument("username")
    p_add.add_argument("--profile", default=None, help="Storage profile to link (default: same as username).")
    p_add.add_argument("--role", default="member", choices=["owner", "member"])

    sub.add_parser("list", help="List all registered users.")

    p_rotate = sub.add_parser("rotate", help="Issue a new API key for an existing user.")
    p_rotate.add_argument("username")

    p_remove = sub.add_parser("remove", help="Remove a user.")
    p_remove.add_argument("username")

    p_link = sub.add_parser("link", help="Link a chat-platform identity to a user (e.g. for Slack/Telegram).")
    p_link.add_argument("username")
    p_link.add_argument("channel", help="e.g. slack, telegram, discord")
    p_link.add_argument("external_id", help="The platform's user/chat ID.")

    args = parser.parse_args()

    try:
        if args.command == "add":
            record, api_key = add_user(args.username, profile=args.profile, role=args.role)
            print(f"Created user '{record['username']}' (profile: {record['profile']}, role: {record['role']})")
            print(f"API key (save this now - it will not be shown again):\n  {api_key}")
        elif args.command == "list":
            users = list_users()
            if not users:
                print("No users registered yet. Add one with: python demo/users.py add <username>")
            for u in users:
                channels = ", ".join(f"{k}={v}" for k, v in u.get("channels", {}).items()) or "none"
                print(f"  {u['username']:<20} profile={u['profile']:<20} role={u['role']:<8} channels={channels}")
        elif args.command == "rotate":
            api_key = rotate_user_key(args.username)
            print(f"New API key for '{args.username}' (save this now - it will not be shown again):\n  {api_key}")
        elif args.command == "remove":
            remove_user(args.username)
            print(f"Removed user '{args.username}'.")
        elif args.command == "link":
            link_channel(args.username, args.channel, args.external_id)
            print(f"Linked {args.channel}:{args.external_id} -> user '{args.username}'.")
    except UserError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
