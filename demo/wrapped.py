"""
Hermes Life OS - Wrapped
============================
Generates a single, shareable summary image - "your month/year with
Hermes" - in the spirit of Spotify Wrapped or GitHub's yearly
contribution recap. Entirely local: reads only from data already on
disk, makes no LLM or network calls, and the image never leaves your
machine unless you choose to share it yourself.

Usage:
    python demo/wrapped.py                    # last 30 days -> ./hermes-wrapped.png
    python demo/wrapped.py --days 365 --out my-year.png --title "My 2026"
    hermes-life-os-wrapped --days 7            # a "your week" card

Requires matplotlib (see requirements.txt) - same as demo/dashboard.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import matplotlib
    matplotlib.use("Agg")  # headless - no display needed to render
    import matplotlib.pyplot as plt
except ImportError:
    print("Wrapped needs matplotlib. Install it with:\n  pip install matplotlib")
    sys.exit(1)

from storage import get_recent_memory
from analytics import daily_averages
from life_score import compute_life_score_trend
from achievements import evaluate_achievements

BG_COLOR = "#12141a"
ACCENT = "#6c8cff"
TEXT_COLOR = "#f5f6fa"
DIM_COLOR = "#8b8fa3"


def _avg_metric(daily: Dict[str, Dict[str, float]], metric: str) -> Optional[float]:
    vals = [d[metric] for d in daily.values() if metric in d]
    return round(sum(vals) / len(vals), 1) if vals else None


def build_wrapped_stats(days: int) -> Dict:
    """Gathers every number the card needs into one plain dict - kept
    separate from rendering so it's independently testable without
    matplotlib ever being invoked."""
    entries = get_recent_memory(days)
    daily = daily_averages(entries)

    trend = compute_life_score_trend(days)
    best_day = max(trend, key=lambda t: t["score"]) if trend else None
    avg_life_score = round(sum(t["score"] for t in trend) / len(trend)) if trend else None

    badges = evaluate_achievements()
    earned = [b for b in badges if b["earned"]]

    return {
        "days": days,
        "n_entries": len(entries),
        "n_days_logged": len(daily),
        "avg_mood": _avg_metric(daily, "mood"),
        "avg_sleep": _avg_metric(daily, "sleep"),
        "avg_stress": _avg_metric(daily, "stress"),
        "avg_life_score": avg_life_score,
        "best_day": best_day,
        "earned_badges": earned,
        "trend": trend,
    }


def _period_label(days: int) -> str:
    if days <= 8:
        return "Week"
    if days <= 35:
        return "Month"
    if days <= 100:
        return "Quarter"
    return "Year"


def render_wrapped_image(stats: Dict, out_path: Path, title: Optional[str] = None) -> Path:
    """Renders build_wrapped_stats()'s output as a single PNG card,
    sized for social sharing (a tall, portrait-friendly aspect ratio)."""
    title = title or f"My {_period_label(stats['days'])} with Hermes"

    fig = plt.figure(figsize=(8, 10), facecolor=BG_COLOR)
    fig.patch.set_facecolor(BG_COLOR)

    fig.text(0.5, 0.94, title, ha="center", va="center",
              fontsize=26, weight="bold", color=TEXT_COLOR)
    fig.text(0.5, 0.905, f"Last {stats['days']} days", ha="center", va="center",
              fontsize=12, color=DIM_COLOR)

    score = stats["avg_life_score"]
    fig.text(0.5, 0.76, str(score) if score is not None else "N/A", ha="center", va="center",
              fontsize=72, weight="bold", color=ACCENT)
    fig.text(0.5, 0.685, "Average Life Score", ha="center", va="center",
              fontsize=13, color=DIM_COLOR)

    # Trend sparkline
    trend = stats["trend"]
    if len(trend) >= 2:
        ax = fig.add_axes([0.15, 0.58, 0.7, 0.08])
        ax.set_facecolor(BG_COLOR)
        ys = [t["score"] for t in trend]
        ax.plot(range(len(ys)), ys, color=ACCENT, linewidth=2)
        ax.fill_between(range(len(ys)), ys, alpha=0.15, color=ACCENT)
        ax.axis("off")

    stat_rows = [
        ("Entries logged", stats["n_entries"]),
        ("Days active", stats["n_days_logged"]),
        ("Avg mood", f"{stats['avg_mood']}/10" if stats["avg_mood"] is not None else "N/A"),
        ("Avg sleep", f"{stats['avg_sleep']}h" if stats["avg_sleep"] is not None else "N/A"),
    ]
    y = 0.47
    for label, value in stat_rows:
        fig.text(0.28, y, str(value), ha="right", va="center",
                  fontsize=18, weight="bold", color=TEXT_COLOR)
        fig.text(0.32, y, label, ha="left", va="center",
                  fontsize=13, color=DIM_COLOR)
        y -= 0.055

    best_day = stats["best_day"]
    if best_day:
        fig.text(0.5, 0.20, f"Best day: {best_day['date']} (score {best_day['score']})",
                  ha="center", va="center", fontsize=12, color=DIM_COLOR)

    badges = stats["earned_badges"]
    if badges:
        names = [b["name"] for b in badges[:3]]
        summary = ", ".join(names)
        if len(badges) > 3:
            summary += f", +{len(badges) - 3} more"
        fig.text(0.5, 0.13, f"{len(badges)} badge(s) earned", ha="center", va="center",
                  fontsize=15, weight="bold", color=TEXT_COLOR)
        fig.text(0.5, 0.10, summary, ha="center", va="center",
                  fontsize=9, color=DIM_COLOR, wrap=True)

    fig.text(0.5, 0.03, "Generated by Hermes Life OS", ha="center", va="center",
              fontsize=9, color=DIM_COLOR)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160, facecolor=BG_COLOR)
    plt.close(fig)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a shareable Hermes Life OS Wrapped card")
    parser.add_argument("--days", type=int, default=30, help="Period to summarize. Default 30.")
    parser.add_argument("--out", default="hermes-wrapped.png",
                        help="Output path - .png (default) or .pdf, format is picked from the extension.")
    parser.add_argument("--title", default=None, help="Custom title. Default: 'My <Period> with Hermes'.")
    parser.add_argument("--profile", default=None, help="Profile to summarize. Default: active/default.")
    args = parser.parse_args()

    import storage
    storage.set_active_profile(args.profile)

    stats = build_wrapped_stats(args.days)
    if stats["n_entries"] == 0:
        print(f"No entries logged in the last {args.days} days - nothing to wrap yet.")
        sys.exit(1)

    out_path = render_wrapped_image(stats, Path(args.out), title=args.title)
    print(f"Wrapped card saved to {out_path}")


if __name__ == "__main__":
    main()
