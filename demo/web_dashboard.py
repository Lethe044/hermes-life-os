"""
Hermes Life OS - Web Dashboard
==================================
An interactive, always-current browser dashboard - the live counterpart
to dashboard.py's static HTML snapshot. Same underlying data
(build_dashboard_data() from dashboard.py: daily metric series,
correlations, retrospective comparison, habit streaks), served as JSON
and rendered client-side with Chart.js, so changing the day-range
re-fetches and re-draws without regenerating a file or reloading the
whole page.

Usage:
    pip install "hermes-life-os[web]"   # or: pip install flask
    hermes-life-os-web
    # open http://127.0.0.1:8080

Localhost-only by default, no API key required (unlike local_api.py) -
this only ever reads your own data for your own browser to render, it
doesn't expose a general-purpose write API. If you change --host to
something other than 127.0.0.1/localhost, anyone who can reach that
address can read your dashboard - same caveat as local_api.py's
docstring, see that file for the reverse-proxy/Tailscale recommendation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage
from dashboard import build_dashboard_data


class WebDashboardError(RuntimeError):
    pass


def _require_flask():
    try:
        from flask import Flask, jsonify, request, Response
        return Flask, jsonify, request, Response
    except ImportError as e:
        raise WebDashboardError(
            "The 'flask' package is required for the web dashboard.\n"
            "  pip install \"hermes-life-os[web]\"   # or: pip install flask"
        ) from e


def dashboard_data_as_json(days: int, compare_days: int) -> Dict[str, Any]:
    """build_dashboard_data() as-is, minus the one non-JSON-friendly
    field (habits' raw objects are already plain dicts, so nothing
    actually needs converting today - this wrapper exists so future
    fields added to build_dashboard_data() get a single place to filter
    or reshape before they hit the wire)."""
    data = build_dashboard_data(days, compare_days)
    return data


def build_app():
    """Constructs and returns the Flask app. Split out from main() so
    tests can build an app instance directly (via Flask's test client)
    without going through argument parsing or app.run()."""
    Flask, jsonify, request, Response = _require_flask()

    app = Flask(__name__)

    @app.route("/")
    def index():
        return Response(_INDEX_HTML, mimetype="text/html")

    @app.route("/api/dashboard-data")
    def dashboard_data():
        days = request.args.get("days", default=30, type=int)
        compare_days = request.args.get("compare_days", default=7, type=int)
        days = max(1, min(days, 365))
        compare_days = max(1, min(compare_days, 90))
        data = dashboard_data_as_json(days, compare_days)
        data["profile"] = storage.ACTIVE_PROFILE
        return jsonify(data)

    return app


_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hermes Life OS - Live Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  :root { color-scheme: dark; }
  body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
         background: #0f1115; color: #e6e6e6; margin: 0; padding: 32px; }
  .wrap { max-width: 900px; margin: 0 auto; }
  h1 { font-size: 1.6em; margin-bottom: 4px; }
  .sub { color: #9aa0a6; margin-bottom: 20px; }
  .controls { display: flex; gap: 12px; align-items: center; margin-bottom: 24px; flex-wrap: wrap; }
  .controls label { font-size: 0.85em; color: #9aa0a6; }
  .controls select, .controls button { background: #1a1d24; color: #e6e6e6; border: 1px solid #2a2e37;
         border-radius: 6px; padding: 6px 10px; font-size: 0.9em; }
  .controls button { cursor: pointer; }
  .controls button:hover { border-color: #16a085; }
  .card { background: #1a1d24; border-radius: 10px; padding: 20px 24px; margin-bottom: 20px;
          border: 1px solid #2a2e37; }
  .card h2 { font-size: 1.05em; margin: 0 0 12px 0; color: #f0f0f0; }
  ul { margin: 0; padding-left: 20px; }
  li { margin-bottom: 8px; line-height: 1.4; }
  .empty { color: #7a828e; font-style: italic; }
  .habit { display: flex; justify-content: space-between; padding: 6px 0;
           border-bottom: 1px solid #262a33; font-size: 0.92em; }
  .habit:last-child { border-bottom: none; }
  .streak { color: #16a085; font-weight: 600; }
  .retro { display: flex; justify-content: space-between; align-items: center; padding: 8px 0;
           border-bottom: 1px solid #262a33; font-size: 0.92em; }
  .retro:last-child { border-bottom: none; }
  .retro-metric { text-transform: capitalize; color: #cfd3da; }
  .retro-values { color: #9aa0a6; font-variant-numeric: tabular-nums; }
  .retro-up { color: #16a085; font-weight: 600; margin-left: 8px; }
  .retro-down { color: #c0392b; font-weight: 600; margin-left: 8px; }
  .retro-flat { color: #9aa0a6; font-weight: 600; margin-left: 8px; }
  .footer { color: #6a6f78; font-size: 0.8em; margin-top: 24px; text-align: center; }
  canvas { max-width: 100%; }
  .loading { color: #7a828e; font-style: italic; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Hermes Life OS - Live Dashboard</h1>
  <div class="sub" id="subheader">Loading...</div>

  <div class="controls">
    <label for="days">Range</label>
    <select id="days">
      <option value="7">Last 7 days</option>
      <option value="14">Last 14 days</option>
      <option value="30" selected>Last 30 days</option>
      <option value="60">Last 60 days</option>
      <option value="90">Last 90 days</option>
    </select>
    <button id="refresh">Refresh</button>
  </div>

  <div class="card">
    <h2>Trends</h2>
    <div id="chartWrap"><p class="loading">Loading chart...</p></div>
  </div>

  <div class="card">
    <h2>Retrospective</h2>
    <div id="retro"><p class="loading">Loading...</p></div>
  </div>

  <div class="card">
    <h2>Correlations Detected</h2>
    <div id="insights"><p class="loading">Loading...</p></div>
  </div>

  <div class="card">
    <h2>Habits</h2>
    <div id="habits"><p class="loading">Loading...</p></div>
  </div>

  <div class="footer">Generated locally from your own data - nothing leaves your machine.</div>
</div>

<script>
const METRIC_LABELS = {
  mood: ["Mood", "#2980b9"], energy: ["Energy", "#e67e22"],
  stress: ["Stress", "#c0392b"], sleep: ["Sleep (hrs)", "#8e44ad"],
  hydration: ["Hydration (glasses)", "#16a085"],
};
const HIGHER_IS_BETTER = { mood: true, energy: true, sleep: true, hydration: true, stress: false };
let chart = null;

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function renderChart(dates, perMetric) {
  const wrap = document.getElementById("chartWrap");
  const present = Object.keys(METRIC_LABELS).filter(m => perMetric[m] && perMetric[m].length);
  if (!present.length) {
    wrap.innerHTML = '<p class="empty">Not enough logged data yet to chart trends.</p>';
    return;
  }
  wrap.innerHTML = '<canvas id="trendChart" height="90"></canvas>';
  const ctx = document.getElementById("trendChart").getContext("2d");
  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: "line",
    data: {
      labels: dates,
      datasets: present.map(m => ({
        label: METRIC_LABELS[m][0],
        data: perMetric[m],
        borderColor: METRIC_LABELS[m][1],
        backgroundColor: METRIC_LABELS[m][1] + "22",
        tension: 0.25, pointRadius: 2, fill: false,
      })),
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: "#e6e6e6" } } },
      scales: {
        x: { ticks: { color: "#9aa0a6" }, grid: { color: "#262a33" } },
        y: { ticks: { color: "#9aa0a6" }, grid: { color: "#262a33" } },
      },
    },
  });
}

function renderRetro(retro) {
  const el = document.getElementById("retro");
  const metrics = Object.keys(retro || {});
  if (!metrics.length) {
    el.innerHTML = '<p class="empty">Not enough data yet to compare periods.</p>';
    return;
  }
  el.innerHTML = metrics.map(metric => {
    const stats = retro[metric];
    const delta = stats.delta;
    let arrow = "\\u2192", cls = "retro-flat";
    const better = HIGHER_IS_BETTER[metric] !== false;
    if (delta > 0) { arrow = "\\u2191"; cls = better ? "retro-up" : "retro-down"; }
    else if (delta < 0) { arrow = "\\u2193"; cls = better ? "retro-down" : "retro-up"; }
    return `<div class="retro"><span class="retro-metric">${escapeHtml(metric)}</span>` +
           `<span><span class="retro-values">${stats.previous} \\u2192 ${stats.current}</span>` +
           `<span class="${cls}">${arrow} ${Math.abs(stats.pct_change)}%</span></span></div>`;
  }).join("");
}

function renderInsights(insights) {
  const el = document.getElementById("insights");
  if (!insights || !insights.length) {
    el.innerHTML = '<p class="empty">No strong correlations yet - needs more overlapping days of data.</p>';
    return;
  }
  el.innerHTML = "<ul>" + insights.map(i => `<li>${escapeHtml(i)}</li>`).join("") + "</ul>";
}

function renderHabits(habits) {
  const el = document.getElementById("habits");
  if (!habits || !habits.length) {
    el.innerHTML = '<p class="empty">No habits tracked yet.</p>';
    return;
  }
  el.innerHTML = habits.map(h =>
    `<div class="habit"><span>${escapeHtml(h.name || "?")}</span>` +
    `<span class="streak">${h.streak || 0} day streak (best ${h.best_streak || 0})</span></div>`
  ).join("");
}

async function load() {
  const days = document.getElementById("days").value;
  const res = await fetch(`/api/dashboard-data?days=${days}&compare_days=7`);
  const data = await res.json();
  document.getElementById("subheader").textContent =
    `Profile: ${data.profile} - Last ${data.days} days - ${data.entry_count} logged entries`;
  renderChart(data.dates, data.per_metric);
  renderRetro(data.retrospective);
  renderInsights(data.insights);
  renderHabits(data.habits);
}

document.getElementById("refresh").addEventListener("click", load);
document.getElementById("days").addEventListener("change", load);
load();
</script>
</body>
</html>
"""


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the Hermes Life OS live web dashboard.")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind address. Default: 127.0.0.1 (localhost only).")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on. Default: 8080.")
    parser.add_argument("--profile", default=None,
                        help="Named profile to serve. Default: 'default'. Can also be set via LIFE_OS_PROFILE.")
    args = parser.parse_args()

    storage.set_active_profile(args.profile or os.environ.get("LIFE_OS_PROFILE"))

    try:
        app = build_app()
    except WebDashboardError as e:
        print(e)
        sys.exit(1)

    print(f"Hermes Life OS web dashboard - profile: {storage.ACTIVE_PROFILE}")
    print(f"Open http://{args.host}:{args.port} in your browser (Ctrl+C to stop)")
    if args.host not in ("127.0.0.1", "localhost"):
        print("WARNING: binding beyond localhost exposes your data to anyone who can reach "
              "this address - see this file's docstring.")
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
