"""
Hermes Life OS - Gratitude Recap
====================================
Summarizes recent gratitude entries logged via log_gratitude - total
entries, total items, and the most frequently recurring words across
them (a lightweight signal for recurring themes, not real NLP). Pure
local arithmetic over data already in mental.json (via load_mental),
no new tracking or storage of its own, no network call.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List

from storage import load_mental

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "for", "of", "to", "in", "on",
    "at", "with", "my", "me", "i", "is", "was", "are", "were", "it", "that",
    "this", "so", "very", "really", "today", "having", "getting", "being",
}


def _tokenize(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-zA-Z']+", text.lower())
            if len(w) > 2 and w not in _STOPWORDS]


def compute_gratitude_recap(days: int = 30, top_n: int = 5) -> Dict[str, Any]:
    """Returns {"days", "total_entries", "total_items",
    "top_words": [(word, count), ...], "recent_items": [...]} over the
    last `days` days. "recent_items" holds up to the 5 most recent
    individual gratitude items, most recent first.
    """
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    entries = [m for m in load_mental()
               if m.get("type") == "gratitude" and m.get("date", "") >= cutoff]

    if not entries:
        return {"days": days, "total_entries": 0, "total_items": 0,
                "top_words": [], "recent_items": []}

    entries.sort(key=lambda e: e.get("date", ""), reverse=True)

    all_items: List[str] = []
    word_counts: Counter = Counter()
    for e in entries:
        items = e.get("items", [])
        all_items.extend(items)
        for item in items:
            word_counts.update(_tokenize(item))

    return {
        "days": days,
        "total_entries": len(entries),
        "total_items": len(all_items),
        "top_words": word_counts.most_common(top_n),
        "recent_items": all_items[:5],
    }


def format_gratitude_recap(result: Dict[str, Any]) -> str:
    """Turns compute_gratitude_recap()'s output into a friendly
    multi-line summary."""
    if result["total_entries"] == 0:
        return f"No gratitude entries logged in the last {result['days']} days."

    lines = [
        f"{result['total_entries']} gratitude entry(ies), {result['total_items']} item(s) "
        f"over the last {result['days']} days."
    ]
    if result["top_words"]:
        words_str = ", ".join(f"{w} ({c})" for w, c in result["top_words"])
        lines.append(f"Recurring themes: {words_str}.")
    if result["recent_items"]:
        lines.append("Recent: " + "; ".join(result["recent_items"]))
    return "\n".join(lines)
