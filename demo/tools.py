"""
Hermes Life OS - Tool Implementations
========================================
The dispatch_tool() function and TOOLS schema list that the LLM agent
calls into: logging meals/sleep/workouts/stress/meditation/focus/dreams,
updating habits and goals, running pattern detection, building health
dashboards, and delivering briefings.

Extracted from the original monolithic demo_life_os.py.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict

from rich.console import Console
from rich.panel import Panel
import shutil

from storage import (
    load_nutrition, save_nutrition,
    load_sleep, save_sleep,
    load_hydration, save_hydration,
    load_fitness, save_fitness,
    load_focus, save_focus,
    load_mental, save_mental,
    load_habits, save_habits,
    load_goals, save_goals,
    load_profile, save_profile,
    write_memory, search_memory, get_recent_memory, memory_count,
    edit_memory_entry, delete_memory_entry, get_memory_window, get_all_memory,
    get_memory_by_date_range,
)
from patterns import detect_patterns
from analytics import (
    compute_goal_progress, compare_periods, compare_before_after,
    detect_anomalies, daily_averages, TRACKABLE_METRICS,
)

console = Console(width=min(110, shutil.get_terminal_size().columns))

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def dispatch_tool(name: str, inp: Dict[str, Any]) -> str:

    # ── remember ──────────────────────────────────────────────────────────────
    if name == "remember":
        entry = {k: v for k, v in inp.items()}
        write_memory(entry)
        return (f"Remembered [id={entry['id']}]: [{inp.get('type','note')}] "
                f"{str(inp.get('content', inp.get('description','')))[:80]}")

    # ── recall ────────────────────────────────────────────────────────────────
    elif name == "recall":
        results = search_memory(inp.get("query", ""), limit=8)
        if not results:
            return f"Nothing found for '{inp.get('query','')}'."
        return "\n".join(
            f"[id={r.get('id','?')}] [{r.get('type','?')}] "
            f"{str(r.get('content', r.get('description','')))[:100]}"
            for r in results[-5:]
        )

    # ── correct_entry ────────────────────────────────────────────────────────
    elif name == "correct_entry":
        entry_id = inp.get("entry_id", "")
        updates = inp.get("updates", {})
        if not isinstance(updates, dict) or not updates:
            return "No updates provided - specify at least one field to change."
        if edit_memory_entry(entry_id, updates):
            return f"Updated entry [id={entry_id}] with {updates}."
        return (f"No entry found with id '{entry_id}'. Use recall first to find "
                f"the id of the entry you want to correct.")

    # ── delete_entry ─────────────────────────────────────────────────────────
    elif name == "delete_entry":
        entry_id = inp.get("entry_id", "")
        if delete_memory_entry(entry_id):
            return f"Deleted entry [id={entry_id}]. This can't be undone."
        return (f"No entry found with id '{entry_id}'. Use recall first to find "
                f"the id of the entry you want to delete.")

    # ── log_meal ──────────────────────────────────────────────────────────────
    elif name == "log_meal":
        meal = {
            "date":     time.strftime("%Y-%m-%d"),
            "time":     inp.get("meal_time", "unknown"),
            "food":     inp.get("food", ""),
            "calories": inp.get("calories", 0),
            "protein":  inp.get("protein_g", 0),
            "carbs":    inp.get("carbs_g", 0),
            "fat":      inp.get("fat_g", 0),
            "notes":    inp.get("notes", ""),
        }
        nutrition = load_nutrition()
        nutrition.append(meal)
        save_nutrition(nutrition)
        write_memory({"type": "meal", "content": inp.get("food", ""),
                      "calories": inp.get("calories", 0), "meal_time": inp.get("meal_time", "")})
        today_meals = [m for m in nutrition if m["date"] == time.strftime("%Y-%m-%d")]
        total_cal = sum(m.get("calories", 0) for m in today_meals)
        return (f"Meal logged: {inp.get('food','')} ({inp.get('calories',0)} cal)\n"
                f"Today's total: {total_cal} calories across {len(today_meals)} meals.")

    # ── log_sleep ─────────────────────────────────────────────────────────────
    elif name == "log_sleep":
        entry = {
            "date":      time.strftime("%Y-%m-%d"),
            "bedtime":   inp.get("bedtime", ""),
            "wake_time": inp.get("wake_time", ""),
            "hours":     inp.get("hours", 0),
            "quality":   inp.get("quality", 5),
            "notes":     inp.get("notes", ""),
        }
        sleep_log = load_sleep()
        sleep_log.append(entry)
        save_sleep(sleep_log)
        write_memory({"type": "sleep", "content": f"{inp.get('hours',0)}h sleep",
                      "hours": inp.get("hours", 0), "quality": inp.get("quality", 5)})
        avg_quality = sum(s.get("quality", 5) for s in sleep_log[-7:]) / min(7, len(sleep_log))
        avg_hours   = sum(s.get("hours", 0) for s in sleep_log[-7:]) / min(7, len(sleep_log))
        return (f"Sleep logged: {inp.get('hours',0)}h (quality: {inp.get('quality',5)}/10)\n"
                f"7-day average: {avg_hours:.1f}h at quality {avg_quality:.1f}/10")

    # ── log_hydration ─────────────────────────────────────────────────────────
    elif name == "log_hydration":
        glasses = inp.get("glasses", 1)
        hydration = load_hydration()
        today = time.strftime("%Y-%m-%d")
        if hydration.get("last_date") != today:
            hydration["today"] = 0
            hydration["last_date"] = today
        hydration["today"] = hydration.get("today", 0) + glasses
        hydration.setdefault("log", []).append({"date": today, "glasses": glasses,
                                                  "time": time.strftime("%H:%M")})
        save_hydration(hydration)
        write_memory({"type": "hydration", "content": f"{glasses} glasses water",
                      "glasses": hydration["today"]})
        goal   = hydration.get("goal", 8)
        total  = hydration["today"]
        pct    = min(100, int(total / goal * 100))
        bar    = "█" * (pct // 10) + "░" * (10 - pct // 10)
        return (f"Logged {glasses} glass(es). Today: {total}/{goal} glasses\n"
                f"Progress: [{bar}] {pct}%")

    # ── log_workout ───────────────────────────────────────────────────────────
    elif name == "log_workout":
        entry = {
            "date":      time.strftime("%Y-%m-%d"),
            "type":      inp.get("workout_type", ""),
            "duration":  inp.get("duration_min", 0),
            "intensity": inp.get("intensity", "medium"),
            "calories":  inp.get("calories_burned", 0),
            "notes":     inp.get("notes", ""),
        }
        fitness = load_fitness()
        fitness.append(entry)
        save_fitness(fitness)
        write_memory({"type": "workout", "content": f"{inp.get('workout_type','')} {inp.get('duration_min',0)}min",
                      "workout_type": inp.get("workout_type", ""), "duration": inp.get("duration_min", 0)})
        this_week = [f for f in fitness if
                     datetime.strptime(f["date"], "%Y-%m-%d") >=
                     datetime.utcnow() - timedelta(days=7)]
        return (f"Workout logged: {inp.get('workout_type','')} for {inp.get('duration_min',0)} min\n"
                f"This week: {len(this_week)} workout(s)")

    # ── log_stress ────────────────────────────────────────────────────────────
    elif name == "log_stress":
        entry = {
            "date":    time.strftime("%Y-%m-%d"),
            "score":   inp.get("score", 5),
            "trigger": inp.get("trigger", ""),
            "notes":   inp.get("notes", ""),
        }
        mental = load_mental()
        mental.append(entry)
        save_mental(mental)
        write_memory({"type": "stress", "content": inp.get("trigger", "stress logged"),
                      "score": inp.get("score", 5)})
        recent_stress = [m for m in mental[-7:] if m.get("score")]
        avg = sum(m["score"] for m in recent_stress) / len(recent_stress) if recent_stress else 0
        return (f"Stress logged: {inp.get('score',5)}/10 - trigger: {inp.get('trigger','')}\n"
                f"7-day stress average: {avg:.1f}/10")

    # ── log_meditation ────────────────────────────────────────────────────────
    elif name == "log_meditation":
        duration = inp.get("duration_min", 10)
        mental   = load_mental()
        entry = {"date": time.strftime("%Y-%m-%d"), "type": "meditation",
                 "duration": duration, "notes": inp.get("notes", "")}
        mental.append(entry)
        save_mental(mental)
        write_memory({"type": "meditation", "content": f"{duration}min meditation",
                      "duration": duration})
        total_sessions = sum(1 for m in mental if m.get("type") == "meditation")
        return f"Meditation logged: {duration} minutes. Total sessions: {total_sessions}"

    # ── log_gratitude ─────────────────────────────────────────────────────────
    elif name == "log_gratitude":
        items = inp.get("items", [])
        mental = load_mental()
        entry = {"date": time.strftime("%Y-%m-%d"), "type": "gratitude",
                 "items": items, "notes": inp.get("notes", "")}
        mental.append(entry)
        save_mental(mental)
        write_memory({"type": "gratitude", "content": ", ".join(items[:3])})
        return f"Gratitude logged: {', '.join(items[:3])}"

    # ── log_focus_session ─────────────────────────────────────────────────────
    elif name == "log_focus_session":
        entry = {
            "date":        time.strftime("%Y-%m-%d"),
            "duration":    inp.get("duration_min", 25),
            "task":        inp.get("task", ""),
            "completed":   inp.get("completed", True),
            "distractions": inp.get("distractions", 0),
            "quality":     inp.get("quality", 7),
        }
        focus = load_focus()
        focus.append(entry)
        save_focus(focus)
        write_memory({"type": "focus", "content": inp.get("task", "focus session"),
                      "duration": inp.get("duration_min", 25),
                      "quality": inp.get("quality", 7)})
        today_focus = [f for f in focus if f["date"] == time.strftime("%Y-%m-%d")]
        total_min   = sum(f.get("duration", 0) for f in today_focus)
        return (f"Focus session logged: {inp.get('duration_min',25)} min on '{inp.get('task','')}'\n"
                f"Today's deep work: {total_min} minutes across {len(today_focus)} sessions")

    # ── update_habit ──────────────────────────────────────────────────────────
    elif name == "update_habit":
        name_h    = inp.get("habit_name", "")
        completed = inp.get("completed", True)
        habits    = load_habits()
        found     = False
        for h in habits:
            if h["name"].lower() == name_h.lower():
                if completed:
                    h["streak"]    = h.get("streak", 0) + 1
                    h["last_done"] = time.strftime("%Y-%m-%d")
                    h["best_streak"] = max(h.get("best_streak", 0), h["streak"])
                else:
                    h["streak"] = 0
                found = True
                break
        if not found:
            habits.append({
                "name": name_h, "streak": 1 if completed else 0,
                "best_streak": 1 if completed else 0,
                "last_done": time.strftime("%Y-%m-%d") if completed else None,
                "created": time.strftime("%Y-%m-%d"),
            })
        save_habits(habits)
        streak = next((h["streak"] for h in habits if h["name"].lower() == name_h.lower()), 0)
        best   = next((h.get("best_streak",0) for h in habits if h["name"].lower() == name_h.lower()), 0)
        return f"Habit '{name_h}': streak {streak} days (best: {best})"

    # ── update_goal ───────────────────────────────────────────────────────────
    elif name == "update_goal":
        goal_name = inp.get("goal_name", "")
        progress  = inp.get("progress", None)
        note      = inp.get("note", "")
        metric    = inp.get("metric")
        target    = inp.get("target")
        direction = inp.get("direction", "at_least")
        window_days = inp.get("window_days", 7)

        goals     = load_goals()
        found     = False
        goal_ref  = None
        for g in goals:
            if g["name"].lower() == goal_name.lower():
                if metric:
                    g["metric"] = metric
                    g["target"] = target
                    g["direction"] = direction
                    g["window_days"] = window_days
                if progress is not None and "metric" not in g:
                    g["progress"] = progress
                g["last_updated"] = time.strftime("%Y-%m-%d")
                if note:
                    g["last_note"] = note
                found = True
                goal_ref = g
                break
        if not found:
            goal_ref = {"name": goal_name, "progress": progress or 0,
                        "created": time.strftime("%Y-%m-%d"),
                        "last_updated": time.strftime("%Y-%m-%d"), "last_note": note}
            if metric:
                goal_ref["metric"] = metric
                goal_ref["target"] = target
                goal_ref["direction"] = direction
                goal_ref["window_days"] = window_days
            goals.append(goal_ref)

        if goal_ref.get("metric"):
            entries = get_recent_memory(days=goal_ref.get("window_days", 7))
            computed = compute_goal_progress(goal_ref, entries)
            if computed is not None:
                goal_ref["progress"] = computed

        save_goals(goals)
        if goal_ref.get("metric"):
            return (f"Goal '{goal_name}' now auto-tracks {goal_ref['metric']} "
                    f"({direction.replace('_', ' ')} {target}): {goal_ref['progress']}% - {note}")
        return f"Goal '{goal_name}': {goal_ref['progress']}% - {note}"

    # ── check_goal_progress ──────────────────────────────────────────────────
    elif name == "check_goal_progress":
        goals = load_goals()
        if not goals:
            return "No goals set yet."
        lines = []
        for g in goals:
            if g.get("metric"):
                entries = get_recent_memory(days=g.get("window_days", 7))
                computed = compute_goal_progress(g, entries)
                if computed is not None:
                    g["progress"] = computed
                lines.append(
                    f"{g['name']}: {g.get('progress', 0)}% "
                    f"(auto-tracked: {g['metric']} {g.get('direction','at_least').replace('_',' ')} "
                    f"{g.get('target')}, last {g.get('window_days',7)} days)"
                )
            else:
                lines.append(f"{g['name']}: {g.get('progress', 0)}% (manually tracked)")
        save_goals(goals)
        return "\n".join(lines)

    # ── compare_periods ──────────────────────────────────────────────────────
    elif name == "compare_periods":
        window = inp.get("window_days", 7)
        current = get_recent_memory(days=window)
        previous = get_memory_window(window * 2, window)
        comparison = compare_periods(current, previous)
        if not comparison:
            return (f"Not enough data yet to compare the last {window} days to the "
                    f"{window} before that - need overlapping days of the same metric "
                    f"in both periods.")
        lines = []
        for metric, stats in comparison.items():
            arrow = "up" if stats["delta"] > 0 else ("down" if stats["delta"] < 0 else "flat")
            lines.append(
                f"{metric}: {stats['previous']} -> {stats['current']} "
                f"({arrow} {abs(stats['pct_change'])}%)"
            )
        return "\n".join(lines)

    # ── compare_before_after ─────────────────────────────────────────────────
    elif name == "compare_before_after":
        changepoint = inp.get("date", "")
        entries = get_all_memory()
        comparison = compare_before_after(entries, changepoint)
        if not comparison:
            return (f"Not enough data around {changepoint} to compare before/after - "
                    f"need logged entries on both sides of that date, and a valid "
                    f"YYYY-MM-DD date.")
        lines = []
        for metric, stats in comparison.items():
            arrow = "up" if stats["delta"] > 0 else ("down" if stats["delta"] < 0 else "flat")
            lines.append(
                f"{metric}: {stats['previous']} (before {changepoint}) -> "
                f"{stats['current']} (since {changepoint}) ({arrow} {abs(stats['pct_change'])}%)"
            )
        return "\n".join(lines)

    # ── check_anomalies ──────────────────────────────────────────────────────
    elif name == "check_anomalies":
        window = inp.get("window_days", 30)
        entries = get_recent_memory(days=window)
        anomalies = detect_anomalies(entries)
        if not anomalies:
            return f"No unusual days detected in the last {window} days."
        lines = []
        for a in anomalies[:5]:
            lines.append(
                f"{a['date']}: {a['metric']} was {a['value']} - unusually {a['direction']} "
                f"your recent average of {a['mean']} (z={a['z_score']})"
            )
        return "\n".join(lines)

    # ── get_period_summary ───────────────────────────────────────────────────
    elif name == "get_period_summary":
        start = inp.get("start_date", "")
        end = inp.get("end_date", "")
        entries = get_memory_by_date_range(start, end)
        if not entries:
            return (f"No logged data found between {start} and {end}. Double-check "
                     f"the dates are valid YYYY-MM-DD and that period was actually logged.")

        daily = daily_averages(entries)
        lines = [f"Period {start} to {end}: {len(entries)} entries across {len(daily)} logged days."]

        for metric in TRACKABLE_METRICS:
            values = [d[metric] for d in daily.values() if metric in d]
            if values:
                lines.append(f"  avg {metric}: {round(sum(values) / len(values), 2)}")

        notable = [
            e for e in entries
            if e.get("type") in ("gratitude", "dream") or e.get("note") or e.get("content")
        ]
        if notable:
            lines.append("Notable entries:")
            for e in notable[:5]:
                text = e.get("content") or e.get("note") or e.get("description") or ""
                date = e.get("timestamp", "")[:10]
                lines.append(f"  [{date}] {e.get('type', '?')}: {str(text)[:100]}")

        return "\n".join(lines)

    # ── detect_patterns ───────────────────────────────────────────────────────
    elif name == "detect_patterns":
        p = detect_patterns()
        parts = []
        for key in ["mood_trend", "energy_trend", "sleep_trend",
                    "hydration_trend", "stress_trend", "nutrition_trend"]:
            if p.get(key):
                parts.append(f"{key.replace('_trend','').title()} trend: {p[key]}")
        if p["wins"]:
            parts.append(f"Recent wins: {', '.join(p['wins'][:3])}")
        if p["struggles"]:
            parts.append(f"Open struggles: {', '.join(p['struggles'][:2])}")
        if p["correlations"]:
            parts.extend(p["correlations"])
        for insight in p["insights"]:
            parts.append(f"Insight: {insight}")
        return "\n".join(parts) if parts else "Not enough data yet for pattern detection."

    # ── get_health_dashboard ──────────────────────────────────────────────────
    elif name == "get_health_dashboard":
        today      = time.strftime("%Y-%m-%d")
        nutrition  = load_nutrition()
        sleep_log  = load_sleep()
        hydration  = load_hydration()
        fitness    = load_fitness()
        focus_log  = load_focus()
        mental     = load_mental()
        habits     = load_habits()
        goals      = load_goals()

        today_meals    = [m for m in nutrition if m.get("date") == today]
        today_cal      = sum(m.get("calories", 0) for m in today_meals)
        today_water    = hydration.get("today", 0)
        last_sleep     = sleep_log[-1] if sleep_log else {}
        today_workouts = [f for f in fitness if f.get("date") == today]
        today_focus    = [f for f in focus_log if f.get("date") == today]
        today_focus_min = sum(f.get("duration", 0) for f in today_focus)
        active_habits  = [h for h in habits if h.get("streak", 0) > 0]
        active_goals   = [g for g in goals if g.get("progress", 0) < 100]

        dashboard = {
            "today": today,
            "nutrition": {
                "meals_today": len(today_meals),
                "calories_today": today_cal,
                "foods": [m.get("food", "") for m in today_meals],
            },
            "hydration": {
                "glasses_today": today_water,
                "goal": hydration.get("goal", 8),
                "pct": min(100, int(today_water / hydration.get("goal", 8) * 100)),
            },
            "sleep": {
                "last_night_hours": last_sleep.get("hours", 0),
                "last_night_quality": last_sleep.get("quality", 0),
            },
            "fitness": {
                "workouts_today": len(today_workouts),
                "types": [w.get("type", "") for w in today_workouts],
            },
            "focus": {
                "deep_work_minutes": today_focus_min,
                "sessions": len(today_focus),
            },
            "habits": {
                "active_count": len(active_habits),
                "top_streaks": sorted(
                    [(h["name"], h.get("streak", 0)) for h in active_habits],
                    key=lambda x: -x[1]
                )[:3],
            },
            "goals": {
                "active_count": len(active_goals),
                "list": [(g["name"], g.get("progress", 0)) for g in active_goals[:3]],
            },
        }
        return json.dumps(dashboard, indent=2, ensure_ascii=False)

    # ── get_weekly_health_report ──────────────────────────────────────────────
    elif name == "get_weekly_health_report":
        cutoff     = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
        nutrition  = [m for m in load_nutrition()  if m.get("date", "") >= cutoff]
        sleep_log  = [s for s in load_sleep()       if s.get("date", "") >= cutoff]
        fitness    = [f for f in load_fitness()     if f.get("date", "") >= cutoff]
        focus_log  = [f for f in load_focus()       if f.get("date", "") >= cutoff]
        mental     = [m for m in load_mental()      if m.get("date", "") >= cutoff]

        avg_sleep    = (sum(s.get("hours", 0) for s in sleep_log) / len(sleep_log)) if sleep_log else 0
        avg_sleep_q  = (sum(s.get("quality", 0) for s in sleep_log) / len(sleep_log)) if sleep_log else 0
        total_cal    = sum(m.get("calories", 0) for m in nutrition)
        total_workout = len(fitness)
        total_focus  = sum(f.get("duration", 0) for f in focus_log)
        stress_scores = [m.get("score", 0) for m in mental if m.get("type") == "stress" and m.get("score")]
        avg_stress   = (sum(stress_scores) / len(stress_scores)) if stress_scores else 0
        meditations  = [m for m in mental if m.get("type") == "meditation"]

        report = {
            "period": f"Last 7 days (since {cutoff})",
            "sleep":  {"avg_hours": round(avg_sleep, 1), "avg_quality": round(avg_sleep_q, 1), "nights_logged": len(sleep_log)},
            "nutrition": {"total_calories": total_cal, "meals_logged": len(nutrition),
                          "avg_daily_cal": round(total_cal / 7, 0)},
            "fitness": {"workouts": total_workout,
                        "types": list(set(f.get("type", "") for f in fitness))},
            "focus":   {"total_minutes": total_focus, "sessions": len(focus_log),
                        "avg_session_min": round(total_focus / len(focus_log), 1) if focus_log else 0},
            "mental":  {"avg_stress": round(avg_stress, 1), "meditation_sessions": len(meditations),
                        "total_meditation_min": sum(m.get("duration", 0) for m in meditations)},
        }
        return json.dumps(report, indent=2, ensure_ascii=False)

    # ── send_briefing ─────────────────────────────────────────────────────────
    elif name == "send_briefing":
        content       = inp.get("content", "").replace("\\n", "\n").replace("\\\\n", "\n")
        briefing_type = inp.get("type", "morning")
        titles = {
            "morning":   "🌅 Morning Briefing",
            "midday":    "☀️  Midday Check-in",
            "evening":   "🌙 Evening Reflection",
            "weekly":    "📋 Weekly Review",
            "nutrition": "🥗 Nutrition Insight",
            "sleep":     "😴 Sleep Analysis",
            "health":    "❤️  Health Dashboard",
            "fitness":   "💪 Fitness Summary",
            "mental":    "🧘 Mental Wellness",
            "focus":     "🎯 Focus Report",
        }
        console.print(Panel(
            content,
            title=f"[bold cyan]{titles.get(briefing_type, '📋 Briefing')}[/]",
            border_style="cyan",
            padding=(1, 2),
            width=min(100, console.width - 4),
        ))
        write_memory({"type": "briefing", "briefing_type": briefing_type,
                      "content": content[:200]})
        return f"Briefing delivered: {briefing_type}"

    # ── save_profile ──────────────────────────────────────────────────────────
    elif name == "save_profile":
        profile = load_profile()
        for k, v in inp.items():
            profile[k] = v
        profile["onboarded"] = True
        save_profile(profile)
        return f"Profile saved."

    # ── get_profile ───────────────────────────────────────────────────────────
    elif name == "get_profile":
        profile   = load_profile()
        habits    = load_habits()
        goals     = load_goals()
        return json.dumps({
            "profile": profile,
            "habits":  habits,
            "goals":   goals,
            "memory_entries": memory_count(),
        }, indent=2, ensure_ascii=False)

    # ── log_dream ──────────────────────────────────────────────────────────────
    elif name == "log_dream":
        entry = {
            "date":      time.strftime("%Y-%m-%d"),
            "content":   inp.get("content", ""),
            "emotions":  inp.get("emotions", []),
            "symbols":   inp.get("symbols", []),
            "tone":      inp.get("tone", "neutral"),
            "vividness": inp.get("vividness", 5),
        }
        write_memory({"type": "dream", **entry})
        # Check for recurring symbols
        recent = get_recent_memory(days=30)
        dream_entries = [r for r in recent if r.get("type") == "dream"]
        all_symbols = []
        for d in dream_entries:
            all_symbols.extend(d.get("symbols", []))
        recurring = []
        for s in set(all_symbols):
            if all_symbols.count(s) >= 2:
                recurring.append(f"{s} ({all_symbols.count(s)}x)")
        result = f"Dream logged. Vividness: {entry['vividness']}/10, Tone: {entry['tone']}"
        if recurring:
            result += f"\nRecurring symbols this month: {', '.join(recurring)}"
        return result

        return f"Unknown tool: {name}"

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

TOOLS = [
    {"type": "function", "function": {"name": "remember",
        "description": "Store to long-term memory. Types: mood, energy, win, struggle, note.",
        "parameters": {"type": "object", "properties": {
            "type":        {"type": "string"},
            "content":     {"type": "string"},
            "score":       {"type": "number"},
            "level":       {"type": "string"},
            "description": {"type": "string"},
            "resolved":    {"type": "boolean"},
        }, "required": ["type", "content"]}}},

    {"type": "function", "function": {"name": "recall",
        "description": "Search long-term memory.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
        }, "required": ["query"]}}},

    {"type": "function", "function": {"name": "correct_entry",
        "description": "Fix a mistake in a previously logged memory entry (e.g. wrong "
                       "sleep hours, wrong mood score). Always call recall first to find "
                       "the entry's id - never guess an id.",
        "parameters": {"type": "object", "properties": {
            "entry_id": {"type": "string", "description": "The id shown by recall, e.g. 'a1b2c3d4'."},
            "updates":  {"type": "object", "description": "Fields to change, e.g. {\"score\": 7} or {\"hours\": 6.5}."},
        }, "required": ["entry_id", "updates"]}}},

    {"type": "function", "function": {"name": "delete_entry",
        "description": "Permanently delete a previously logged memory entry. Always call "
                       "recall first to find the entry's id, and confirm with the user "
                       "before deleting - this can't be undone.",
        "parameters": {"type": "object", "properties": {
            "entry_id": {"type": "string", "description": "The id shown by recall, e.g. 'a1b2c3d4'."},
        }, "required": ["entry_id"]}}},

    {"type": "function", "function": {"name": "log_meal",
        "description": "Log a meal with nutritional info.",
        "parameters": {"type": "object", "properties": {
            "meal_time":  {"type": "string", "description": "breakfast/lunch/dinner/snack"},
            "food":       {"type": "string"},
            "calories":   {"type": "integer"},
            "protein_g":  {"type": "number"},
            "carbs_g":    {"type": "number"},
            "fat_g":      {"type": "number"},
            "notes":      {"type": "string"},
        }, "required": ["meal_time", "food"]}}},

    {"type": "function", "function": {"name": "log_sleep",
        "description": "Log sleep duration and quality.",
        "parameters": {"type": "object", "properties": {
            "bedtime":   {"type": "string"},
            "wake_time": {"type": "string"},
            "hours":     {"type": "number"},
            "quality":   {"type": "integer", "description": "1-10"},
            "notes":     {"type": "string"},
        }, "required": ["hours", "quality"]}}},

    {"type": "function", "function": {"name": "log_hydration",
        "description": "Log water intake.",
        "parameters": {"type": "object", "properties": {
            "glasses": {"type": "integer", "description": "Number of glasses (250ml each)"},
        }, "required": ["glasses"]}}},

    {"type": "function", "function": {"name": "log_workout",
        "description": "Log a workout session.",
        "parameters": {"type": "object", "properties": {
            "workout_type":    {"type": "string", "description": "running/gym/yoga/cycling/etc"},
            "duration_min":    {"type": "integer"},
            "intensity":       {"type": "string", "description": "low/medium/high"},
            "calories_burned": {"type": "integer"},
            "notes":           {"type": "string"},
        }, "required": ["workout_type", "duration_min"]}}},

    {"type": "function", "function": {"name": "log_stress",
        "description": "Log stress level and trigger.",
        "parameters": {"type": "object", "properties": {
            "score":   {"type": "integer", "description": "1-10"},
            "trigger": {"type": "string"},
            "notes":   {"type": "string"},
        }, "required": ["score"]}}},

    {"type": "function", "function": {"name": "log_meditation",
        "description": "Log a meditation or mindfulness session.",
        "parameters": {"type": "object", "properties": {
            "duration_min": {"type": "integer"},
            "notes":        {"type": "string"},
        }, "required": ["duration_min"]}}},

    {"type": "function", "function": {"name": "log_gratitude",
        "description": "Log daily gratitude items.",
        "parameters": {"type": "object", "properties": {
            "items": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "string"},
        }, "required": ["items"]}}},

    {"type": "function", "function": {"name": "log_focus_session",
        "description": "Log a deep work / focus session.",
        "parameters": {"type": "object", "properties": {
            "duration_min":  {"type": "integer"},
            "task":          {"type": "string"},
            "completed":     {"type": "boolean"},
            "distractions":  {"type": "integer", "description": "Number of interruptions"},
            "quality":       {"type": "integer", "description": "1-10"},
        }, "required": ["duration_min", "task"]}}},

    {"type": "function", "function": {"name": "update_habit",
        "description": "Update habit streak.",
        "parameters": {"type": "object", "properties": {
            "habit_name": {"type": "string"},
            "completed":  {"type": "boolean"},
        }, "required": ["habit_name", "completed"]}}},

    {"type": "function", "function": {"name": "update_goal",
        "description": "Create or update a goal. For goals that should track themselves "
                       "automatically from logged data (e.g. 'sleep 7+ hours', 'keep stress "
                       "under 4'), set metric/target/direction instead of a manual progress "
                       "number - progress will be computed from real logged averages.",
        "parameters": {"type": "object", "properties": {
            "goal_name":   {"type": "string"},
            "progress":    {"type": "number", "description": "Manual progress 0-100. Ignored if metric is set."},
            "note":        {"type": "string"},
            "metric":      {"type": "string", "enum": ["mood", "energy", "stress", "sleep", "hydration"],
                            "description": "Set this to make the goal auto-track from logged data."},
            "target":      {"type": "number", "description": "Target value for the metric, e.g. 7 for '7 hours of sleep'."},
            "direction":   {"type": "string", "enum": ["at_least", "at_most"],
                            "description": "'at_least' for goals like sleep/mood/hydration, 'at_most' for goals like stress."},
            "window_days": {"type": "integer", "description": "How many recent days to average. Default 7."},
        }, "required": ["goal_name"]}}},

    {"type": "function", "function": {"name": "check_goal_progress",
        "description": "Show current progress on every goal, refreshing auto-tracked goals from the latest logged data.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},

    {"type": "function", "function": {"name": "compare_periods",
        "description": "Compare average mood/energy/stress/sleep/hydration between the last "
                       "N days and the N days before that (e.g. this week vs last week).",
        "parameters": {"type": "object", "properties": {
            "window_days": {"type": "integer", "description": "Size of each period in days. Default 7 (week vs week)."},
        }, "required": []}}},

    {"type": "function", "function": {"name": "compare_before_after",
        "description": "Compare average mood/energy/stress/sleep/hydration before vs. after "
                       "a specific date - use this when the user asks whether something "
                       "(a new habit, a life change) actually made a difference, and they "
                       "give or imply a start date.",
        "parameters": {"type": "object", "properties": {
            "date": {"type": "string", "description": "The changepoint date, YYYY-MM-DD. Counted as part of the 'after' period."},
        }, "required": ["date"]}}},

    {"type": "function", "function": {"name": "check_anomalies",
        "description": "Find unusually high or low days (statistical outliers) in recent "
                       "mood/energy/stress/sleep/hydration data - e.g. 'today's stress was "
                       "way above your normal range'.",
        "parameters": {"type": "object", "properties": {
            "window_days": {"type": "integer", "description": "How many recent days to scan. Default 30."},
        }, "required": []}}},

    {"type": "function", "function": {"name": "get_period_summary",
        "description": "Summarize a specific past calendar period (e.g. 'how was I in "
                       "March?', 'summarize last month') - resolve the user's phrase to "
                       "concrete YYYY-MM-DD start/end dates yourself, then call this. "
                       "Returns average metrics for the period plus notable entries "
                       "(gratitude, dreams, notes).",
        "parameters": {"type": "object", "properties": {
            "start_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
            "end_date":   {"type": "string", "description": "YYYY-MM-DD, inclusive."},
        }, "required": ["start_date", "end_date"]}}},

    {"type": "function", "function": {"name": "detect_patterns",
        "description": "Analyze all memory for trends across mood, energy, sleep, nutrition, stress, habits.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},

    {"type": "function", "function": {"name": "get_health_dashboard",
        "description": "Get a full health dashboard for today.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},

    {"type": "function", "function": {"name": "get_weekly_health_report",
        "description": "Get a comprehensive weekly health report.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},

    {"type": "function", "function": {"name": "send_briefing",
        "description": "Deliver a formatted briefing to the user.",
        "parameters": {"type": "object", "properties": {
            "content": {"type": "string"},
            "type":    {"type": "string"},
        }, "required": ["content", "type"]}}},

    {"type": "function", "function": {"name": "save_profile",
        "description": "Save user profile.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}, "timezone": {"type": "string"},
        }, "required": []}}},

    {"type": "function", "function": {"name": "get_profile",
        "description": "Load full profile, habits, goals, memory stats.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},

    {"type": "function", "function": {
        "name": "log_dream",
        "description": "Log a dream from this morning. Include content, emotions, symbols, tone and vividness.",
        "parameters": {"type": "object", "properties": {
            "content":   {"type": "string", "description": "What happened in the dream"},
            "emotions":  {"type": "array",  "items": {"type": "string"}, "description": "Emotions felt: anxiety, joy, fear, peace, etc."},
            "symbols":   {"type": "array",  "items": {"type": "string"}, "description": "Key symbols: flying, water, exam, chasing, etc."},
            "tone":      {"type": "string", "description": "Overall tone: positive/negative/neutral/mixed"},
            "vividness": {"type": "integer","description": "How vivid was it 1-10"},
        }, "required": ["content"]}}},
]
