"""
Hermes Life OS - Social Insights
====================================
Breaks down recent social interactions by who they were with - total
time, average quality, and the most frequent contact - a different
angle than get_social_summary, which only totals the whole window.
Pure local arithmetic over data already in social.json (via
load_social), no new tracking of its own, no network call.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List


from storage import load_social


def compute_social_insights(days: int = 30) -> Dict[str, Any]:
    """Returns {"days", "total_interactions", "by_person": {person:
    {"count", "total_minutes", "avg_quality"}}, "most_frequent_contact",
    "highest_quality_contact"} over the last `days` days. A person
    needs a non-empty "with_who" to be counted; blank entries are
    excluded from the breakdown but still counted in the total.
    """
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    interactions = [s for s in load_social() if s.get("date", "") >= cutoff]

    if not interactions:
        return {"days": days, "total_interactions": 0, "by_person": {},
                "most_frequent_contact": None, "highest_quality_contact": None}

    minutes_by_person: Dict[str, int] = defaultdict(int)
    quality_by_person: Dict[str, List[float]] = defaultdict(list)
    count_by_person: Dict[str, int] = defaultdict(int)
    for s in interactions:
        person = s.get("with_who", "").strip()
        if not person:
            continue
        minutes_by_person[person] += s.get("duration_min", 0)
        quality_by_person[person].append(s.get("quality", 5))
        count_by_person[person] += 1

    by_person = {
        person: {
            "count": count_by_person[person],
            "total_minutes": minutes_by_person[person],
            "avg_quality": round(sum(quality_by_person[person]) / len(quality_by_person[person]), 1),
        }
        for person in count_by_person
    }

    most_frequent = max(by_person, key=lambda p: by_person[p]["count"]) if by_person else None
    highest_quality = max(by_person, key=lambda p: by_person[p]["avg_quality"]) if by_person else None

    return {
        "days": days,
        "total_interactions": len(interactions),
        "by_person": by_person,
        "most_frequent_contact": most_frequent,
        "highest_quality_contact": highest_quality,
    }


def format_social_insights(result: Dict[str, Any]) -> str:
    """Turns compute_social_insights()'s output into a friendly
    multi-line summary, most time spent first."""
    if result["total_interactions"] == 0:
        return f"No social interactions logged in the last {result['days']} days."

    lines = [f"{result['total_interactions']} social interaction(s) over the last {result['days']} days."]
    ordered = sorted(result["by_person"].items(), key=lambda kv: -kv[1]["total_minutes"])
    for person, stats in ordered:
        lines.append(
            f"- {person}: {stats['count']} interaction(s), {stats['total_minutes']} min total, "
            f"avg quality {stats['avg_quality']}/10"
        )
    if result["most_frequent_contact"]:
        lines.append(f"Most frequent: {result['most_frequent_contact']}.")
    return "\n".join(lines)
