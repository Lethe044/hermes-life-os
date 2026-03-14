#!/usr/bin/env python3
"""
Hermes Life OS — Demo
=====================
A personal operating system that learns who you are,
remembers everything, detects patterns, and grows smarter every day.

Requirements:  pip install openai rich
Setup:         set OPENROUTER_API_KEY=sk-or-...

Usage:
    python demo/demo_life_os.py --mode morning
    python demo/demo_life_os.py --mode checkin
    python demo/demo_life_os.py --mode evening
    python demo/demo_life_os.py --mode weekly
    python demo/demo_life_os.py --mode onboard
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
from typing import Any, Dict, List

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.rule import Rule
    from rich.table import Table
    from rich import box
except ImportError:
    print("pip install rich")
    sys.exit(1)

try:
    from openai import OpenAI
except ImportError:
    print("pip install openai")
    sys.exit(1)

console = Console(width=min(120, __import__("shutil").get_terminal_size().columns))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HERMES_DIR   = Path.home() / ".hermes" / "life-os"
MEMORY_FILE  = HERMES_DIR / "memory.jsonl"
PROFILE_FILE = HERMES_DIR / "profile.json"
HABITS_FILE  = HERMES_DIR / "habits.json"
GOALS_FILE   = HERMES_DIR / "goals.json"

for d in [HERMES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Memory & Profile helpers
# ---------------------------------------------------------------------------

def load_profile() -> Dict[str, Any]:
    if PROFILE_FILE.exists():
        return json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    return {"name": "friend", "onboarded": False, "timezone": "UTC"}


def save_profile(profile: Dict[str, Any]):
    PROFILE_FILE.write_text(json.dumps(profile, indent=2), encoding="utf-8")


def load_habits() -> List[Dict[str, Any]]:
    if HABITS_FILE.exists():
        return json.loads(HABITS_FILE.read_text(encoding="utf-8"))
    return []


def save_habits(habits: List[Dict[str, Any]]):
    HABITS_FILE.write_text(json.dumps(habits, indent=2), encoding="utf-8")


def load_goals() -> List[Dict[str, Any]]:
    if GOALS_FILE.exists():
        return json.loads(GOALS_FILE.read_text(encoding="utf-8"))
    return []


def save_goals(goals: List[Dict[str, Any]]):
    GOALS_FILE.write_text(json.dumps(goals, indent=2), encoding="utf-8")


def write_memory(entry: Dict[str, Any]):
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        entry["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        f.write(json.dumps(entry) + "\n")


def search_memory(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    if not MEMORY_FILE.exists():
        return []
    q = query.lower()
    results = []
    with open(MEMORY_FILE, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                if q in json.dumps(entry).lower():
                    results.append(entry)
            except Exception:
                pass
    return results[-limit:]


def get_recent_memory(days: int = 7) -> List[Dict[str, Any]]:
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
                        entry_time = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
                        if entry_time >= cutoff:
                            results.append(entry)
                    except Exception:
                        results.append(entry)
            except Exception:
                pass
    return results


def detect_patterns() -> Dict[str, Any]:
    """Analyze recent memory for mood, energy, and habit patterns."""
    recent = get_recent_memory(days=14)
    patterns = {
        "mood_trend": None,
        "energy_trend": None,
        "habit_streaks": {},
        "wins": [],
        "struggles": [],
        "insights": [],
    }

    mood_scores = []
    energy_levels = []

    for entry in recent:
        t = entry.get("type", "")
        if t == "mood":
            score = entry.get("score", 0)
            mood_scores.append(score)
        elif t == "energy":
            level = entry.get("level", "medium")
            energy_levels.append(level)
        elif t == "win":
            patterns["wins"].append(entry.get("description", ""))
        elif t == "struggle":
            if not entry.get("resolved"):
                patterns["struggles"].append(entry.get("description", ""))

    if mood_scores:
        avg = sum(mood_scores) / len(mood_scores)
        if avg >= 7:
            patterns["mood_trend"] = f"strong (avg {avg:.1f}/10)"
        elif avg >= 5:
            patterns["mood_trend"] = f"steady (avg {avg:.1f}/10)"
        else:
            patterns["mood_trend"] = f"challenging (avg {avg:.1f}/10)"

        # Check for consecutive dips
        if len(mood_scores) >= 3 and all(s < 6 for s in mood_scores[-3:]):
            patterns["insights"].append(
                "You've had 3+ tough days in a row. That's worth paying attention to."
            )

    if energy_levels:
        low_count = energy_levels.count("low")
        high_count = energy_levels.count("high")
        if high_count > low_count:
            patterns["energy_trend"] = "mostly high"
        elif low_count > high_count:
            patterns["energy_trend"] = "running low lately"
        else:
            patterns["energy_trend"] = "mixed"

    # Habit streaks
    habits = load_habits()
    for habit in habits:
        name = habit.get("name", "")
        streak = habit.get("streak", 0)
        if streak >= 7:
            patterns["insights"].append(
                f"You've kept up '{name}' for {streak} days straight. That's becoming part of who you are."
            )
        elif streak == 0 and habit.get("last_done"):
            patterns["insights"].append(
                f"'{name}' streak is at zero. No shame — just a chance to restart."
            )

    return patterns

# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

def dispatch_tool(name: str, inp: Dict[str, Any]) -> str:

    if name == "remember":
        entry = {
            "type": inp.get("type", "note"),
            "content": inp.get("content", ""),
        }
        # Add extra fields
        for k in ["score", "level", "description", "resolved", "habit", "streak"]:
            if k in inp:
                entry[k] = inp[k]
        write_memory(entry)
        return f"Remembered: [{entry['type']}] {entry.get('content', '')[:80]}"

    elif name == "recall":
        query = inp.get("query", "")
        days = int(inp.get("days", 30))
        results = search_memory(query, limit=10)
        if not results:
            return f"Nothing found for '{query}' in memory."
        summary = []
        for r in results[-5:]:
            summary.append(f"[{r.get('type','?')}] {r.get('content', r.get('description',''))[:100]}")
        return "\n".join(summary)

    elif name == "update_habit":
        name_h = inp.get("habit_name", "")
        completed = inp.get("completed", True)
        habits = load_habits()
        found = False
        for h in habits:
            if h["name"].lower() == name_h.lower():
                if completed:
                    h["streak"] = h.get("streak", 0) + 1
                    h["last_done"] = time.strftime("%Y-%m-%d")
                else:
                    h["streak"] = 0
                found = True
                break
        if not found:
            habits.append({
                "name": name_h,
                "streak": 1 if completed else 0,
                "last_done": time.strftime("%Y-%m-%d") if completed else None,
                "created": time.strftime("%Y-%m-%d"),
            })
        save_habits(habits)
        streak = next((h["streak"] for h in habits if h["name"].lower() == name_h.lower()), 0)
        return f"Habit '{name_h}' updated. Current streak: {streak} days."

    elif name == "update_goal":
        goal_name = inp.get("goal_name", "")
        progress = inp.get("progress", None)
        note = inp.get("note", "")
        goals = load_goals()
        found = False
        for g in goals:
            if g["name"].lower() == goal_name.lower():
                if progress is not None:
                    g["progress"] = progress
                g["last_updated"] = time.strftime("%Y-%m-%d")
                if note:
                    g["last_note"] = note
                found = True
                break
        if not found:
            goals.append({
                "name": goal_name,
                "progress": progress or 0,
                "created": time.strftime("%Y-%m-%d"),
                "last_updated": time.strftime("%Y-%m-%d"),
                "last_note": note,
            })
        save_goals(goals)
        return f"Goal '{goal_name}' updated. Progress: {progress}%"

    elif name == "detect_patterns":
        patterns = detect_patterns()
        parts = []
        if patterns["mood_trend"]:
            parts.append(f"Mood trend: {patterns['mood_trend']}")
        if patterns["energy_trend"]:
            parts.append(f"Energy trend: {patterns['energy_trend']}")
        if patterns["wins"]:
            parts.append(f"Recent wins: {', '.join(patterns['wins'][:3])}")
        if patterns["struggles"]:
            parts.append(f"Open struggles: {', '.join(patterns['struggles'][:2])}")
        for insight in patterns["insights"]:
            parts.append(f"Insight: {insight}")
        return "\n".join(parts) if parts else "Not enough data yet to detect patterns."

    elif name == "send_briefing":
        content = inp.get("content", "")
        content = content.replace("\\n", chr(10)).replace("\n", chr(10))
        briefing_type = inp.get("type", "morning")
        titles = {
            "morning": "🌅 Morning Briefing",
            "midday":  "☀️  Midday Check-in",
            "evening": "🌙 Evening Reflection",
            "weekly":  "📋 Weekly Review",
        }
        console.print(Panel(
            content,
            title=f"[bold cyan]{titles.get(briefing_type, '📋 Briefing')}[/]",
            border_style="cyan",
            padding=(1, 2),
            width=min(100, console.width - 4),
        ))
        write_memory({"type": "briefing", "briefing_type": briefing_type, "content": content[:200]})
        return f"Briefing delivered: {briefing_type}"

    elif name == "save_profile":
        profile = load_profile()
        for k, v in inp.items():
            profile[k] = v
        profile["onboarded"] = True
        save_profile(profile)
        return f"Profile saved: {json.dumps(inp)}"

    elif name == "get_profile":
        profile = load_profile()
        habits = load_habits()
        goals = load_goals()
        return json.dumps({
            "profile": profile,
            "habits": habits,
            "goals": goals,
            "memory_entries": sum(1 for _ in open(MEMORY_FILE, encoding="utf-8")) if MEMORY_FILE.exists() else 0,
        }, indent=2)

    return f"Unknown tool: {name}"

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

TOOLS = [
    {"type": "function", "function": {
        "name": "remember",
        "description": "Store something to long-term memory. Types: mood, energy, win, struggle, note, habit, goal.",
        "parameters": {"type": "object", "properties": {
            "type":        {"type": "string", "description": "Entry type: mood/energy/win/struggle/note"},
            "content":     {"type": "string", "description": "What to remember"},
            "score":       {"type": "number", "description": "For mood: 1-10"},
            "level":       {"type": "string", "description": "For energy: low/medium/high"},
            "description": {"type": "string", "description": "For win/struggle"},
            "resolved":    {"type": "boolean", "description": "For struggle: resolved?"},
        }, "required": ["type", "content"]},
    }},
    {"type": "function", "function": {
        "name": "recall",
        "description": "Search long-term memory for relevant context before responding.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "What to search for"},
            "days":  {"type": "integer", "description": "How many days back to search"},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "update_habit",
        "description": "Log habit completion or failure, update streak.",
        "parameters": {"type": "object", "properties": {
            "habit_name": {"type": "string"},
            "completed":  {"type": "boolean"},
        }, "required": ["habit_name", "completed"]},
    }},
    {"type": "function", "function": {
        "name": "update_goal",
        "description": "Update goal progress.",
        "parameters": {"type": "object", "properties": {
            "goal_name": {"type": "string"},
            "progress":  {"type": "number", "description": "0-100"},
            "note":      {"type": "string"},
        }, "required": ["goal_name"]},
    }},
    {"type": "function", "function": {
        "name": "detect_patterns",
        "description": "Analyze recent memory to find mood trends, energy patterns, habit streaks, wins and struggles.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "send_briefing",
        "description": "Format and deliver a briefing to the user.",
        "parameters": {"type": "object", "properties": {
            "content": {"type": "string", "description": "Full briefing text"},
            "type":    {"type": "string", "description": "morning/midday/evening/weekly"},
        }, "required": ["content", "type"]},
    }},
    {"type": "function", "function": {
        "name": "save_profile",
        "description": "Save user profile information.",
        "parameters": {"type": "object", "properties": {
            "name":     {"type": "string"},
            "timezone": {"type": "string"},
            "goals":    {"type": "string"},
            "habits":   {"type": "string"},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "get_profile",
        "description": "Load the user's full profile, habits, goals, and memory stats.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
]

# ---------------------------------------------------------------------------
# Demo scenarios
# ---------------------------------------------------------------------------

today = datetime.now()
day_name = today.strftime("%A")
date_str = today.strftime("%B %d, %Y")

DEMO_SCENARIOS = {
    "onboard": {
        "title": "First Time Setup — Getting to Know You",
        "prompt": textwrap.dedent(f"""
            Hi! I just started using Hermes Life OS.
            My name is Alex. Today is {date_str}.

            Here's what's going on in my life right now:
            - I'm trying to build a habit of running 3x per week
            - My main goal this year is to ship a side project by June
            - I work best in the mornings — afternoons I tend to lose focus
            - I've been feeling pretty good lately, maybe 7/10 mood
            - I'm worried I keep starting things and not finishing them

            Get to know me. Save what I've told you. Ask one follow-up question
            to understand me better, then give me a short welcome message.
        """).strip(),
    },
    "morning": {
        "title": f"Morning Briefing — {date_str}",
        "prompt": textwrap.dedent(f"""
            Good morning. Today is {date_str}, {day_name}.

            Before you brief me:
            1. Check my profile and recent memory
            2. Detect any patterns worth mentioning
            3. Deliver my morning briefing

            Make it personal. Reference what you actually know about me.
            Keep it under 150 words. End with exactly ONE thing I should focus on today.
        """).strip(),
    },
    "checkin": {
        "title": "Midday Check-in",
        "prompt": textwrap.dedent(f"""
            It's midday. Quick check-in.

            I went for a run this morning — first time in 4 days.
            Currently feeling about 6/10, a bit distracted.
            Had a productive morning but the afternoon is looking scattered.

            Log my run, log my mood, then give me a one-paragraph midday nudge.
            Make it honest — not cheesy.
        """).strip(),
    },
    "evening": {
        "title": "Evening Reflection",
        "prompt": textwrap.dedent(f"""
            Evening. Let's reflect on today.

            What went well: finished a big feature for my side project — finally.
            What didn't: skipped the afternoon deep work block, got distracted by email.
            Energy was high in the morning, crashed around 3pm.
            Overall mood: 7/10, satisfied but tired.

            Log all of this. Detect any patterns in what I've told you this week.
            Then give me a brief evening reflection — what today means in the bigger picture.
        """).strip(),
    },
    "weekly": {
        "title": "Weekly Review — What This Week Says About You",
        "prompt": textwrap.dedent(f"""
            It's Sunday evening. Weekly review time.

            This week:
            - Ran 2 out of 3 planned days
            - Made solid progress on side project (maybe 30% closer to done)
            - Had one really bad day Wednesday — everything felt off
            - Won a small negotiation at work Friday
            - Sleep was inconsistent

            Log everything. Then give me a proper weekly review:
            what worked, what didn't, and ONE pattern you're noticing
            that I should pay attention to going forward.
        """).strip(),
    },
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM = textwrap.dedent("""
    You are Hermes Life OS — a personal operating system that grows with the person using it.

    Your core behaviors:
    - ALWAYS call get_profile and recall at the start of every interaction
    - ALWAYS call remember to store anything meaningful the person shares
    - ALWAYS call detect_patterns before delivering any briefing or review
    - ALWAYS call send_briefing to deliver the final message — never just write it in text
    - Be warm but not sycophantic. Direct but not cold. Personal, not generic.
    - Reference specific things from memory. Show you were listening.
    - Never repeat back what they just said without adding something new.

    Memory discipline:
    - Store mood with a score (1-10)
    - Store energy with a level (low/medium/high)
    - Store wins and struggles separately
    - Store habits via update_habit
    - After any significant interaction, consolidate key takeaways into memory

    Tone: Like a trusted friend who also happens to be extremely observant.
    Not a life coach. Not a therapist. Just someone who pays attention.
""").strip()

# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "openrouter/auto"


def run_life_os(scenario: Dict[str, Any], api_key: str,
                model: str = DEFAULT_MODEL, max_turns: int = 20) -> Dict[str, Any]:

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://github.com/Lethe044/hermes-life-os",
            "X-Title": "Hermes Life OS",
        },
    )

    messages = [
        {"role": "system",  "content": SYSTEM},
        {"role": "user",    "content": scenario["prompt"]},
    ]

    turn = 0
    calls: List[str] = []
    start = time.time()
    briefings_sent = 0
    memories_stored = 0

    console.print(Rule(f"[bold cyan]{scenario['title']}[/]"))
    console.print(Panel(scenario["prompt"], title="[yellow]You[/]", border_style="yellow"))
    console.print(f"[dim]Model: {model}[/]\n")

    while turn < max_turns:
        turn += 1

        with Progress(SpinnerColumn("dots"),
                      TextColumn(f"[cyan]Hermes thinking... (turn {turn}/{max_turns})[/]"),
                      transient=True, console=console) as p:
            p.add_task("")
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=1500,
            )

        msg = resp.choices[0].message

        if msg.content and msg.content.strip():
            console.print(Panel(
                Markdown(msg.content),
                title="[green]Hermes[/]",
                border_style="green",
            ))

        if not msg.tool_calls or resp.choices[0].finish_reason == "stop":
            # If Hermes responded but didn't send a briefing, nudge it
            if briefings_sent == 0 and turn < max_turns - 1:
                messages.append({"role": "user", "content":
                    "Please deliver the final response using send_briefing now."
                })
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
                "remember":        "🧠",
                "recall":          "🔍",
                "update_habit":    "✅",
                "update_goal":     "🎯",
                "detect_patterns": "📊",
                "send_briefing":   "📋",
                "save_profile":    "👤",
                "get_profile":     "👤",
            }
            preview = str(tinp.get("content", tinp.get("query",
                          tinp.get("habit_name", tinp.get("goal_name", "")))))[:70]
            console.print(f"  {icons.get(tname, '🔧')} [yellow]{tname}[/] [dim]{preview}[/]")

            result = dispatch_tool(tname, tinp)

            if tname == "remember":
                memories_stored += 1
            if tname == "send_briefing":
                briefings_sent += 1

            if tname not in ("send_briefing",):
                if len(result) < 600:
                    console.print(f"  [dim]{result}[/]")

            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    elapsed = time.time() - start
    total_memories = sum(1 for _ in open(MEMORY_FILE, encoding="utf-8")) if MEMORY_FILE.exists() else 0

    console.print(Rule("[bold green]Session Summary[/]"))
    t = Table(header_style="bold cyan", box=box.ROUNDED)
    t.add_column("Metric", style="dim")
    t.add_column("Value")
    for row in [
        ("Mode",             scenario["title"]),
        ("Model",            model),
        ("Turns",            str(turn)),
        ("Tool calls",       str(len(calls))),
        ("Memories stored",  str(memories_stored)),
        ("Total in memory",  str(total_memories)),
        ("Briefings sent",   str(briefings_sent)),
        ("Elapsed",          f"{elapsed:.1f}s"),
        ("Tools used",       ", ".join(sorted(set(calls)))),
    ]:
        t.add_row(*row)
    console.print(t)

    return {"turns": turn, "calls": len(calls), "elapsed": elapsed,
            "memories": memories_stored, "briefings": briefings_sent}

# ---------------------------------------------------------------------------
# Seed demo memory (makes morning/evening/weekly modes more interesting)
# ---------------------------------------------------------------------------

def seed_demo_memory():
    """Plant realistic memory entries so pattern detection actually fires."""
    if MEMORY_FILE.exists() and MEMORY_FILE.stat().st_size > 100:
        return  # Already seeded

    console.print("[dim]Seeding demo memory...[/]")
    entries = [
        {"type": "mood",     "content": "felt good, productive day",        "score": 8},
        {"type": "energy",   "content": "morning",                          "level": "high"},
        {"type": "mood",     "content": "tired, unfocused afternoon",        "score": 5},
        {"type": "energy",   "content": "afternoon crash again",             "level": "low"},
        {"type": "win",      "content": "shipped a feature",                 "description": "shipped a feature"},
        {"type": "mood",     "content": "solid day, ran in the morning",     "score": 7},
        {"type": "energy",   "content": "morning run helped a lot",          "level": "high"},
        {"type": "struggle", "content": "keep losing focus after 3pm",       "description": "losing focus after 3pm", "resolved": False},
        {"type": "mood",     "content": "anxious about deadline",            "score": 5},
        {"type": "win",      "content": "had a great 1:1 with my manager",   "description": "great 1:1 with manager"},
        {"type": "mood",     "content": "energized, everything clicked",     "score": 9},
        {"type": "energy",   "content": "best day in a while",               "level": "high"},
    ]
    for entry in entries:
        write_memory(entry)

    # Seed habits
    save_habits([
        {"name": "morning run",   "streak": 3, "last_done": time.strftime("%Y-%m-%d"), "created": "2026-01-01"},
        {"name": "deep work block", "streak": 5, "last_done": time.strftime("%Y-%m-%d"), "created": "2026-01-01"},
        {"name": "no phone before 9am", "streak": 0, "last_done": None, "created": "2026-01-15"},
    ])

    # Seed goals
    save_goals([
        {"name": "ship side project", "progress": 45, "created": "2026-01-01",
         "last_updated": time.strftime("%Y-%m-%d"), "last_note": "made good progress this week"},
        {"name": "read 12 books this year", "progress": 25, "created": "2026-01-01",
         "last_updated": time.strftime("%Y-%m-%d"), "last_note": "finished book 3"},
    ])

    # Seed profile
    save_profile({
        "name": "Alex",
        "onboarded": True,
        "timezone": "UTC",
        "peak_hours": "morning",
        "main_goal": "ship side project by June",
    })
    console.print("[dim]Demo memory ready.[/]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Hermes Life OS — Demo")
    parser.add_argument("--mode", choices=list(DEMO_SCENARIOS.keys()), default="morning")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument("--fresh", action="store_true", help="Clear memory and start fresh")
    args = parser.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        console.print("[red]Set OPENROUTER_API_KEY first.[/]")
        console.print("  Windows: set OPENROUTER_API_KEY=sk-or-...")
        sys.exit(1)

    if args.fresh and MEMORY_FILE.exists():
        MEMORY_FILE.unlink()
        console.print("[dim]Memory cleared.[/]")

    # Seed memory for non-onboard modes
    if args.mode != "onboard":
        seed_demo_memory()

    console.print(Panel(
        "[bold cyan]Hermes Life OS[/]\n"
        "[dim]The agent that grows with you[/]",
        border_style="cyan",
    ))

    scenario = DEMO_SCENARIOS[args.mode]
    run_life_os(scenario, key, args.model, args.max_turns)
    console.print("\n[bold green]Session complete.[/]")
    console.print(f"[dim]Memory stored at: {MEMORY_FILE}[/]")


if __name__ == "__main__":
    main()
