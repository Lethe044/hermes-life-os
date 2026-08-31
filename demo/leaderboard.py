"""
Hermes Life OS - Leaderboard
================================
An opt-in, cross-profile leaderboard for households or small teams
sharing one Hermes install (see docs/MULTI_USER.md) - a friendly way
to see how everyone's doing. Entirely local (no data ever leaves the
machine, nothing is sent anywhere) and strictly opt-in per profile.

Nobody is included by default. A profile only appears on the
leaderboard after explicitly opting in (the join_leaderboard tool, or
`python demo/leaderboard.py join`), and can opt out again at any time -
at which point their data stops being read for leaderboard purposes
immediately, not just hidden from display.

Ranks by average Life Score over a window, current logging streak, and
total achievements earned. Only those three numbers are ever shared
across profiles - no journal content, no specific logged entries, no
raw metric values.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage
from achievements import evaluate_achievements
from life_score import compute_life_score_trend


def is_opted_in(profile: Optional[str] = None) -> bool:
    """Whether `profile` (default: the currently active profile) has
    opted into the leaderboard. Temporarily switches the active profile
    to check, if needed, and always restores it afterward - safe to
    call regardless of which profile is currently active."""
    target = profile or storage.ACTIVE_PROFILE
    original = storage.ACTIVE_PROFILE
    try:
        if target != original:
            storage.set_active_profile(target)
        return bool(storage.load_profile().get("leaderboard_opt_in", False))
    finally:
        if target != original:
            storage.set_active_profile(original)


def set_opt_in(opted_in: bool, profile: Optional[str] = None) -> None:
    """Opts `profile` (default: the currently active profile) in or out.
    Opting out takes effect immediately - the next get_leaderboard()
    call simply won't visit that profile, there is no cached/stale
    leaderboard state to clear separately."""
    target = profile or storage.ACTIVE_PROFILE
    original = storage.ACTIVE_PROFILE
    try:
        if target != original:
            storage.set_active_profile(target)
        p = storage.load_profile()
        p["leaderboard_opt_in"] = opted_in
        storage.save_profile(p)
    finally:
        if target != original:
            storage.set_active_profile(original)


def _stats_for_current_profile(days: int, profile_name: str) -> Dict[str, Any]:
    """Computes leaderboard stats assuming storage is ALREADY pointed at
    the profile to score - callers own switching in/out of profiles;
    this function never does so itself, to avoid redundant switches
    when scanning many profiles in a loop."""
    trend = compute_life_score_trend(days)
    avg_score = round(sum(t["score"] for t in trend) / len(trend)) if trend else None
    badges = evaluate_achievements()
    earned = [b for b in badges if b["earned"]]
    streak_badges = [b for b in badges if b["id"].startswith("logging-streak-")]
    current_streak = max((b["progress"] for b in streak_badges), default=0)
    display_name = storage.load_profile().get("name") or profile_name
    return {
        "profile": profile_name,
        "display_name": display_name,
        "avg_life_score": avg_score,
        "logging_streak": current_streak,
        "achievements_earned": len(earned),
    }


def get_leaderboard(days: int = 7) -> List[Dict[str, Any]]:
    """Returns one entry per opted-in profile, sorted by average Life
    Score descending (profiles with no scoreable data yet sort last,
    not treated as a score of 0). The globally active profile is always
    restored before returning, no matter how many profiles were visited
    or whether an error occurred partway through - a leaderboard lookup
    should never leave the caller "stuck" on someone else's profile."""
    original = storage.ACTIVE_PROFILE
    entries: List[Dict[str, Any]] = []
    try:
        for profile in storage.list_profiles():
            storage.set_active_profile(profile)
            if not storage.load_profile().get("leaderboard_opt_in", False):
                continue
            entries.append(_stats_for_current_profile(days, profile))
    finally:
        storage.set_active_profile(original)

    entries.sort(key=lambda e: (e["avg_life_score"] is None, -(e["avg_life_score"] or 0)))
    return entries


def format_leaderboard(entries: List[Dict[str, Any]]) -> str:
    """Renders get_leaderboard()'s output as plain text, medal emoji for
    the top 3. Returns a friendly message (not an error) for an empty
    leaderboard, since "nobody's opted in yet" is an expected state."""
    if not entries:
        return ("No one has joined the leaderboard yet. Opt in with the join_leaderboard "
                 "tool (or `python demo/leaderboard.py join`) to be the first.")
    medals = ["\U0001F947", "\U0001F948", "\U0001F949"]
    lines = []
    for i, e in enumerate(entries):
        prefix = medals[i] if i < len(medals) else f"{i + 1}."
        score = e["avg_life_score"] if e["avg_life_score"] is not None else "N/A"
        lines.append(
            f"{prefix} {e['display_name']}: Life Score {score}, "
            f"{e['logging_streak']}-day streak, {e['achievements_earned']} badge(s)"
        )
    return "\n".join(lines)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Manage or view the Hermes Life OS leaderboard")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("join", help="Opt the active profile into the leaderboard.")
    sub.add_parser("leave", help="Opt the active profile out of the leaderboard.")
    p_show = sub.add_parser("show", help="Show the current leaderboard.")
    p_show.add_argument("--days", type=int, default=7)
    for p in (sub.choices["join"], sub.choices["leave"], p_show):
        p.add_argument("--profile", default=None, help="Profile to act on. Default: active/default.")

    args = parser.parse_args()
    storage.set_active_profile(getattr(args, "profile", None))

    if args.command == "join":
        set_opt_in(True)
        print(f"'{storage.ACTIVE_PROFILE}' joined the leaderboard.")
    elif args.command == "leave":
        set_opt_in(False)
        print(f"'{storage.ACTIVE_PROFILE}' left the leaderboard.")
    elif args.command == "show":
        entries = get_leaderboard(args.days)
        print(format_leaderboard(entries))


if __name__ == "__main__":
    main()
