"""
Example Hermes Life OS plugin - dice & coin flip.

Copy this file into ~/.hermes/life-os/plugins/ to enable it (or
LIFE_OS_PLUGINS_DIR if you've set that instead):

    mkdir -p ~/.hermes/life-os/plugins
    cp demo/plugins_examples/dice.py ~/.hermes/life-os/plugins/

No extra dependencies - this is the smallest possible plugin, meant as
a copy-paste starting point. See docs/PLUGINS.md for the full plugin
API, and weather.py in this same folder for an example that reads
storage/state.
"""

from __future__ import annotations

import random

PLUGIN_NAME = "dice"

TOOLS = [
    {"type": "function", "function": {
        "name": "roll_dice",
        "description": "Roll one or more N-sided dice, e.g. for deciding between options or just for fun.",
        "parameters": {"type": "object", "properties": {
            "sides": {"type": "integer", "description": "Sides per die. Default 6."},
            "count": {"type": "integer", "description": "Number of dice to roll. Default 1."},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "flip_coin",
        "description": "Flip a coin - returns heads or tails.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
]


def dispatch(name, inp):
    if name == "roll_dice":
        sides = int(inp.get("sides") or 6)
        count = int(inp.get("count") or 1)
        if sides < 2:
            return "A die needs at least 2 sides."
        count = max(1, min(count, 20))  # sane upper bound
        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls)
        if count == 1:
            return f"Rolled a {sides}-sided die: {rolls[0]}"
        return f"Rolled {count}x d{sides}: {rolls} (total {total})"

    if name == "flip_coin":
        return random.choice(["Heads", "Tails"])

    return None  # not one of ours
