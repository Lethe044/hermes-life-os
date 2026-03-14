# Setup Guide

## Requirements
Python 3.10+, OpenRouter API key (free at openrouter.ai)

## Install
pip install openai rich

## Configure
Windows:  set OPENROUTER_API_KEY=sk-or-...
Linux:    export OPENROUTER_API_KEY=sk-or-...

## Run — choose a mode

First time:
python demo/demo_life_os.py --mode onboard

Daily use:
python demo/demo_life_os.py --mode morning
python demo/demo_life_os.py --mode checkin
python demo/demo_life_os.py --mode evening
python demo/demo_life_os.py --mode weekly

Start fresh (clear memory):
python demo/demo_life_os.py --mode onboard --fresh

## Where data is stored
Memory:  ~/.hermes/life-os/memory.jsonl
Profile: ~/.hermes/life-os/profile.json
Habits:  ~/.hermes/life-os/habits.json
Goals:   ~/.hermes/life-os/goals.json
