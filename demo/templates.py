"""
Hermes Life OS - Quick-Log Templates
=========================================
Lets a person save a named shortcut for a specific log_* tool call with
fixed parameters (e.g. "usual breakfast" -> log_meal with a particular
food/calories), then replay it later with one call instead of
re-typing the same details every time. Templates only ever point at
log_* tools - never at export/backup/goal/habit-management tools or
anything else - so replaying one can only ever add a new log entry,
never trigger a side effect the person didn't explicitly ask for in
that moment. Stored in templates.json (via load_templates/
save_templates), no network call.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from storage import load_templates, save_templates


def save_template(template_name: str, tool_name: str, params: Dict[str, Any]) -> None:
    """Saves (or overwrites) a named template pointing at `tool_name`
    with `params`. Does not validate `tool_name` itself - callers
    (dispatch_tool) are expected to check it's an allowed log_* tool
    before calling this, so this function stays a pure storage
    operation and easy to test in isolation.
    """
    templates = load_templates()
    templates[template_name] = {"tool_name": tool_name, "params": params}
    save_templates(templates)


def get_template(template_name: str) -> Optional[Dict[str, Any]]:
    """Returns {"tool_name", "params"} for `template_name`
    (case-insensitive), or None if no template with that name exists."""
    templates = load_templates()
    for name, template in templates.items():
        if name.lower() == template_name.lower():
            return template
    return None


def list_templates() -> List[Dict[str, Any]]:
    """Returns every saved template as a list of {"name", "tool_name",
    "params"}, sorted alphabetically by name."""
    templates = load_templates()
    return [
        {"name": name, "tool_name": t["tool_name"], "params": t["params"]}
        for name, t in sorted(templates.items())
    ]


def delete_template(template_name: str) -> bool:
    """Removes a template (case-insensitive match). Returns True if a
    template was found and removed, False if no matching template
    existed."""
    templates = load_templates()
    for name in list(templates.keys()):
        if name.lower() == template_name.lower():
            del templates[name]
            save_templates(templates)
            return True
    return False


def format_template_list(templates: List[Dict[str, Any]]) -> str:
    """Turns list_templates()'s output into a friendly multi-line
    summary."""
    if not templates:
        return "No log templates saved yet."

    lines = ["Saved log templates:"]
    for t in templates:
        params_str = ", ".join(f"{k}={v}" for k, v in t["params"].items())
        lines.append(f"- {t['name']}: {t['tool_name']}({params_str})")
    return "\n".join(lines)
