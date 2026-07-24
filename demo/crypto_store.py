"""
Hermes Life OS - Encryption at rest
======================================
Opt-in only. If LIFE_OS_ENCRYPTION_KEY isn't set, nothing here is used
and every file is plain JSON/JSONL exactly as before - zero behavior
change for anyone who doesn't ask for this.

When a passphrase IS set, storage.py transparently encrypts every
config file (profile.json, habits.json, etc.) as a single Fernet
token, and every line of memory.jsonl as its own Fernet token (so it
stays append-only and line-readable). Existing plaintext files are
read transparently and get encrypted the next time they're written -
no separate "migrate" step needed.

Fernet (AES-128-CBC + HMAC, from the `cryptography` package) with a
key derived from the passphrase via PBKDF2-HMAC-SHA256 and a random,
per-profile salt stored alongside the data (the salt isn't secret -
only the passphrase is).
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Optional

SALT_FILE_NAME = ".salt"
PBKDF2_ITERATIONS = 480_000  # OWASP 2023 recommendation for PBKDF2-HMAC-SHA256


class EncryptionUnavailable(RuntimeError):
    """Raised when LIFE_OS_ENCRYPTION_KEY is set but the `cryptography`
    package isn't installed."""


def _require_cryptography():
    try:
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        return Fernet, hashes, PBKDF2HMAC
    except ImportError as e:
        raise EncryptionUnavailable(
            "LIFE_OS_ENCRYPTION_KEY is set but the 'cryptography' package "
            "isn't installed.\n  pip install cryptography\n"
            "  (or: pip install \"hermes-life-os[encryption]\")"
        ) from e


def get_or_create_salt(hermes_dir: Path) -> bytes:
    salt_path = hermes_dir / SALT_FILE_NAME
    if salt_path.exists():
        return salt_path.read_bytes()
    hermes_dir.mkdir(parents=True, exist_ok=True)
    salt = os.urandom(16)
    salt_path.write_bytes(salt)
    return salt


def derive_key(passphrase: str, salt: bytes) -> bytes:
    Fernet, hashes, PBKDF2HMAC = _require_cryptography()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def get_fernet(passphrase: Optional[str], hermes_dir: Path):
    """Returns a ready-to-use Fernet instance, or None if no passphrase
    is configured (i.e. encryption is off)."""
    if not passphrase:
        return None
    Fernet, _, _ = _require_cryptography()
    salt = get_or_create_salt(hermes_dir)
    key = derive_key(passphrase, salt)
    return Fernet(key)
