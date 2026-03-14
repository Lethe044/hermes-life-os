# Hermes Life OS — Technical Writeup

## The Problem

Every productivity tool treats you like a new user every day.
Your journal doesn't know your calendar. Your habit tracker doesn't know your mood.
Your AI assistant asks you the same questions it asked yesterday.

No single system accumulates knowledge about you over time,
connects the dots between your patterns, and uses that to show up better.

## The Solution

Hermes Life OS is a personal operating system — not a task manager, not a chatbot.
It runs on a daily cron schedule, stores everything you share in long-term memory,
detects behavioral patterns across weeks, and delivers briefings that feel like
they were written by someone who actually knows you.

Because over time, Hermes actually does.

## How It Works

**Memory-first architecture:** Every interaction starts with recall.
Hermes searches memory before it says anything. It never asks what it already knows.

**Pattern detection:** After accumulating enough entries, Hermes starts noticing things.
Three low-mood days in a row. Energy that always crashes on Wednesday afternoons.
A habit streak the user didn't realize they were building. These observations surface
naturally in briefings — never as clinical reports, always as observations from a friend.

**Daily rhythm via Cron:**
- 07:00 — Morning briefing: patterns, priorities, one insight
- 12:00 — Midday check-in: log energy, quick nudge
- 18:00 — Evening reflection: wins, struggles, what today means
- 23:00 — Memory consolidation: store the day's patterns
- Monday 08:00 — Weekly review: what this week says about you

**Five demo modes:** onboard, morning, checkin, evening, weekly.
Each mode seeds realistic memory so pattern detection actually fires during the demo.

## Atropos RL Integration

The reward function trains Hermes to become a better personal OS over time:

- **Briefing delivered** (30%): Did it actually send the briefing, not just write it?
- **Memory used** (25%): Did it both recall context AND store new information?
- **Patterns detected** (20%): Did it analyze trends before responding?
- **Personalization** (15%): Does the output reference real user context?
- **Tool coverage** (10%): Did it use the right tools for the mode?

Seven training scenarios of varying difficulty ensure Hermes learns to handle
simple morning briefings through complex weekly pattern synthesis.

## Why This Wins

NousResearch's tagline is "the agent that grows with you."
Every other submission grows at completing tasks.
Hermes Life OS grows at knowing a person.

That's a fundamentally different kind of intelligence — and it's what Hermes was built for.
