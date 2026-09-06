"""
Hermes Life OS - Contribution Heatmap
=========================================
A GitHub-style calendar heatmap of your logging activity - darker
squares for more active days, exactly like GitHub's own contribution
graph. Pure SVG, no matplotlib needed, so it's lightweight, fast, and
embeddable (a personal wiki page, a blog post, anywhere that accepts
raw SVG or an <img> pointing at the file).

Usage:
    hermes-life-os-heatmap --days 365 --out heatmap.svg
    hermes-life-os-heatmap --days 90 --out heatmap.html   # wrapped page with stats
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage
from achievements import consecutive_day_streak

# GitHub's own five-level contribution-graph palette (dark theme).
COLOR_LEVELS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]


def compute_daily_counts(days: int) -> Dict[str, int]:
    """{date: entry_count} for every day with at least one memory entry
    in the last `days` days. Days with zero entries are simply absent
    from the dict - render_svg() fills the gaps as empty (level 0)
    squares rather than expecting a zero-padded input."""
    entries = storage.get_recent_memory(days)
    counts: Dict[str, int] = {}
    for e in entries:
        date = str(e.get("timestamp", ""))[:10]
        if date:
            counts[date] = counts.get(date, 0) + 1
    return counts


def compute_stats(counts: Dict[str, int], days: int) -> Dict[str, int]:
    """Summary stats to display alongside the heatmap: total active
    days, total entries, and the current logging streak (reusing
    achievements.py's own streak-counting logic so the two numbers
    never disagree with each other)."""
    return {
        "days": days,
        "active_days": len(counts),
        "total_entries": sum(counts.values()),
        "current_streak": consecutive_day_streak(list(counts.keys())),
    }


def _level_for_count(count: int, max_count: int) -> int:
    if count <= 0:
        return 0
    if max_count <= 1:
        return 4
    ratio = count / max_count
    if ratio > 0.75:
        return 4
    if ratio > 0.5:
        return 3
    if ratio > 0.25:
        return 2
    return 1


def render_svg(counts: Dict[str, int], days: int = 365) -> str:
    """Renders a GitHub-style calendar heatmap as standalone SVG - one
    column per week, one row per weekday (Sunday at the top, matching
    GitHub's own layout), most recent day at the bottom-right."""
    end = datetime.utcnow().date()
    start = end - timedelta(days=days - 1)
    # Align the start back to the most recent Sunday on/before it, so
    # weeks line up into full 7-day columns the way GitHub's graph does.
    start -= timedelta(days=(start.weekday() + 1) % 7)

    max_count = max(counts.values(), default=0)
    cell = 11
    gap = 3
    total_days = (end - start).days + 1
    n_weeks = (total_days + 6) // 7
    width = n_weeks * (cell + gap) + 20
    height = 7 * (cell + gap) + 20

    rects = []
    cursor = start
    week = 0
    while cursor <= end:
        weekday = (cursor.weekday() + 1) % 7  # 0 = Sunday, matching GitHub's convention
        date_str = cursor.strftime("%Y-%m-%d")
        count = counts.get(date_str, 0)
        level = _level_for_count(count, max_count)
        x = 10 + week * (cell + gap)
        y = 10 + weekday * (cell + gap)
        entry_word = "entry" if count == 1 else "entries"
        rects.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" '
            f'fill="{COLOR_LEVELS[level]}"><title>{date_str}: {count} {entry_word}</title></rect>'
        )
        if weekday == 6:
            week += 1
        cursor += timedelta(days=1)

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" fill="#0d1117"/>'
        + "".join(rects) +
        "</svg>"
    )


def render_html(svg: str, stats: Dict[str, int]) -> str:
    """Wraps render_svg()'s output in a minimal standalone HTML page
    with the summary stats shown above it."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Hermes Life OS - Contribution Heatmap</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif;
          background: #0d1117; color: #e6e6e6; margin: 0; padding: 32px;
          display: flex; flex-direction: column; align-items: center; }}
  h1 {{ font-size: 1.3em; margin-bottom: 4px; }}
  .stats {{ color: #9aa0a6; margin-bottom: 20px; font-size: 0.9em; }}
</style>
</head>
<body>
  <h1>Logging Activity</h1>
  <div class="stats">
    {stats['active_days']} active day(s) &middot; {stats['total_entries']} total entries &middot;
    {stats['current_streak']}-day current streak &middot; last {stats['days']} days
  </div>
  {svg}
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a GitHub-style contribution heatmap")
    parser.add_argument("--days", type=int, default=365, help="Lookback window. Default 365.")
    parser.add_argument("--out", default="hermes-heatmap.svg",
                        help="Output path - .svg (raw, embeddable) or .html (wrapped with stats).")
    parser.add_argument("--profile", default=None, help="Profile to summarize. Default: active/default.")
    args = parser.parse_args()

    storage.set_active_profile(args.profile)

    counts = compute_daily_counts(args.days)
    stats = compute_stats(counts, args.days)
    svg = render_svg(counts, args.days)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() == ".html":
        out_path.write_text(render_html(svg, stats), encoding="utf-8")
    else:
        out_path.write_text(svg, encoding="utf-8")

    print(f"Heatmap saved to {out_path} "
          f"({stats['active_days']} active days, {stats['current_streak']}-day current streak)")


if __name__ == "__main__":
    main()
