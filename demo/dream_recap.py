"""
Hermes Life OS - Dream Recap
================================
Summarizes recent dreams logged via log_dream - total dreams, average
vividness, the most common tone, and any symbols or emotions that
recur across multiple dreams. Dreams have no dedicated storage file;
they live only in memory entries (via write_memory), so this reads
from get_recent_memory rather than a load_*() function. Pure local
arithmetic, no new tracking of its own, no network call.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from storage import get_recent_memory


def compute_dream_recap(days: int = 30, min_recurrence: int = 2) -> Dict[str, Any]:
    """Returns {"days", "total_dreams", "avg_vividness", "most_common_tone",
    "recurring_symbols": [(symbol, count), ...],
    "recurring_emotions": [(emotion, count), ...]} over the last `days`
    days. A symbol or emotion is "recurring" once it appears in at
    least `min_recurrence` distinct dreams.
    """
    entries = get_recent_memory(days)
    dreams = [e for e in entries if e.get("type") == "dream"]

    if not dreams:
        return {"days": days, "total_dreams": 0, "avg_vividness": 0.0,
                "most_common_tone": None, "recurring_symbols": [], "recurring_emotions": []}

    total_vividness = sum(d.get("vividness", 0) for d in dreams)
    tones = Counter(d.get("tone", "neutral") for d in dreams)
    most_common_tone = tones.most_common(1)[0][0]

    symbol_counts: Counter = Counter()
    emotion_counts: Counter = Counter()
    for d in dreams:
        symbol_counts.update(set(d.get("symbols", [])))
        emotion_counts.update(set(d.get("emotions", [])))

    recurring_symbols = [(s, c) for s, c in symbol_counts.most_common() if c >= min_recurrence]
    recurring_emotions = [(e, c) for e, c in emotion_counts.most_common() if c >= min_recurrence]

    return {
        "days": days,
        "total_dreams": len(dreams),
        "avg_vividness": round(total_vividness / len(dreams), 1),
        "most_common_tone": most_common_tone,
        "recurring_symbols": recurring_symbols,
        "recurring_emotions": recurring_emotions,
    }


def format_dream_recap(result: Dict[str, Any]) -> str:
    """Turns compute_dream_recap()'s output into a friendly multi-line
    summary."""
    if result["total_dreams"] == 0:
        return f"No dreams logged in the last {result['days']} days."

    lines = [
        f"{result['total_dreams']} dream(s) logged over the last {result['days']} days, "
        f"average vividness {result['avg_vividness']}/10, mostly {result['most_common_tone']} in tone."
    ]
    if result["recurring_symbols"]:
        symbols_str = ", ".join(f"{s} ({c}x)" for s, c in result["recurring_symbols"])
        lines.append(f"Recurring symbols: {symbols_str}.")
    if result["recurring_emotions"]:
        emotions_str = ", ".join(f"{e} ({c}x)" for e, c in result["recurring_emotions"])
        lines.append(f"Recurring emotions: {emotions_str}.")
    return "\n".join(lines)
