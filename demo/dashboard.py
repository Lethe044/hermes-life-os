"""
Hermes Life OS - Dashboard
============================
Turns the pattern-detection and correlation data that already power the
morning/weekly briefings into a single, self-contained HTML report you
can open in any browser - no server, no JS build step.

Usage:
    python demo/dashboard.py                  # last 30 days -> ./hermes-dashboard.html
    python demo/dashboard.py --days 60
    python demo/dashboard.py --out report.html --no-open

Requires matplotlib (see requirements.txt). Uses only data already on
disk (~/.hermes/life-os/memory.jsonl) - makes no LLM calls, needs no
API key, and never touches the network.
"""

from __future__ import annotations

import argparse
import base64
import io
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import matplotlib
    matplotlib.use("Agg")  # headless - no display needed to render charts
    import matplotlib.pyplot as plt
except ImportError:
    print("Dashboard needs matplotlib. Install it with:\n  pip install matplotlib")
    sys.exit(1)

from storage import get_recent_memory, load_habits, MEMORY_FILE
from analytics import daily_averages, compute_correlations, format_correlation_insights
from patterns import detect_patterns

METRIC_LABELS = {
    "mood": ("Mood", "1-10 self-rating"),
    "energy": ("Energy", "1=low 2=medium 3=high"),
    "stress": ("Stress", "1-10 self-rating"),
    "sleep": ("Sleep", "hours"),
    "hydration": ("Hydration", "glasses of water"),
}
METRIC_COLORS = {
    "mood": "#2980b9", "energy": "#e67e22", "stress": "#c0392b",
    "sleep": "#8e44ad", "hydration": "#16a085",
}


def _fig_to_base64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _render_metric_chart(dates: List[str], values: Dict[str, List[float]]) -> str:
    """One combined line chart with every tracked metric, normalized to
    its own axis where scales differ too much to share one (sleep hours
    vs. hydration glasses vs. 1-10 mood, etc.) - so each metric gets its
    own small subplot instead of a misleading shared axis."""
    present = [m for m in METRIC_LABELS if m in values and values[m]]
    if not present:
        return ""

    fig, axes = plt.subplots(len(present), 1, figsize=(9, 2.1 * len(present)), sharex=True)
    if len(present) == 1:
        axes = [axes]

    for ax, metric in zip(axes, present):
        label, unit = METRIC_LABELS[metric]
        color = METRIC_COLORS[metric]
        ys = values[metric]
        xs = dates[-len(ys):]
        ax.plot(xs, ys, marker="o", markersize=3, linewidth=1.6, color=color)
        ax.fill_between(xs, ys, alpha=0.08, color=color)
        ax.set_ylabel(f"{label}\n({unit})", fontsize=8)
        ax.tick_params(axis="both", labelsize=7)
        ax.grid(alpha=0.25, linewidth=0.5)

    axes[-1].tick_params(axis="x", rotation=45)
    fig.tight_layout()
    return _fig_to_base64(fig)


def build_dashboard_data(days: int) -> Dict:
    entries = get_recent_memory(days=days)
    daily = daily_averages(entries)
    ordered_dates = sorted(daily.keys())

    per_metric: Dict[str, List[float]] = {m: [] for m in METRIC_LABELS}
    for d in ordered_dates:
        for m in METRIC_LABELS:
            if m in daily[d]:
                per_metric[m].append(daily[d][m])

    correlations = compute_correlations(entries)
    insights = format_correlation_insights(correlations)
    patterns = detect_patterns()
    habits = load_habits()

    return {
        "dates": ordered_dates,
        "per_metric": per_metric,
        "correlations": correlations,
        "insights": insights,
        "patterns": patterns,
        "habits": habits,
        "entry_count": len(entries),
        "days": days,
    }


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Hermes Life OS - Dashboard</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif;
          background: #0f1115; color: #e6e6e6; margin: 0; padding: 32px; }}
  .wrap {{ max-width: 860px; margin: 0 auto; }}
  h1 {{ font-size: 1.6em; margin-bottom: 4px; }}
  .sub {{ color: #9aa0a6; margin-bottom: 28px; }}
  .card {{ background: #1a1d24; border-radius: 10px; padding: 20px 24px; margin-bottom: 20px;
           border: 1px solid #2a2e37; }}
  .card h2 {{ font-size: 1.05em; margin: 0 0 12px 0; color: #f0f0f0; }}
  img {{ max-width: 100%; border-radius: 6px; }}
  ul {{ margin: 0; padding-left: 20px; }}
  li {{ margin-bottom: 8px; line-height: 1.4; }}
  .empty {{ color: #7a828e; font-style: italic; }}
  .habit {{ display: flex; justify-content: space-between; padding: 6px 0;
            border-bottom: 1px solid #262a33; font-size: 0.92em; }}
  .habit:last-child {{ border-bottom: none; }}
  .streak {{ color: #16a085; font-weight: 600; }}
  .footer {{ color: #6a6f78; font-size: 0.8em; margin-top: 24px; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>🧠 Hermes Life OS - Dashboard</h1>
  <div class="sub">Last {days} days · {entry_count} logged entries · generated {generated_at}</div>

  <div class="card">
    <h2>Trends</h2>
    {chart_html}
  </div>

  <div class="card">
    <h2>Correlations Detected</h2>
    {insights_html}
  </div>

  <div class="card">
    <h2>Habits</h2>
    {habits_html}
  </div>

  <div class="footer">Generated locally from ~/.hermes/life-os/memory.jsonl - no data leaves your machine.</div>
</div>
</body>
</html>
"""


def render_html(data: Dict) -> str:
    chart_b64 = _render_metric_chart(data["dates"], data["per_metric"])
    chart_html = (
        f'<img src="data:image/png;base64,{chart_b64}" alt="Metric trends">'
        if chart_b64 else '<p class="empty">Not enough logged data yet to chart trends. '
                           'Log a few mood/sleep/stress/energy/hydration entries first.</p>'
    )

    if data["insights"]:
        insights_html = "<ul>" + "".join(f"<li>{i}</li>" for i in data["insights"]) + "</ul>"
    else:
        insights_html = '<p class="empty">No strong correlations yet - needs more overlapping days of data across metrics.</p>'

    habits = data["habits"]
    if habits:
        rows = []
        for h in habits:
            rows.append(
                f'<div class="habit"><span>{h.get("name", "?")}</span>'
                f'<span class="streak">{h.get("streak", 0)} day streak '
                f'(best {h.get("best_streak", 0)})</span></div>'
            )
        habits_html = "".join(rows)
    else:
        habits_html = '<p class="empty">No habits tracked yet.</p>'

    return _HTML_TEMPLATE.format(
        days=data["days"],
        entry_count=data["entry_count"],
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        chart_html=chart_html,
        insights_html=insights_html,
        habits_html=habits_html,
    )


def main():
    parser = argparse.ArgumentParser(description="Generate an HTML dashboard from Hermes Life OS data")
    parser.add_argument("--days", type=int, default=30, help="How many days of history to include")
    parser.add_argument("--out", default="hermes-dashboard.html", help="Output HTML file path")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open the report in a browser")
    args = parser.parse_args()

    if not MEMORY_FILE.exists():
        print("No data yet - run a mode like 'onboard' or 'morning' first to start logging.")
        sys.exit(1)

    data = build_dashboard_data(args.days)
    html = render_html(data)

    out_path = Path(args.out).resolve()
    out_path.write_text(html, encoding="utf-8")
    print(f"Dashboard written to {out_path}")

    if not args.no_open:
        webbrowser.open(out_path.as_uri())


if __name__ == "__main__":
    main()
