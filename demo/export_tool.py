"""
Hermes Life OS - Conversational Data Export
===============================================
A thin dispatch_tool-facing wrapper around the existing
demo/data_export.py CLI (export_json/export_csv/export_markdown),
which until now could only be triggered by running the script
directly. This lets the agent trigger "export my data" from a normal
conversation and get a file path back, picking a sensible default
output location under storage.HERMES_DIR/exports/ so the person
doesn't have to supply one. No new tracking or storage of its own
beyond the export files themselves, no network call.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

import storage
from data_export import export_csv, export_json, export_markdown

VALID_FORMATS = ("json", "csv", "markdown")


def exports_dir():
    """Directory exports for the *currently active* profile live in -
    mirrors backup.py's backups_dir() so exports follow whichever
    profile set_active_profile() has switched to."""
    return storage.HERMES_DIR / "exports"


def run_export(export_format: str = "json", days: int = None) -> Dict[str, Any]:
    """Writes an export of the requested `export_format` ("json", "csv",
    or "markdown") to a fresh timestamped path under exports_dir(), and
    returns {"format", "path", "count"}. "count" is the number of
    memory entries for json, the number of daily rows for csv, or the
    number of day-files written for markdown. Raises ValueError for an
    unrecognized format rather than silently defaulting, since writing
    the wrong format silently would be worse than failing loudly.
    """
    if export_format not in VALID_FORMATS:
        raise ValueError(f"Unknown export format '{export_format}', expected one of {VALID_FORMATS}")

    directory = exports_dir()
    directory.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")

    if export_format == "json":
        path = directory / f"export-{ts}.json"
        count = export_json(str(path))
    elif export_format == "csv":
        path = directory / f"export-{ts}.csv"
        count = export_csv(str(path))
    else:
        path = directory / f"export-{ts}"
        count = export_markdown(str(path), days=days)

    return {"format": export_format, "path": str(path), "count": count}


def format_export_result(result: Dict[str, Any]) -> str:
    """Turns run_export()'s output into a friendly one-line summary."""
    unit = {"json": "memory entries", "csv": "daily rows", "markdown": "day-files"}[result["format"]]
    return f"Exported {result['count']} {unit} to {result['path']}."
