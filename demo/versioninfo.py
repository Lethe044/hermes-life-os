"""
Hermes Life OS - version lookup
=================================
The version of the running copy: the `version` line of the pyproject.toml next
to a source checkout, otherwise the installed package metadata, otherwise
"unknown". Used by the --version flags.
"""

from __future__ import annotations

import re
from pathlib import Path

PACKAGE = "hermes-life-os"


def get() -> str:
    try:
        text = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")
        found = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
        if found:
            return found.group(1)  # a source checkout: its own pyproject is the truth
    except OSError:
        pass
    try:
        from importlib.metadata import PackageNotFoundError, version
        try:
            return version(PACKAGE)
        except PackageNotFoundError:
            pass
    except ImportError:  # pragma: no cover
        pass
    return "unknown"


def banner() -> str:
    return f"{PACKAGE} {get()}"
