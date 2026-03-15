#!/usr/bin/env python3
"""
Hermes Life OS — Full Featured Demo
=====================================
A personal operating system that learns who you are,
tracks your health, habits, goals, and mental state,
detects patterns across every dimension of your life,
and grows smarter every single day.

Requirements:  pip install openai rich
Setup:         set OPENROUTER_API_KEY=sk-or-...

Modes:
    onboard    - First time setup
    morning    - Daily morning briefing
    checkin    - Midday check-in
    evening    - Evening reflection
    weekly     - Weekly review
    nutrition  - Log meals and get nutrition insights
    sleep      - Log sleep and get sleep analysis
    hydration  - Track daily water intake
    fitness    - Log workouts and track fitness
    mental     - Log stress, meditation, gratitude
    focus      - Log deep work sessions and productivity
    health     - Full health dashboard
    chat       - Interactive conversation with Hermes
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text
    from rich import box
except ImportError:
    print("pip install rich")
    sys.exit(1)

try:
    from openai import OpenAI
except ImportError:
    print("pip install openai")
    sys.exit(1)

import shutil
console = Console(width=min(110, shutil.get_terminal_size().columns))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HERMES_DIR   = Path.home() / ".hermes" / "life-os"
MEMORY_FILE  = HERMES_DIR / "memory.jsonl"
PROFILE_FILE = HERMES_DIR / "profile.json"
HABITS_FILE  = HERMES_DIR / "habits.json"
GOALS_FILE   = HERMES_DIR / "goals.json"
NUTRITION_FILE = HERMES_DIR / "nutrition.json"
SLEEP_FILE   = HERMES_DIR / "sleep.json"
HYDRATION_FILE = HERMES_DIR / "hydration.json"
FITNESS_FILE = HERMES_DIR / "fitness.json"
FOCUS_FILE   = HERMES_DIR / "focus.json"
MENTAL_FILE  = HERMES_DIR / "mental.json"

HERMES_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _load(path: Path, default=None):
    if default is None:
        default = {}
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default

def _save(path: Path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def load_profile() -> Dict:    return _load(PROFILE_FILE, {"name": "friend", "onboarded": False})
def save_profile(p):           _save(PROFILE_FILE, p)
def load_habits() -> List:     return _load(HABITS_FILE, [])
def save_habits(h):            _save(HABITS_FILE, h)
def load_goals() -> List:      return _load(GOALS_FILE, [])
def save_goals(g):             _save(GOALS_FILE, g)
def load_nutrition() -> List:  return _load(NUTRITION_FILE, [])
def save_nutrition(n):         _save(NUTRITION_FILE, n)
def load_sleep() -> List:      return _load(SLEEP_FILE, [])
def save_sleep(s):             _save(SLEEP_FILE, s)
def load_hydration() -> Dict:  return _load(HYDRATION_FILE, {"today": 0, "goal": 8, "log": []})
def save_hydration(h):         _save(HYDRATION_FILE, h)
def load_fitness() -> List:    return _load(FITNESS_FILE, [])
def save_fitness(f):           _save(FITNESS_FILE, f)
def load_focus() -> List:      return _load(FOCUS_FILE, [])
def save_focus(f):             _save(FOCUS_FILE, f)
def load_mental() -> List:     return _load(MENTAL_FILE, [])
def save_mental(m):            _save(MENTAL_FILE, m)

def write_memory(entry: Dict):
    entry["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def search_memory(query: str, limit: int = 10) -> List[Dict]:
    if not MEMORY_FILE.exists():
        return []
    q = query.lower()
    results = []
    with open(MEMORY_FILE, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                if q in json.dumps(entry, ensure_ascii=False).lower():
                    results.append(entry)
            except Exception:
                pass
    return results[-limit:]

def get_recent_memory(days: int = 7) -> List[Dict]:
    if not MEMORY_FILE.exists():
        return []
    cutoff = datetime.utcnow() - timedelta(days=days)
    results = []
    with open(MEMORY_FILE, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                ts = entry.get("timestamp", "")
                if ts:
                    try:
                        if datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ") >= cutoff:
                            results.append(entry)
                    except Exception:
                        results.append(entry)
            except Exception:
                pass
    return results

def memory_count() -> int:
    if not MEMORY_FILE.exists():
        return 0
    try:
        return sum(1 for _ in open(MEMORY_FILE, encoding="utf-8"))
    except Exception:
        return 0

# ---------------------------------------------------------------------------
# Pattern detection
# ---------------------------------------------------------------------------

def detect_patterns() -> Dict[str, Any]:
    recent = get_recent_memory(days=14)
    patterns: Dict[str, Any] = {
        "mood_trend": None, "energy_trend": None,
        "sleep_trend": None, "hydration_trend": None,
        "nutrition_trend": None, "stress_trend": None,
        "habit_streaks": {}, "wins": [], "struggles": [],
        "correlations": [], "insights": [],
    }

    mood_scores, energy_levels, stress_scores = [], [], []
    sleep_hours, water_glasses = [], []

    for entry in recent:
        t = entry.get("type", "")
        if t == "mood":
            mood_scores.append(entry.get("score", 0))
        elif t == "energy":
            energy_levels.append(entry.get("level", "medium"))
        elif t == "stress":
            stress_scores.append(entry.get("score", 0))
        elif t == "sleep":
            sleep_hours.append(entry.get("hours", 0))
        elif t == "hydration":
            water_glasses.append(entry.get("glasses", 0))
        elif t == "win":
            patterns["wins"].append(entry.get("description", ""))
        elif t == "struggle":
            if not entry.get("resolved"):
                patterns["struggles"].append(entry.get("description", ""))

    # Mood trend
    if mood_scores:
        avg = sum(mood_scores) / len(mood_scores)
        patterns["mood_trend"] = (
            f"strong (avg {avg:.1f}/10)" if avg >= 7 else
            f"steady (avg {avg:.1f}/10)" if avg >= 5 else
            f"challenging (avg {avg:.1f}/10)"
        )
        if len(mood_scores) >= 3 and all(s < 6 for s in mood_scores[-3:]):
            patterns["insights"].append(
                "Three consecutive tough days detected. This pattern is worth addressing."
            )

    # Energy trend
    if energy_levels:
        low = energy_levels.count("low")
        high = energy_levels.count("high")
        patterns["energy_trend"] = (
            "mostly high" if high > low else
            "running low lately" if low > high else "mixed"
        )

    # Sleep trend
    if sleep_hours:
        avg_sleep = sum(sleep_hours) / len(sleep_hours)
        patterns["sleep_trend"] = (
            f"well-rested (avg {avg_sleep:.1f}h)" if avg_sleep >= 7.5 else
            f"slightly short (avg {avg_sleep:.1f}h)" if avg_sleep >= 6 else
            f"sleep-deprived (avg {avg_sleep:.1f}h)"
        )
        if avg_sleep < 6.5:
            patterns["insights"].append(
                f"Averaging only {avg_sleep:.1f}h sleep. This is likely affecting your mood and focus."
            )

    # Hydration trend
    if water_glasses:
        avg_water = sum(water_glasses) / len(water_glasses)
        patterns["hydration_trend"] = (
            f"well hydrated (avg {avg_water:.1f} glasses)" if avg_water >= 8 else
            f"slightly low (avg {avg_water:.1f} glasses)" if avg_water >= 5 else
            f"dehydrated (avg {avg_water:.1f} glasses)"
        )

    # Stress trend
    if stress_scores:
        avg_stress = sum(stress_scores) / len(stress_scores)
        patterns["stress_trend"] = (
            f"low stress (avg {avg_stress:.1f}/10)" if avg_stress < 4 else
            f"moderate stress (avg {avg_stress:.1f}/10)" if avg_stress < 7 else
            f"high stress (avg {avg_stress:.1f}/10)"
        )
        if avg_stress >= 7:
            patterns["insights"].append(
                f"Stress levels averaging {avg_stress:.1f}/10. Consider reviewing workload and recovery habits."
            )

    # Correlations
    if mood_scores and sleep_hours and len(mood_scores) >= 3 and len(sleep_hours) >= 3:
        patterns["correlations"].append(
            "Sleep and mood data available — correlation analysis active."
        )

    # Habit streaks
    for habit in load_habits():
        name = habit.get("name", "")
        streak = habit.get("streak", 0)
        if streak >= 7:
            patterns["insights"].append(
                f"'{name}' is at {streak} days — this is becoming a real part of your identity."
            )
        elif streak == 0 and habit.get("last_done"):
            patterns["insights"].append(
                f"'{name}' streak is at zero. Easy to restart — just one day."
            )

    return patterns

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def dispatch_tool(name: str, inp: Dict[str, Any]) -> str:

    # ── remember ──────────────────────────────────────────────────────────────
    if name == "remember":
        entry = {k: v for k, v in inp.items()}
        write_memory(entry)
        return f"Remembered: [{inp.get('type','note')}] {str(inp.get('content', inp.get('description','')))[:80]}"

    # ── recall ────────────────────────────────────────────────────────────────
    elif name == "recall":
        results = search_memory(inp.get("query", ""), limit=8)
        if not results:
            return f"Nothing found for '{inp.get('query','')}'."
        return "\n".join(
            f"[{r.get('type','?')}] {str(r.get('content', r.get('description','')))[:100]}"
            for r in results[-5:]
        )

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
        return (f"Stress logged: {inp.get('score',5)}/10 — trigger: {inp.get('trigger','')}\n"
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
        goals     = load_goals()
        found     = False
        for g in goals:
            if g["name"].lower() == goal_name.lower():
                if progress is not None:
                    g["progress"]     = progress
                g["last_updated"] = time.strftime("%Y-%m-%d")
                if note:
                    g["last_note"] = note
                found = True
                break
        if not found:
            goals.append({"name": goal_name, "progress": progress or 0,
                          "created": time.strftime("%Y-%m-%d"),
                          "last_updated": time.strftime("%Y-%m-%d"), "last_note": note})
        save_goals(goals)
        return f"Goal '{goal_name}': {progress}% — {note}"

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
        "description": "Update goal progress.",
        "parameters": {"type": "object", "properties": {
            "goal_name": {"type": "string"},
            "progress":  {"type": "number"},
            "note":      {"type": "string"},
        }, "required": ["goal_name"]}}},

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
]

# ---------------------------------------------------------------------------
# Demo scenarios
# ---------------------------------------------------------------------------

today    = datetime.now()
day_name = today.strftime("%A")
date_str = today.strftime("%B %d, %Y")

DEMO_SCENARIOS = {
    "onboard": {
        "title": "First Time Setup - Getting to Know You",
        "prompt": textwrap.dedent(f"""
            Hi! I just started using Hermes Life OS. Today is {date_str}.
            My name is Alex.

            Here is what is going on in my life:
            - Trying to run 3x per week
            - Main goal: ship a side project by June
            - Work best in mornings, lose focus in afternoons
            - Mood lately: 7/10
            - Worried about starting things and not finishing them
            - Usually sleep around 7 hours, quality varies
            - Try to drink 8 glasses of water but often forget
            - Have been stressed about work deadlines lately

            Save everything I told you. Ask one follow-up question, then welcome me.
        """).strip(),
    },
    "morning": {
        "title": f"Morning Briefing — {date_str}",
        "prompt": textwrap.dedent(f"""
            Good morning. Today is {date_str}, {day_name}.
            Check my profile, recall recent memory, detect all patterns,
            check my health dashboard, then deliver my morning briefing.
            Make it personal. Under 200 words. End with ONE focus for today.
        """).strip(),
    },
    "checkin": {
        "title": "Midday Check-in",
        "prompt": textwrap.dedent(f"""
            Midday check-in.
            - Ran 30 minutes this morning
            - Had breakfast: oatmeal and coffee (~400 cal)
            - Drank 3 glasses of water so far
            - Did a 45-min focus session on my project
            - Mood: 7/10, energy: good
            - Feeling slightly stressed about an afternoon meeting

            Log everything. Detect patterns. Give me a short midday nudge.
        """).strip(),
    },
    "evening": {
        "title": "Evening Reflection",
        "prompt": textwrap.dedent(f"""
            Evening. Let's reflect.
            - Finished a big feature for my project
            - Skipped afternoon deep work, got distracted by email
            - Energy high in morning, crashed at 3pm
            - Had lunch: salad and chicken (~600 cal)
            - Dinner: pasta (~700 cal)
            - Drank 6 glasses of water total
            - Meditated for 10 minutes before dinner
            - Mood: 7/10, satisfied but tired
            - Stress: 5/10 from the afternoon meeting

            Log all of it. Detect patterns. Tell me what today means in the bigger picture.
        """).strip(),
    },
    "weekly": {
        "title": "Weekly Review",
        "prompt": textwrap.dedent(f"""
            Sunday evening. Weekly review.
            - Ran 2 out of 3 planned days
            - Side project 30% closer to done
            - Bad day Wednesday, everything felt off
            - Won a work negotiation Friday
            - Sleep was inconsistent (avg ~6.5h)
            - Stress peaked midweek
            - Meditated 3 times
            - Water intake was low on busy days

            Get the weekly health report. Log everything.
            Give me a proper weekly review: patterns, wins, struggles, ONE thing to change.
        """).strip(),
    },
    "nutrition": {
        "title": "Nutrition Check-in",
        "prompt": textwrap.dedent(f"""
            Let's review my nutrition today.
            - Breakfast: Greek yogurt with berries (~300 cal, 20g protein)
            - Lunch: Grilled chicken salad (~500 cal, 35g protein)
            - Snack: Apple and almonds (~200 cal)
            - Dinner: Salmon with vegetables (~550 cal, 40g protein)
            - Water: 7 glasses

            Log all meals and water. Detect nutrition patterns.
            Give me a nutrition briefing with insights and one actionable suggestion.
        """).strip(),
    },
    "sleep": {
        "title": "Sleep Analysis",
        "prompt": textwrap.dedent(f"""
            Log last night's sleep and analyze.
            - Went to bed at 11:30pm
            - Woke up at 7:00am (7.5 hours)
            - Sleep quality: 8/10 — felt well rested
            - No interruptions

            Log it. Pull recent sleep data. Detect sleep patterns.
            Give me a sleep analysis briefing with insights.
        """).strip(),
    },
    "fitness": {
        "title": "Fitness Summary",
        "prompt": textwrap.dedent(f"""
            Log today's workout and give me a fitness summary.
            - Morning run: 5km in 28 minutes, high intensity
            - Calories burned: approximately 350
            - Felt strong, best run in a week

            Log the workout. Update my running habit streak.
            Get the weekly health report for fitness data.
            Deliver a fitness briefing with pattern insights.
        """).strip(),
    },
    "mental": {
        "title": "Mental Wellness Check",
        "prompt": textwrap.dedent(f"""
            Mental wellness check-in.
            - Stress today: 4/10 — much better than yesterday
            - Did 15 minutes of meditation this morning
            - Grateful for: good sleep, productive morning, supportive team
            - Mood: 8/10

            Log stress, meditation, and gratitude.
            Detect mental wellness patterns.
            Give me a mental wellness briefing.
        """).strip(),
    },
    "focus": {
        "title": "Focus & Productivity Report",
        "prompt": textwrap.dedent(f"""
            Log my focus sessions and give me a productivity report.
            - Morning session: 90 minutes on project feature, completed, 1 distraction, quality 8/10
            - Afternoon session: 45 minutes on code review, completed, 3 distractions, quality 6/10
            - Evening session: 30 minutes on planning, completed, 0 distractions, quality 9/10

            Log all sessions. Detect focus patterns. Give me a productivity briefing
            with insights on my best focus times and distraction patterns.
        """).strip(),
    },
    "health": {
        "title": "Full Health Dashboard",
        "prompt": textwrap.dedent(f"""
            Give me a complete health dashboard for today and this week.
            Get the health dashboard and weekly health report.
            Detect all patterns across nutrition, sleep, fitness, mental health, and focus.
            Deliver a comprehensive health briefing - what the data says about me right now.
        """).strip(),
    },
    "chat": {
        "title": "Interactive Chat",
        "prompt": "__CHAT_MODE__",
    },
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM = textwrap.dedent("""
    You are Hermes Life OS - a personal operating system that grows with the person using it.
    You track every dimension of their life: mood, energy, sleep, nutrition, hydration,
    fitness, stress, meditation, gratitude, focus, habits, and goals.

    Core behaviors:
    - ALWAYS call get_profile and recall at the start of every interaction
    - ALWAYS call detect_patterns before delivering any briefing
    - ALWAYS call send_briefing to deliver the final response
    - Store everything meaningful the person shares using the appropriate log tool
    - Be warm, direct, and personal. Reference specific things from memory.
    - Show correlations: connect sleep to mood, nutrition to energy, stress to focus.

    Available tracking tools:
    - log_meal, log_sleep, log_hydration, log_workout
    - log_stress, log_meditation, log_gratitude, log_focus_session
    - update_habit, update_goal
    - get_health_dashboard, get_weekly_health_report
    - detect_patterns, remember, recall

    Tone: trusted friend who pays close attention and connects the dots.
    Not a coach. Not a doctor. Just someone who genuinely notices things.
""").strip()

# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "openrouter/auto"


def run_life_os(scenario: Dict[str, Any], api_key: str,
                model: str = DEFAULT_MODEL, max_turns: int = 25,
                user_message: str = "") -> Dict[str, Any]:

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://github.com/Lethe044/hermes-life-os",
            "X-Title": "Hermes Life OS",
        },
    )

    prompt = user_message if user_message else scenario["prompt"]

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user",   "content": prompt},
    ]

    turn = 0
    calls: List[str] = []
    start = time.time()
    briefings_sent = 0
    memories_stored = 0

    console.print(Rule(f"[bold cyan]{scenario['title']}[/]"))
    if not user_message:
        console.print(Panel(prompt, title="[yellow]You[/]", border_style="yellow"))
    console.print(f"[dim]Model: {model}[/]\n")

    while turn < max_turns:
        turn += 1

        with Progress(SpinnerColumn("dots"),
                      TextColumn(f"[cyan]Hermes thinking... (turn {turn}/{max_turns})[/]"),
                      transient=True, console=console) as p:
            p.add_task("")
            resp = client.chat.completions.create(
                model=model, messages=messages,
                tools=TOOLS, tool_choice="auto", max_tokens=1500,
            )

        msg = resp.choices[0].message

        if msg.content and msg.content.strip():
            console.print(Panel(
                Markdown(msg.content),
                title="[green]Hermes[/]",
                border_style="green",
                width=min(100, console.width - 4),
            ))

        if not msg.tool_calls or resp.choices[0].finish_reason == "stop":
            if briefings_sent == 0 and turn < max_turns - 1:
                messages.append({"role": "user", "content":
                    "Please deliver your response using send_briefing now."})
                continue
            break

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })

        for tc in msg.tool_calls:
            tname = tc.function.name
            try:
                tinp = json.loads(tc.function.arguments)
            except Exception:
                tinp = {}
            calls.append(tname)

            icons = {
                "remember": "🧠", "recall": "🔍", "log_meal": "🥗",
                "log_sleep": "😴", "log_hydration": "💧", "log_workout": "💪",
                "log_stress": "😤", "log_meditation": "🧘", "log_gratitude": "🙏",
                "log_focus_session": "🎯", "update_habit": "✅", "update_goal": "🎯",
                "detect_patterns": "📊", "get_health_dashboard": "❤️",
                "get_weekly_health_report": "📋", "send_briefing": "📋",
                "save_profile": "👤", "get_profile": "👤",
            }
            preview = str(tinp.get("food", tinp.get("content", tinp.get("query",
                          tinp.get("task", tinp.get("habit_name", tinp.get("goal_name", "")))))))[:60]
            console.print(f"  {icons.get(tname,'🔧')} [yellow]{tname}[/] [dim]{preview}[/]")

            result = dispatch_tool(tname, tinp)

            if tname in ("remember", "log_meal", "log_sleep", "log_hydration",
                         "log_workout", "log_stress", "log_meditation",
                         "log_gratitude", "log_focus_session"):
                memories_stored += 1

            if tname == "send_briefing":
                briefings_sent += 1
            elif tname not in ("get_profile", "get_health_dashboard", "get_weekly_health_report"):
                if len(result) < 400:
                    console.print(f"  [dim]{result}[/]")

            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    elapsed = time.time() - start

    console.print(Rule("[bold green]Session Summary[/]"))
    t = Table(header_style="bold cyan", box=box.ROUNDED)
    t.add_column("Metric", style="dim")
    t.add_column("Value")
    for row in [
        ("Mode",            scenario["title"]),
        ("Model",           model),
        ("Turns",           str(turn)),
        ("Tool calls",      str(len(calls))),
        ("Items logged",    str(memories_stored)),
        ("Total in memory", str(memory_count())),
        ("Briefings sent",  str(briefings_sent)),
        ("Elapsed",         f"{elapsed:.1f}s"),
        ("Tools used",      ", ".join(sorted(set(calls)))),
    ]:
        t.add_row(*row)
    console.print(t)
    return {"turns": turn, "calls": len(calls), "elapsed": elapsed,
            "memories": memories_stored, "briefings": briefings_sent}


# ---------------------------------------------------------------------------
# Chat mode
# ---------------------------------------------------------------------------

def run_chat_mode(api_key: str, model: str = DEFAULT_MODEL):
    """Interactive chat - you type, Hermes responds using your full memory."""
    console.print(Panel(
        "[bold cyan]Hermes Life OS — Chat Mode[/]\n"
        "[dim]Type anything. Hermes will respond using everything it knows about you.\n"
        "Type 'exit' or 'quit' to leave.[/]",
        border_style="cyan",
    ))

    seed_demo_memory()

    while True:
        try:
            user_input = input("\n[You]: ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/]")
            break

        if user_input.lower() in ("exit", "quit", "bye", "q"):
            console.print("[dim]See you tomorrow. 🌙[/]")
            break

        if not user_input:
            continue

        scenario = {
            "title": "Chat",
            "prompt": user_input,
        }
        run_life_os(scenario, api_key, model, max_turns=15, user_message=user_input)


# ---------------------------------------------------------------------------
# Seed demo memory
# ---------------------------------------------------------------------------

def seed_demo_memory():
    if MEMORY_FILE.exists() and MEMORY_FILE.stat().st_size > 200:
        return

    console.print("[dim]Seeding demo memory...[/]")

    entries = [
        {"type": "mood",     "content": "productive day",              "score": 8},
        {"type": "energy",   "content": "morning",                     "level": "high"},
        {"type": "mood",     "content": "tired afternoon",             "score": 5},
        {"type": "energy",   "content": "afternoon crash",             "level": "low"},
        {"type": "win",      "content": "shipped a feature",           "description": "shipped a feature"},
        {"type": "mood",     "content": "good run morning",            "score": 7},
        {"type": "energy",   "content": "morning run helped",          "level": "high"},
        {"type": "struggle", "content": "losing focus after 3pm",      "description": "losing focus after 3pm", "resolved": False},
        {"type": "mood",     "content": "anxious about deadline",      "score": 5},
        {"type": "win",      "content": "great 1:1 with manager",      "description": "great 1:1 with manager"},
        {"type": "mood",     "content": "everything clicked today",    "score": 9},
        {"type": "sleep",    "content": "6.5h sleep",                  "hours": 6.5, "quality": 6},
        {"type": "sleep",    "content": "7h sleep",                    "hours": 7.0, "quality": 7},
        {"type": "sleep",    "content": "5.5h sleep bad night",        "hours": 5.5, "quality": 4},
        {"type": "meal",     "content": "oatmeal breakfast",           "calories": 350, "meal_time": "breakfast"},
        {"type": "meal",     "content": "chicken salad lunch",         "calories": 550, "meal_time": "lunch"},
        {"type": "workout",  "content": "running 5km",                 "workout_type": "running", "duration": 30},
        {"type": "hydration","content": "6 glasses water",             "glasses": 6},
        {"type": "stress",   "content": "deadline pressure",           "score": 7},
        {"type": "stress",   "content": "lighter day",                 "score": 4},
        {"type": "meditation","content": "10min meditation",           "duration": 10},
        {"type": "focus",    "content": "90min deep work session",     "duration": 90, "quality": 8},
    ]
    for e in entries:
        write_memory(e)

    save_habits([
        {"name": "morning run",       "streak": 3,  "best_streak": 7,  "last_done": time.strftime("%Y-%m-%d"), "created": "2026-01-01"},
        {"name": "deep work block",   "streak": 5,  "best_streak": 12, "last_done": time.strftime("%Y-%m-%d"), "created": "2026-01-01"},
        {"name": "no phone before 9", "streak": 0,  "best_streak": 4,  "last_done": None, "created": "2026-01-15"},
        {"name": "drink 8 glasses",   "streak": 2,  "best_streak": 5,  "last_done": time.strftime("%Y-%m-%d"), "created": "2026-02-01"},
        {"name": "meditate",          "streak": 4,  "best_streak": 4,  "last_done": time.strftime("%Y-%m-%d"), "created": "2026-02-15"},
    ])

    save_goals([
        {"name": "ship side project", "progress": 45, "created": "2026-01-01",
         "last_updated": time.strftime("%Y-%m-%d"), "last_note": "good progress this week"},
        {"name": "read 12 books",     "progress": 25, "created": "2026-01-01",
         "last_updated": time.strftime("%Y-%m-%d"), "last_note": "finished book 3"},
        {"name": "run 5km under 25min","progress": 60, "created": "2026-02-01",
         "last_updated": time.strftime("%Y-%m-%d"), "last_note": "pb: 27:30"},
    ])

    save_profile({
        "name": "Alex", "onboarded": True, "timezone": "UTC",
        "peak_hours": "morning", "main_goal": "ship side project by June",
        "sleep_goal_hours": 7.5, "water_goal_glasses": 8,
        "weekly_workout_goal": 3,
    })

    # Seed some nutrition, sleep, fitness data
    today = time.strftime("%Y-%m-%d")
    save_nutrition([
        {"date": today, "time": "breakfast", "food": "oatmeal", "calories": 350, "protein": 12},
        {"date": today, "time": "lunch",     "food": "chicken salad", "calories": 550, "protein": 40},
    ])
    save_sleep([
        {"date": today, "bedtime": "23:30", "wake_time": "07:00", "hours": 7.5, "quality": 8},
    ])
    hydration = load_hydration()
    hydration["today"]     = 5
    hydration["last_date"] = today
    hydration["goal"]      = 8
    save_hydration(hydration)

    console.print("[dim]Demo memory ready.[/]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Hermes Life OS")
    parser.add_argument("--mode", choices=list(DEMO_SCENARIOS.keys()), default="morning")
    parser.add_argument("--model",     default=DEFAULT_MODEL)
    parser.add_argument("--max-turns", type=int, default=25)
    parser.add_argument("--fresh",     action="store_true", help="Clear all data and start fresh")
    args = parser.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        console.print("[red]Set OPENROUTER_API_KEY first.[/]")
        console.print("  Windows: set OPENROUTER_API_KEY=sk-or-...")
        sys.exit(1)

    if args.fresh:
        for f in [MEMORY_FILE, PROFILE_FILE, HABITS_FILE, GOALS_FILE,
                  NUTRITION_FILE, SLEEP_FILE, HYDRATION_FILE,
                  FITNESS_FILE, FOCUS_FILE, MENTAL_FILE]:
            if f.exists():
                f.unlink()
        console.print("[dim]All data cleared.[/]")

    console.print(Panel(
        "[bold cyan]Hermes Life OS[/]\n"
        "[dim]The personal OS that grows with you[/]",
        border_style="cyan",
    ))

    if args.mode == "chat":
        run_chat_mode(key, args.model)
        return

    if args.mode != "onboard":
        seed_demo_memory()

    scenario = DEMO_SCENARIOS[args.mode]
    run_life_os(scenario, key, args.model, args.max_turns)
    console.print("\n[bold green]Session complete.[/]")
    console.print(f"[dim]Memory: {MEMORY_FILE}[/]")


if __name__ == "__main__":
    main()
