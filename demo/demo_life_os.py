#!/usr/bin/env python3
"""
Hermes Life OS - Full Featured Demo
=====================================
A personal operating system that learns who you are,
tracks your health, habits, goals, and mental state,
detects patterns across every dimension of your life,
and grows smarter every single day.

Requirements:  pip install -r requirements.txt
Setup:         Pick one backend, no code changes needed:
                 - Local, free, no key: run `ollama serve` (pull a tool-calling
                   model first, e.g. `ollama pull llama3.1`)
                 - Anthropic:  set ANTHROPIC_API_KEY=sk-ant-...
                 - OpenAI:     set OPENAI_API_KEY=sk-...
                 - OpenRouter: set OPENROUTER_API_KEY=sk-or-...
               The provider is auto-detected from whichever key is set
               (falls back to ollama). Force one with --provider or
               LIFE_OS_PROVIDER=anthropic|openai|openrouter|ollama.

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

Architecture:
    This file is the CLI/UI/orchestration layer only. Storage, pattern
    detection, correlation analytics, and tool implementations live in
    sibling modules for testability and maintainability:
        storage.py   - local persistence (profile, habits, goals, logs, memory)
        patterns.py  - trend detection across mood/sleep/stress/energy
        analytics.py - real Pearson correlation engine
        tools.py     - dispatch_tool() + TOOLS schema for the LLM agent
        scheduler.py - cron-style daily/weekly briefing scheduler
        notifications.py - pluggable delivery (console/webhook/Telegram/email)
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

import shutil
import concurrent.futures

# Ensure this file's own directory is importable regardless of how the
# script is invoked (as __main__, via pytest, or via importlib spec loading).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from llm_providers import (
    PROVIDERS, ProviderError, resolve_provider, default_model_for, get_client,
)
from storage import (
    HERMES_DIR, MEMORY_FILE, PROFILE_FILE, HABITS_FILE, GOALS_FILE,
    NUTRITION_FILE, SLEEP_FILE, HYDRATION_FILE, FITNESS_FILE,
    FOCUS_FILE, MENTAL_FILE,
    load_profile, save_profile, load_habits, save_habits,
    load_goals, save_goals, load_nutrition, save_nutrition,
    load_sleep, save_sleep, load_hydration, save_hydration,
    load_fitness, save_fitness, load_focus, save_focus,
    load_mental, save_mental,
    write_memory, search_memory, get_recent_memory, memory_count,
)
from patterns import detect_patterns
from analytics import compute_correlations, format_correlation_insights
from tools import dispatch_tool, TOOLS

console = Console(width=min(110, shutil.get_terminal_size().columns))


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
        "title": f"Morning Briefing - {date_str}",
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
            - Sleep quality: 8/10 - felt well rested
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
            - Stress today: 4/10 - much better than yesterday
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
    "dream": {
        "title": "Dream Journal - Morning Log",
        "prompt": (
            "Good morning. I just woke up and want to log last night's dream before I forget it.\n\n"
            "I was at my old school but it looked different. I had an important exam but "
            "I couldn't find the classroom. I kept running down hallways that changed shape. "
            "There was water flooding from somewhere. I felt anxious but also strangely calm "
            "by the end. Overall it was vivid, maybe 7/10.\n\n"
            "Log this dream with all details - emotions, symbols, tone, vividness. "
            "Then check if there are any recurring patterns in my recent dreams. "
            "Also look at my recent stress and sleep data - is there a correlation? "
            "Give me a brief dream analysis as a morning briefing."
        ),
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
    - log_dream (for dream journal - symbols, emotions, tone, vividness)
    - update_habit, update_goal
    - get_health_dashboard, get_weekly_health_report
    - detect_patterns, remember, recall

    Tone: trusted friend who pays close attention and connects the dots.
    Not a coach. Not a doctor. Just someone who genuinely notices things.
""").strip()

# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

# Per-provider defaults live in llm_providers.DEFAULT_MODELS and are picked
# automatically in main(). This constant only exists as a fallback for
# functions called directly (e.g. in tests) without going through main().
DEFAULT_MODEL = "nousresearch/hermes-3-llama-3.1-405b"


def run_life_os(scenario: Dict[str, Any], client, model: str = DEFAULT_MODEL,
                max_turns: int = 25, user_message: str = "") -> Dict[str, Any]:

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
            # In chat mode, don't force send_briefing - let model respond naturally
            if briefings_sent == 0 and turn < max_turns - 1 and user_message == "":
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

        icons = {
            "remember": "🧠", "recall": "🔍", "log_meal": "🥗",
            "log_sleep": "😴", "log_hydration": "💧", "log_workout": "💪",
            "log_stress": "😤", "log_meditation": "🧘", "log_gratitude": "🙏",
            "log_focus_session": "🎯", "update_habit": "✅", "update_goal": "🎯",
            "detect_patterns": "📊", "get_health_dashboard": "❤️",
            "get_weekly_health_report": "📋", "send_briefing": "📋",
            "save_profile": "👤", "get_profile": "👤",
        }

        # Parallel tools: read-only, no side effects - safe to run concurrently
        PARALLEL_TOOLS = {
            "get_profile", "get_health_dashboard",
            "get_weekly_health_report", "detect_patterns", "recall",
        }

        parallel_tcs = [tc for tc in msg.tool_calls
                        if tc.function.name in PARALLEL_TOOLS]
        sequential_tcs = [tc for tc in msg.tool_calls
                          if tc.function.name not in PARALLEL_TOOLS]

        def _run_tool(tc):
            try:
                tinp = json.loads(tc.function.arguments)
            except Exception:
                tinp = {}
            return tc, tinp, dispatch_tool(tc.function.name, tinp)

        # --- Concurrent execution for read-only tools ---
        parallel_results = {}
        if parallel_tcs:
            if len(parallel_tcs) > 1:
                console.print(
                    f"  [dim cyan]⚡ Running {len(parallel_tcs)} tools concurrently...[/]"
                )
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=len(parallel_tcs)
            ) as ex:
                futs = {ex.submit(_run_tool, tc): tc for tc in parallel_tcs}
                for fut in concurrent.futures.as_completed(futs):
                    tc, tinp, result = fut.result()
                    parallel_results[tc.id] = (tc, tinp, result)

            for tc in parallel_tcs:
                tc_obj, tinp, result = parallel_results[tc.id]
                tname = tc_obj.function.name
                calls.append(tname)
                preview = str(tinp.get("query", ""))[:60]
                console.print(
                    f"  {icons.get(tname,'🔧')} [yellow]{tname}[/] [dim]{preview}[/]"
                )
                messages.append({
                    "role": "tool", "tool_call_id": tc.id, "content": result
                })

        # --- Sequential execution for stateful tools ---
        for tc in sequential_tcs:
            tname = tc.function.name
            try:
                tinp = json.loads(tc.function.arguments)
            except Exception:
                tinp = {}
            calls.append(tname)

            preview = str(tinp.get("food", tinp.get("content", tinp.get("query",
                          tinp.get("task", tinp.get("habit_name",
                          tinp.get("goal_name", "")))))))[:60]
            console.print(
                f"  {icons.get(tname,'🔧')} [yellow]{tname}[/] [dim]{preview}[/]"
            )

            result = dispatch_tool(tname, tinp)

            if tname in ("remember", "log_meal", "log_sleep", "log_hydration",
                         "log_workout", "log_stress", "log_meditation",
                         "log_gratitude", "log_focus_session"):
                memories_stored += 1

            if tname == "send_briefing":
                briefings_sent += 1
            elif tname not in ("get_profile", "get_health_dashboard",
                                "get_weekly_health_report"):
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
# Voice mode
# ---------------------------------------------------------------------------

def speak(text: str, elevenlabs_key: str = "") -> None:
    """Speak text using Windows SAPI TTS (free, no API key needed)."""
    try:
        import re, subprocess
        clean = re.sub(r'\[.*?\]', '', text)
        clean = re.sub(r'[#*`]', '', clean).strip()
        if not clean:
            return
        if os.name == "nt":
            # Windows built-in TTS via PowerShell - completely free
            ps_cmd = (
                f"Add-Type -AssemblyName System.Speech; "
                f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.Rate = 1; "
                f"$s.Speak(\"{clean[:400]}\");"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-c", ps_cmd],
                capture_output=True, timeout=30
            )
        else:
            subprocess.run(["espeak", clean[:400]], capture_output=True, timeout=15)
    except Exception as e:
        console.print(f"[dim]Voice: {e}[/]")

def run_voice_mode(client, elevenlabs_key: str, model: str = DEFAULT_MODEL) -> None:
    try:
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        mic_available = True
    except ImportError:
        mic_available = False
        console.print("[yellow]pip install SpeechRecognition pyaudio for mic input[/]")
        console.print("[dim]Falling back to keyboard input with voice output.[/]")

    seed_demo_memory()

    console.print(Panel(
        "[bold cyan]Hermes Life OS - Voice Mode[/]\n"
        "[dim]Speak or type. Hermes responds with voice.\n"
        "Say or type 'exit' to leave.[/]",
        border_style="cyan",
    ))

    voice_system = (
        "You are Hermes Life OS in voice mode. "
        "Keep responses SHORT - max 3 sentences. "
        "No bullet points or markdown. Just natural conversational speech. "
        "Use tools when needed but always end with a spoken response."
    )

    messages = [{"role": "system", "content": voice_system}]

    while True:
        if mic_available:
            console.print("[dim]Listening... (or type)[/]")
            try:
                with sr.Microphone() as source:
                    recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    recognizer.pause_threshold = 1.5
                    recognizer.phrase_threshold = 0.3
                    try:
                        audio = recognizer.listen(source, timeout=8, phrase_time_limit=20)
                        user_input = recognizer.recognize_google(audio)
                        console.print(f"[bold][You]:[/] {user_input}")
                    except Exception:
                        user_input = input("[You] (type): ").strip()
            except Exception:
                user_input = input("[You]: ").strip()
        else:
            user_input = input("\n[You]: ").strip()

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye", "q"):
            farewell = "Goodbye! Take care."
            console.print(f"[green]Hermes:[/] {farewell}")
            speak(farewell, elevenlabs_key)
            break

        messages.append({"role": "user", "content": user_input})

        with Progress(SpinnerColumn("dots"),
                      TextColumn("[cyan]Hermes thinking...[/]"),
                      transient=True, console=console) as p:
            p.add_task("")
            resp = client.chat.completions.create(
                model=model, messages=messages,
                tools=TOOLS, tool_choice="auto", max_tokens=300,
            )

        msg = resp.choices[0].message

        if msg.tool_calls:
            messages.append({
                "role": "assistant", "content": msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ],
            })
            for tc in msg.tool_calls:
                try:
                    tinp = json.loads(tc.function.arguments)
                except Exception:
                    tinp = {}
                result = dispatch_tool(tc.function.name, tinp)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            resp2 = client.chat.completions.create(
                model=model, messages=messages, max_tokens=200)
            response_text = resp2.choices[0].message.content or ""
            messages.append({"role": "assistant", "content": response_text})
        else:
            response_text = msg.content or ""
            messages.append({"role": "assistant", "content": response_text})

        if response_text:
            console.print(Panel(
                response_text, title="[green]Hermes[/]",
                border_style="green", width=min(100, console.width - 4),
            ))
            speak(response_text, elevenlabs_key)



# ---------------------------------------------------------------------------
# Chat mode
# ---------------------------------------------------------------------------

def run_chat_mode(client, model: str = DEFAULT_MODEL):
    """Interactive chat - you type, Hermes responds using your full memory."""
    console.print(Panel(
        "[bold cyan]Hermes Life OS - Chat Mode[/]\n"
        "[dim]Type anything. Hermes will respond using everything it knows about you.\n"
        "Type 'exit' or 'quit' to leave.[/]",
        border_style="cyan",
    ))

    seed_demo_memory()

    # Chat system prompt
    chat_system = (
        "You are Hermes Life OS - a personal assistant that tracks health and life data. "
        "ALWAYS use tools. Never respond without calling at least one tool first. "
        "If user says log/track/record anything: call the appropriate log tool immediately. "
        "If user asks how they feel or pattern questions: call detect_patterns and get_health_dashboard. "
        "Always call get_profile first. Always end with send_briefing. "
        "log_meal for food, log_workout for exercise, log_hydration for water, "
        "log_sleep for sleep, log_stress for stress, log_focus_session for work sessions."
    )

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

        # Use lighter system prompt for chat
        scenario = {
            "title": "Chat",
            "prompt": user_input,
        }
        run_life_os(scenario, client, model, max_turns=10, user_message=user_input)


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

    # Seed dream entries
    dream_seeds = [
        {"type": "dream", "date": time.strftime("%Y-%m-%d"),
         "content": "running late, couldn't find the meeting room",
         "emotions": ["anxiety", "frustration"], "symbols": ["running", "office", "late"],
         "tone": "negative", "vividness": 6},
        {"type": "dream", "date": time.strftime("%Y-%m-%d"),
         "content": "flying over a city, felt free",
         "emotions": ["joy", "peace"], "symbols": ["flying", "city", "freedom"],
         "tone": "positive", "vividness": 8},
        {"type": "dream", "date": time.strftime("%Y-%m-%d"),
         "content": "exam I hadn't studied for, water flooding the room",
         "emotions": ["anxiety", "panic"], "symbols": ["exam", "water", "school"],
         "tone": "negative", "vividness": 7},
    ]
    for d in dream_seeds:
        write_memory(d)

    console.print("[dim]Demo memory ready.[/]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _print_provider_troubleshooting(provider: str, error: Exception) -> None:
    """Turn a raw client/network exception into a short, actionable hint
    instead of a bare traceback - most first-run failures are either
    'ollama isn't running' or 'bad/missing API key'."""
    console.print(f"\n[red]Request to '{provider}' failed:[/] {error}")
    if provider == "ollama":
        console.print(
            "[yellow]Tip:[/] Ollama provider needs a local server running with a "
            "tool-calling model pulled:\n"
            "  ollama serve\n"
            "  ollama pull llama3.1\n"
            "Or switch providers: --provider anthropic|openai|openrouter "
            "(with the matching API key set)."
        )
    else:
        console.print(
            f"[yellow]Tip:[/] Double-check your API key and that '{provider}' "
            f"is spelled correctly, or try --provider ollama for a free local run."
        )


def main():
    parser = argparse.ArgumentParser(description="Hermes Life OS")
    parser.add_argument("--mode", choices=list(DEMO_SCENARIOS.keys()), default="morning",
                        help="Mode: " + ", ".join(DEMO_SCENARIOS.keys()))
    parser.add_argument("--provider", choices=list(PROVIDERS), default=None,
                        help="LLM backend: ollama (free/local), openai, anthropic, "
                             "openrouter. Default: auto-detect from env vars, "
                             "falling back to ollama.")
    parser.add_argument("--model",     default=None,
                        help="Overrides the provider's default model.")
    parser.add_argument("--max-turns", type=int, default=25)
    parser.add_argument("--fresh",     action="store_true", help="Clear all data and start fresh")
    parser.add_argument("--voice",     action="store_true", help="Voice mode - speak to Hermes")
    parser.add_argument("--elevenlabs-key", default=None, help="ElevenLabs API key for TTS")
    args = parser.parse_args()

    try:
        provider = resolve_provider(args.provider)
        client = get_client(provider)
    except ProviderError as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)

    model = args.model or default_model_for(provider)
    console.print(f"[dim]Provider: {provider}  Model: {model}[/]")

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

    try:
        if args.voice:
            el_key = args.elevenlabs_key or os.environ.get("ELEVENLABS_API_KEY", "")
            if not el_key:
                console.print("[red]Set --elevenlabs-key or ELEVENLABS_API_KEY for voice mode.[/]")
                sys.exit(1)
            run_voice_mode(client, el_key, model)
            return

        if args.mode == "chat":
            run_chat_mode(client, model)
            return
    except Exception as e:
        _print_provider_troubleshooting(provider, e)
        sys.exit(1)

    if args.mode != "onboard":
        seed_demo_memory()

    scenario = DEMO_SCENARIOS[args.mode]
    try:
        run_life_os(scenario, client, model, args.max_turns)
    except Exception as e:
        _print_provider_troubleshooting(provider, e)
        sys.exit(1)
    console.print("\n[bold green]Session complete.[/]")
    console.print(f"[dim]Memory: {MEMORY_FILE}[/]")


if __name__ == "__main__":
    main()
