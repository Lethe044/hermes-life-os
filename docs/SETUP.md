# Setup Guide

## Requirements
Python 3.10+, and one of the following:
- Nothing extra - a local Ollama server (free, no API key)
- An Anthropic API key
- An OpenAI API key
- An OpenRouter API key (free credits available at openrouter.ai)

## Install
pip install -r requirements.txt

## Configure
Pick one backend. The provider is auto-detected from whichever key is
set (priority: anthropic > openai > openrouter > ollama), or force one
explicitly with `--provider` / `LIFE_OS_PROVIDER`.

Local, free, no key:
    ollama serve
    ollama pull llama3.1

Anthropic:
    Windows:      set ANTHROPIC_API_KEY=sk-ant-...
    macOS/Linux:  export ANTHROPIC_API_KEY=sk-ant-...

OpenAI:
    Windows:      set OPENAI_API_KEY=sk-...
    macOS/Linux:  export OPENAI_API_KEY=sk-...

OpenRouter:
    Windows:      set OPENROUTER_API_KEY=sk-or-...
    macOS/Linux:  export OPENROUTER_API_KEY=sk-or-...

## Run — choose a mode

First time:
python demo/demo_life_os.py --mode onboard

Daily use:
python demo/demo_life_os.py --mode morning
python demo/demo_life_os.py --mode checkin
python demo/demo_life_os.py --mode evening
python demo/demo_life_os.py --mode weekly

Force a specific backend regardless of which keys are set:
python demo/demo_life_os.py --mode morning --provider anthropic

Start fresh (clear memory):
python demo/demo_life_os.py --mode onboard --fresh

## Where data is stored
Memory:  ~/.hermes/life-os/memory.jsonl
Profile: ~/.hermes/life-os/profile.json
Habits:  ~/.hermes/life-os/habits.json
Goals:   ~/.hermes/life-os/goals.json

Multiple people sharing one install: add --profile <name> (or set
LIFE_OS_PROFILE) to any command above. Data moves to
~/.hermes/life-os/profiles/<name>/, fully isolated from everyone else.

## Optional: encryption at rest

set LIFE_OS_ENCRYPTION_KEY=your-passphrase-here

Encrypts every data file and every memory.jsonl line. Off by default.
There is no password recovery - losing the passphrase means losing
access to that data, by design. Requires the `cryptography` package
(pip install "hermes-life-os[encryption]").

## Bulk-importing existing data

hermes-life-os-import --apple-health export.xml
hermes-life-os-import --csv my_data.csv

Preserves real historical dates. See the README's "Health Data Import"
section for supported formats.

## Goals that track themselves

Instead of manually updating a percentage, link a goal to a metric
through chat: "set a goal to sleep 7+ hours a night". Progress is then
computed from your actual logged data. See the README's "Goal Tracking"
section.

## Calendar import (meeting load)

hermes-life-os-calendar --ics calendar.ics

Imports meeting hours per day from a standard .ics export (no OAuth/API
needed). See the README's "Calendar Import" section.

## Exporting your data

hermes-life-os-export --json backup.json --csv summary.csv

Your data isn't locked in - see the README's "Data Export" section.

## Proactive nudges

Running the scheduler (python demo/run_scheduler.py) includes a daily
20:00 check that proactively flags anomalies or lagging goals, with no
LLM call and no notification at all if nothing stands out.
