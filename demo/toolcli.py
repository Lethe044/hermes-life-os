"""
Hermes Life OS - tool command line
====================================
Every tool the agent can call is also available straight from the shell, with
no language model and no API key. Handy for scripts, shortcuts, cron jobs and
for trying a tool before asking the agent to use it.

    hermes-life-os-tool list [--match WORD]
    hermes-life-os-tool show add_task
    hermes-life-os-tool run add_task text="Pay rent" due=friday priority=high
    hermes-life-os-tool run add_task --json '{"text": "Pay rent", "due": "friday"}'
    echo '{"scores": {"health": 7}}' | hermes-life-os-tool run log_life_wheel --json -

In `key=value` form a value is read as JSON when it parses (numbers, true,
false, lists, objects) and as plain text otherwise, so `minutes=45` is a
number and `due=friday` is a word. Use --profile (or LIFE_OS_PROFILE) to pick
a profile. The exit status is 0 on success, 1 for an unknown tool or invalid
arguments.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage  # noqa: E402
import versioninfo  # noqa: E402


def _catalog() -> Dict[str, Dict[str, Any]]:
    import tools
    return {s["function"]["name"]: s["function"] for s in tools.TOOLS}


def _first_sentence(text: str, limit: int = 100) -> str:
    text = " ".join(str(text).split())
    cut = text.find(". ")
    if 0 < cut < limit:
        text = text[:cut + 1]
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


def parse_pairs(pairs: List[str]) -> Dict[str, Any]:
    """`key=value` arguments as a dict. Raises ValueError for a missing `=`
    or an empty key."""
    out: Dict[str, Any] = {}
    for p in pairs:
        key, sep, raw = p.partition("=")
        key = key.strip()
        if not sep or not key:
            raise ValueError(f"'{p}' is not key=value.")
        try:
            out[key] = json.loads(raw)
        except ValueError:
            out[key] = raw
    return out


def read_json(source: str) -> Dict[str, Any]:
    text = sys.stdin.read() if source == "-" else source
    try:
        data = json.loads(text)
    except ValueError as e:
        raise ValueError(f"--json is not valid JSON: {e}") from None
    if not isinstance(data, dict):
        raise ValueError("--json must be a JSON object such as {\"text\": \"x\"}.")
    return data


def format_listing(catalog: Dict[str, Dict[str, Any]], match: Optional[str] = None) -> str:
    names = sorted(n for n, f in catalog.items()
                   if not match or match.lower() in n.lower() or match.lower() in str(f.get("description", "")).lower())
    if not names:
        return f"No tool matches '{match}'."
    width = max(len(n) for n in names)
    lines = [f"{n.ljust(width)}  {_first_sentence(catalog[n].get('description', ''))}" for n in names]
    lines.append(f"{len(names)} of {len(catalog)} tools. Details: hermes-life-os-tool show <name>")
    return "\n".join(lines)


def format_show(fn: Dict[str, Any]) -> str:
    params = fn.get("parameters", {})
    req = set(params.get("required", []))
    lines = [fn["name"], "", " ".join(str(fn.get("description", "")).split()), ""]
    props = params.get("properties", {})
    if not props:
        lines.append("No parameters.")
    else:
        lines.append("Parameters (* required):")
        for k, v in props.items():
            kind = v.get("type", "any") if isinstance(v, dict) else "any"
            if isinstance(v, dict) and v.get("enum"):
                kind = "/".join(str(e) for e in v["enum"])
            note = f" - {v['description']}" if isinstance(v, dict) and v.get("description") else ""
            lines.append(f"  {k}{'*' if k in req else ''} ({kind}){note}")
    example = " ".join(f"{k}=<{k}>" for k in props if k in req)
    lines += ["", f"Example: hermes-life-os-tool run {fn['name']}{(' ' + example) if example else ''}"]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="hermes-life-os-tool",
                                     description="Run Hermes Life OS tools from the shell, no language model needed.")
    parser.add_argument("--version", action="version", version=versioninfo.banner())
    parser.add_argument("--profile", default=None, help="Profile to use. Can also be set via LIFE_OS_PROFILE.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list", help="List the tools.")
    p_list.add_argument("--match", default=None, help="Only tools whose name or description contains this word.")
    p_show = sub.add_parser("show", help="Describe one tool and its parameters.")
    p_show.add_argument("name")
    p_run = sub.add_parser("run", help="Run a tool and print its answer.")
    p_run.add_argument("name")
    p_run.add_argument("pairs", nargs="*", help="key=value arguments.")
    p_run.add_argument("--json", dest="json_input", default=None,
                       help="Arguments as a JSON object, or - to read it from standard input.")
    args, extra = parser.parse_known_args(argv)
    # Older argparse (3.10, 3.11) does not accept key=value arguments that come after an option such
    # as --json, so anything left over that is not an option is treated as more key=value pairs.
    stray = [e for e in extra if e.startswith("-")]
    if stray or (extra and args.cmd != "run"):
        parser.error(f"unrecognized arguments: {' '.join(stray or extra)}")
    if extra:
        args.pairs = list(args.pairs) + extra

    storage.set_active_profile(args.profile or os.environ.get("LIFE_OS_PROFILE"))
    catalog = _catalog()
    if args.cmd == "list":
        print(format_listing(catalog, args.match))
        return 0
    if args.name not in catalog:
        close = [n for n in sorted(catalog) if args.name.lower() in n.lower()][:5]
        hint = f" Did you mean: {', '.join(close)}?" if close else " See hermes-life-os-tool list."
        print(f"Unknown tool '{args.name}'.{hint}", file=sys.stderr)
        return 1
    if args.cmd == "show":
        print(format_show(catalog[args.name]))
        return 0
    try:
        inp: Dict[str, Any] = read_json(args.json_input) if args.json_input is not None else {}
        inp.update(parse_pairs(args.pairs))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    import tools
    print(tools.dispatch_tool(args.name, inp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
