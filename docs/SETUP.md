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
