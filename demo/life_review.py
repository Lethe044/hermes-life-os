"""
Hermes Life OS - Life Review
================================
A comprehensive quarterly/yearly retrospective - the "big" report that
ties together everything the rest of Hermes tracks: Life Score trend,
correlations (same-day and lagged), pattern detection, achievements
earned, and a period-over-period comparison against the equivalent
stretch before it. Self-contained HTML, same "no server, no JS build
step" approach as demo/dashboard.py, just built for a much longer
lookback window (a quarter or a year, rather than the dashboard's
default 30 days).

Usage:
    python demo/life_review.py --days 90              # a quarter
    python demo/life_review.py --days 365 --out my-year-review.html
    hermes-life-os-review --days 90 --no-open

Requires matplotlib (see requirements.txt). Uses only data already on
disk - makes no LLM calls, needs no API key, and never touches the
network. Weather correlation is intentionally NOT included here (it's
the one feature that does touch the network) - ask for it separately
via the get_weather_correlation tool if wanted.
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import matplotlib
    matplotlib.use("Agg")  # headless - no display needed to render charts
    import matplotlib.pyplot as plt
except ImportError:
    print("Life Review needs matplotlib. Install it with:\n  pip install matplotlib")
    sys.exit(1)

import storage
from storage import get_recent_memory, get_memory_window, load_habits
from analytics import (
    compute_correlations, format_correlation_insights,
    compute_lagged_correlations_multi, format_lagged_insights,
    compare_periods,
)
from patterns import detect_patterns
from life_score import compute_life_score_trend
from achievements import evaluate_achievements
from dashboard import _fig_to_base64  # reuse chart -> base64 helper for visual consistency


def _life_score_chart(trend: List[Dict[str, Any]]) -> str:
    if len(trend) < 2:
        return ""
    fig, ax = plt.subplots(figsize=(9, 3))
    dates = [t["date"] for t in trend]
    scores = [t["score"] for t in trend]
    ax.plot(dates, scores, marker="o", markersize=3, linewidth=1.8, color="#6c8cff")
    ax.fill_between(dates, scores, alpha=0.12, color="#6c8cff")
    ax.set_ylim(0, 100)
    ax.set_ylabel("Life Score")
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    ax.grid(alpha=0.25, linewidth=0.5)
    fig.tight_layout()
    return _fig_to_base64(fig)


def _period_label(days: int) -> str:
    if days <= 35:
        return "Month"
    if days <= 100:
        return "Quarter"
    return "Year"


def build_life_review_data(days: int = 90, compare_days: Optional[int] = None) -> Dict[str, Any]:
    """Gathers every number the report needs into one plain dict,
    entirely separate from HTML rendering so it's independently
    testable without matplotlib ever being invoked."""
    compare_days = compare_days or days
    entries = get_recent_memory(days)

    correlations = compute_correlations(entries)
    insights = format_correlation_insights(correlations)
    lagged = compute_lagged_correlations_multi(entries)
    insights = insights + format_lagged_insights(lagged)

    current_period = get_recent_memory(compare_days)
    previous_period = get_memory_window(compare_days * 2, compare_days)
    retrospective = compare_periods(current_period, previous_period)

    trend = compute_life_score_trend(days)
    avg_score = round(sum(t["score"] for t in trend) / len(trend)) if trend else None
    best_day = max(trend, key=lambda t: t["score"]) if trend else None
    worst_day = min(trend, key=lambda t: t["score"]) if trend else None

    badges = evaluate_achievements()
    earned = [b for b in badges if b["earned"]]

    return {
        "days": days,
        "compare_days": compare_days,
        "period_label": _period_label(days),
        "entry_count": len(entries),
        "trend": trend,
        "avg_life_score": avg_score,
        "best_day": best_day,
        "worst_day": worst_day,
        "insights": insights,
        "retrospective": retrospective,
        "patterns": detect_patterns(),
        "habits": load_habits(),
        "earned_badges": earned,
    }


def _retrospective_html(retrospective: Dict[str, Dict[str, float]]) -> str:
    if not retrospective:
        return '<div class="empty">Not enough data in both periods to compare yet.</div>'
    rows = []
    for metric, r in sorted(retrospective.items()):
        arrow_class = "retro-up" if r["delta"] > 0 else "retro-down" if r["delta"] < 0 else "retro-flat"
        arrow = "\u2191" if r["delta"] > 0 else "\u2193" if r["delta"] < 0 else "="
        rows.append(
            f'<div class="retro"><span class="retro-metric">{metric}</span>'
            f'<span class="retro-values">{r["previous"]:.1f} -&gt; {r["current"]:.1f}'
            f'<span class="{arrow_class}">{arrow} {abs(r["pct_change"]):.0f}%</span></span></div>'
        )
    return "".join(rows)


def _insights_html(insights: List[str]) -> str:
    if not insights:
        return '<div class="empty">No strong correlations detected yet - keep logging.</div>'
    return "<ul>" + "".join(f"<li>{i}</li>" for i in insights) + "</ul>"


def _habits_html(habits: List[Dict[str, Any]]) -> str:
    if not habits:
        return '<div class="empty">No habits tracked yet.</div>'
    rows = []
    for h in habits:
        rows.append(
            f'<div class="habit"><span>{h.get("name", "")}</span>'
            f'<span class="streak">{h.get("best_streak", h.get("streak", 0))}-day best streak</span></div>'
        )
    return "".join(rows)


def _badges_html(badges: List[Dict[str, Any]]) -> str:
    if not badges:
        return '<div class="empty">No achievements earned yet this period.</div>'
    return "<ul>" + "".join(f"<li>{b['name']} - {b['description']}</li>" for b in badges) + "</ul>"


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Hermes Life OS - Life Review</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif;
          background: #0f1115; color: #e6e6e6; margin: 0; padding: 32px; }}
  .wrap {{ max-width: 860px; margin: 0 auto; }}
  h1 {{ font-size: 1.8em; margin-bottom: 4px; }}
  .sub {{ color: #9aa0a6; margin-bottom: 28px; }}
  .card {{ background: #1a1d24; border-radius: 10px; padding: 20px 24px; margin-bottom: 20px;
           border: 1px solid #2a2e37; }}
  .card h2 {{ font-size: 1.05em; margin: 0 0 12px 0; color: #f0f0f0; }}
  .score-hero {{ display: flex; align-items: baseline; gap: 16px; }}
  .score-number {{ font-size: 3.2em; font-weight: 700; color: #6c8cff; }}
  .score-label {{ color: #9aa0a6; }}
  img {{ max-width: 100%; border-radius: 6px; }}
  ul {{ margin: 0; padding-left: 20px; }}
  li {{ margin-bottom: 8px; line-height: 1.4; }}
  .empty {{ color: #7a828e; font-style: italic; }}
  .habit {{ display: flex; justify-content: space-between; padding: 6px 0;
            border-bottom: 1px solid #262a33; font-size: 0.92em; }}
  .habit:last-child {{ border-bottom: none; }}
  .streak {{ color: #16a085; font-weight: 600; }}
  .retro {{ display: flex; justify-content: space-between; align-items: center; padding: 8px 0;
            border-bottom: 1px solid #262a33; font-size: 0.92em; }}
  .retro:last-child {{ border-bottom: none; }}
  .retro-metric {{ text-transform: capitalize; color: #cfd3da; }}
  .retro-values {{ color: #9aa0a6; font-variant-numeric: tabular-nums; }}
  .retro-up {{ color: #16a085; font-weight: 600; margin-left: 8px; }}
  .retro-down {{ color: #c0392b; font-weight: 600; margin-left: 8px; }}
  .retro-flat {{ color: #9aa0a6; font-weight: 600; margin-left: 8px; }}
  .best-day {{ color: #9aa0a6; font-size: 0.9em; margin-top: 8px; }}
  .footer {{ color: #6a6f78; font-size: 0.8em; margin-top: 24px; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>My {period_label} with Hermes</h1>
  <div class="sub">Profile: {profile} &middot; Last {days} days &middot; {entry_count} logged entries &middot; generated {generated_at}</div>

  <div class="card">
    <h2>Life Score</h2>
    <div class="score-hero">
      <span class="score-number">{avg_score}</span>
      <span class="score-label">average over the period</span>
    </div>
    {life_score_chart_html}
    <div class="best-day">{best_worst_html}</div>
  </div>

  <div class="card">
    <h2>Retrospective - last {compare_days} days vs. the {compare_days} before</h2>
    {retrospective_html}
  </div>

  <div class="card">
    <h2>Correlations Detected</h2>
    {insights_html}
  </div>

  <div class="card">
    <h2>Achievements Earned</h2>
    {badges_html}
  </div>

  <div class="card">
    <h2>Habits</h2>
    {habits_html}
  </div>

  <div class="footer">Generated locally from {memory_path} - no data leaves your machine.</div>
</div>
</body>
</html>
"""


def render_html(data: Dict[str, Any]) -> str:
    chart_html = ""
    chart_b64 = _life_score_chart(data["trend"])
    if chart_b64:
        chart_html = f'<img src="data:image/png;base64,{chart_b64}" alt="Life Score trend">'

    best_worst = ""
    if data["best_day"] and data["worst_day"]:
        best_worst = (
            f"Best day: {data['best_day']['date']} (score {data['best_day']['score']}) &middot; "
            f"Toughest day: {data['worst_day']['date']} (score {data['worst_day']['score']})"
        )

    return _HTML_TEMPLATE.format(
        period_label=data["period_label"],
        profile=storage.ACTIVE_PROFILE,
        days=data["days"],
        entry_count=data["entry_count"],
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        avg_score=data["avg_life_score"] if data["avg_life_score"] is not None else "N/A",
        life_score_chart_html=chart_html,
        best_worst_html=best_worst,
        compare_days=data["compare_days"],
        retrospective_html=_retrospective_html(data["retrospective"]),
        insights_html=_insights_html(data["insights"]),
        badges_html=_badges_html(data["earned_badges"]),
        habits_html=_habits_html(data["habits"]),
        memory_path=storage.MEMORY_FILE,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a Hermes Life OS Life Review report")
    parser.add_argument("--days", type=int, default=90, help="Period to review. Default 90 (a quarter).")
    parser.add_argument("--compare-days", type=int, default=None,
                        help="Retrospective comparison window. Default: same as --days.")
    parser.add_argument("--out", default="hermes-life-review.html", help="Output HTML path.")
    parser.add_argument("--profile", default=None, help="Profile to review. Default: active/default.")
    parser.add_argument("--no-open", action="store_true", help="Don't open the report in a browser.")
    args = parser.parse_args()

    storage.set_active_profile(args.profile)

    data = build_life_review_data(args.days, args.compare_days)
    html = render_html(data)

    out_path = Path(args.out)
    out_path.write_text(html, encoding="utf-8")
    print(f"Life Review saved to {out_path}")

    if not args.no_open:
        webbrowser.open(out_path.as_uri())


if __name__ == "__main__":
    main()
