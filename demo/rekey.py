"""
Hermes Life OS - Encryption Re-key
=====================================
Changes (or sets, or removes) the passphrase protecting your data at
rest (LIFE_OS_ENCRYPTION_KEY). Reads every file in the active profile
with the OLD key (or as plaintext, if there wasn't one), decrypts it
in memory, generates a brand new random salt, and re-encrypts
everything with the NEW key (or leaves it as plaintext, if disabling).

This touches every config file (profile.json, habits.json, goals.json,
etc.) plus every line of memory.jsonl. Nothing is written to disk
until every file has been successfully decrypted with the old key -
so a wrong old passphrase fails loudly before touching anything.
However, the tool is NOT atomic across the whole profile once writing
starts: if it's interrupted partway through writing, some files may
already be on the new key while others aren't. BACK UP FIRST
(`hermes-life-os-backup`) - the confirmation prompt reminds you.

Usage:
    python demo/rekey.py --new-key "new passphrase"
        (reads the old key from $LIFE_OS_ENCRYPTION_KEY, or treats
        data as plaintext if that's unset)

    python demo/rekey.py --old-key "old passphrase" --new-key "new passphrase"

    python demo/rekey.py --disable
        (decrypts everything back to plaintext; --old-key still
        applies the same way)

    python demo/rekey.py --profile alex --new-key "..." --yes
        (skip the confirmation prompt, e.g. for scripting)

After a successful run, update LIFE_OS_ENCRYPTION_KEY (or unset it,
for --disable) before running any other Hermes command.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage
import crypto_store
from crypto_store import EncryptionUnavailable, get_fernet

CONFIG_FILE_ATTRS = [
    "PROFILE_FILE", "HABITS_FILE", "GOALS_FILE", "NUTRITION_FILE",
    "SLEEP_FILE", "HYDRATION_FILE", "FITNESS_FILE", "FOCUS_FILE", "MENTAL_FILE",
]


class RekeyError(RuntimeError):
    pass


def _config_files() -> List[Path]:
    return [getattr(storage, name) for name in CONFIG_FILE_ATTRS]


def _decrypt_text(raw: str, fernet) -> str:
    """
    Mirrors storage.py's own tolerant fallback (try decrypt, else
    assume plaintext) rather than failing on the first mismatch -
    encryption here is opt-in and can be turned on after the profile
    already has plaintext history, so a mix of encrypted and
    still-plaintext content in the same profile is expected, not an
    error.

    What IS an error: content that neither decrypts with the old key
    NOR parses as valid JSON on its own - that combination means the
    old passphrase is actually wrong (we're looking at someone else's
    ciphertext, not old plaintext), so this raises rather than silently
    writing that garbage back out re-encrypted under the new key.
    """
    if fernet is not None:
        try:
            return fernet.decrypt(raw.encode("ascii")).decode("utf-8")
        except Exception:
            pass  # not decryptable with the old key - might just be pre-encryption plaintext

    try:
        json.loads(raw)
    except Exception as e:
        raise RekeyError(
            "Failed to decrypt existing data with the old key, and it doesn't "
            "look like valid plaintext either - wrong old passphrase?"
        ) from e
    return raw


def _encrypt_text(raw: str, fernet) -> str:
    if fernet is None:
        return raw
    return fernet.encrypt(raw.encode("utf-8")).decode("ascii")


def rekey(old_passphrase: Optional[str], new_passphrase: Optional[str]) -> Dict[str, int]:
    """
    Re-encrypts every file in the *currently active* profile
    (storage.HERMES_DIR) from old_passphrase to new_passphrase. Either
    may be None/empty, meaning "plaintext" on that side (so this same
    function handles enabling encryption for the first time, changing
    an existing passphrase, and disabling encryption entirely).

    Returns {"config_files": N, "memory_lines": M} - counts of what
    was re-keyed.
    """
    hermes_dir = storage.HERMES_DIR
    old_fernet = get_fernet(old_passphrase, hermes_dir) if old_passphrase else None

    # Decrypt everything into memory FIRST - if any file fails to
    # decrypt with the old key, we bail before writing anything at all.
    decrypted_configs: Dict[Path, str] = {}
    for path in _config_files():
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8")
        decrypted_configs[path] = _decrypt_text(raw, old_fernet)

    decrypted_memory_lines: List[str] = []
    if storage.MEMORY_FILE.exists():
        with open(storage.MEMORY_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                decrypted_memory_lines.append(_decrypt_text(line, old_fernet))

    # Rotate the salt and derive the new key. A fresh salt means the
    # old (passphrase, salt) pair is fully retired, not just the
    # passphrase - even if someone reused an old passphrase later, it
    # wouldn't reproduce an old key.
    salt_path = hermes_dir / crypto_store.SALT_FILE_NAME
    if new_passphrase:
        if salt_path.exists():
            salt_path.unlink()
        new_fernet = get_fernet(new_passphrase, hermes_dir)  # creates a fresh salt
    else:
        new_fernet = None
        if salt_path.exists():
            salt_path.unlink()  # no longer needed once encryption is off

    # Only now do we write anything back out.
    for path, content in decrypted_configs.items():
        path.write_text(_encrypt_text(content, new_fernet), encoding="utf-8")

    if decrypted_memory_lines:
        tmp_path = storage.MEMORY_FILE.with_suffix(storage.MEMORY_FILE.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as fh:
            for line in decrypted_memory_lines:
                fh.write(_encrypt_text(line, new_fernet) + "\n")
        tmp_path.replace(storage.MEMORY_FILE)

    return {"config_files": len(decrypted_configs), "memory_lines": len(decrypted_memory_lines)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Change, set, or remove the passphrase encrypting your data at rest.")
    parser.add_argument("--profile", default=None, help="Profile to re-key. Default: the default profile.")
    parser.add_argument("--old-key", default=None,
                        help="Current passphrase. Defaults to $LIFE_OS_ENCRYPTION_KEY "
                             "(or plaintext, if that's unset).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--new-key", default=None, help="New passphrase to encrypt with.")
    group.add_argument("--disable", action="store_true",
                       help="Remove encryption entirely - decrypt everything back to plaintext.")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")
    args = parser.parse_args()

    storage.set_active_profile(args.profile or os.environ.get("LIFE_OS_PROFILE"))

    old_passphrase = args.old_key if args.old_key is not None else os.environ.get("LIFE_OS_ENCRYPTION_KEY")
    new_passphrase = None if args.disable else args.new_key

    if not args.yes:
        answer = input(
            f"This will re-encrypt every file for profile '{storage.ACTIVE_PROFILE}'. "
            f"Back up first with `hermes-life-os-backup` if you haven't already. "
            f"Continue? [y/N] "
        )
        if answer.strip().lower() not in ("y", "yes"):
            print("Cancelled - nothing was changed.")
            return

    try:
        summary = rekey(old_passphrase, new_passphrase)
    except RekeyError as e:
        print(f"Re-key failed: {e}")
        sys.exit(1)
    except EncryptionUnavailable as e:
        print(e)
        sys.exit(1)

    print(f"Done - re-keyed {summary['config_files']} config file(s) and "
          f"{summary['memory_lines']} memory entries.")
    if new_passphrase:
        print("Set LIFE_OS_ENCRYPTION_KEY to your NEW passphrase before running any other Hermes command.")
    else:
        print("Encryption is now disabled - LIFE_OS_ENCRYPTION_KEY is no longer needed.")


if __name__ == "__main__":
    main()
