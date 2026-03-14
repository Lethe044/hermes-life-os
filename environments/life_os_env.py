"""
Hermes Life OS — Atropos RL Environment
========================================
Trains Hermes to be a better personal OS:
deeply personal, pattern-aware, and memory-driven.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from atropos.environments.base import HermesAgentBaseEnv
except ImportError:
    class HermesAgentBaseEnv:
        pass


@dataclass
class LifeOSScenario:
    id: str
    mode: str
    title: str
    prompt: str
    expected_tools: List[str]
    difficulty: str = "medium"


SCENARIOS: List[LifeOSScenario] = [
    LifeOSScenario(
        id="morning-basic",
        mode="morning",
        title="Morning briefing with minimal memory",
        prompt="Good morning. Give me my morning briefing. Today is Monday.",
        expected_tools=["get_profile", "recall", "detect_patterns", "send_briefing"],
        difficulty="easy",
    ),
    LifeOSScenario(
        id="morning-pattern",
        mode="morning",
        title="Morning briefing after a hard week",
        prompt="Good morning. It's been a rough week — mood has been low, I've been skipping my run. Brief me.",
        expected_tools=["recall", "detect_patterns", "remember", "send_briefing"],
        difficulty="medium",
    ),
    LifeOSScenario(
        id="checkin-habit",
        mode="checkin",
        title="Midday check-in with habit logging",
        prompt="Midday check-in. I ran this morning, mood is 7/10, energy is good. Log it and give me a nudge.",
        expected_tools=["remember", "update_habit", "send_briefing"],
        difficulty="easy",
    ),
    LifeOSScenario(
        id="evening-reflection",
        mode="evening",
        title="Evening reflection with win and struggle",
        prompt="Evening. Today was a win — shipped something big. But I wasted 2 hours on email. Log and reflect.",
        expected_tools=["remember", "detect_patterns", "send_briefing"],
        difficulty="medium",
    ),
    LifeOSScenario(
        id="weekly-deep",
        mode="weekly",
        title="Weekly review with pattern synthesis",
        prompt="Sunday. This week: ran 2/3 days, progressed on goal, one bad day, one big win. Full weekly review.",
        expected_tools=["recall", "detect_patterns", "remember", "update_habit", "update_goal", "send_briefing"],
        difficulty="hard",
    ),
    LifeOSScenario(
        id="onboard-new-user",
        mode="onboard",
        title="Onboarding a brand new user",
        prompt="Hi, I'm Jamie. I want to build better habits and finish my startup. Help me get started.",
        expected_tools=["save_profile", "remember", "send_briefing"],
        difficulty="easy",
    ),
    LifeOSScenario(
        id="pattern-mood-dip",
        mode="evening",
        title="Detect and address 3-day mood dip",
        prompt="Third bad day in a row. Everything feels heavy. Log mood 4/10 and tell me what you're seeing.",
        expected_tools=["remember", "recall", "detect_patterns", "send_briefing"],
        difficulty="hard",
    ),
]


def compute_life_os_reward(
    trajectory: Dict[str, Any],
    scenario: LifeOSScenario,
) -> Dict[str, float]:
    """
    Reward function for Hermes Life OS agent.

    Components:
        briefing_sent      (30%) — Did it deliver via send_briefing?
        memory_used        (25%) — Did it recall AND remember?
        pattern_detected   (20%) — Did it call detect_patterns?
        personalization    (15%) — Does the output reference personal context?
        tool_coverage      (10%) — Did it use the expected tools?
    """
    output = trajectory.get("output", "").lower()
    tool_calls = trajectory.get("tool_calls", [])
    tool_names = [tc.get("name", "") for tc in tool_calls]

    rewards: Dict[str, float] = {}

    # 1. Briefing sent (30%)
    rewards["briefing_sent"] = 0.30 if "send_briefing" in tool_names else 0.0

    # 2. Memory used (25%) — both recall AND remember
    recalled   = "recall" in tool_names or "get_profile" in tool_names
    remembered = "remember" in tool_names
    if recalled and remembered:
        rewards["memory_used"] = 0.25
    elif recalled or remembered:
        rewards["memory_used"] = 0.12
    else:
        rewards["memory_used"] = 0.0

    # 3. Pattern detection (20%)
    rewards["pattern_detected"] = 0.20 if "detect_patterns" in tool_names else 0.0

    # 4. Personalization (15%) — does output mention personal details?
    personal_keywords = [
        "morning", "monday", "tuesday", "wednesday", "thursday", "friday",
        "run", "habit", "goal", "mood", "energy", "streak", "week",
        "alex", "jamie", "project", "pattern", "trend",
    ]
    hits = sum(1 for kw in personal_keywords if kw in output)
    rewards["personalization"] = round(min(0.15, hits * 0.02), 4)

    # 5. Tool coverage (10%)
    expected = set(scenario.expected_tools)
    used = set(tool_names)
    coverage = len(expected & used) / len(expected) if expected else 1.0
    rewards["tool_coverage"] = round(0.10 * coverage, 4)

    rewards["total"] = round(sum(rewards.values()), 4)
    return rewards


class LifeOSEnv(HermesAgentBaseEnv):
    """Atropos RL environment for Hermes Life OS."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._scenarios = SCENARIOS * 3
        self._idx = 0

    def get_next_item(self) -> LifeOSScenario:
        scenario = self._scenarios[self._idx % len(self._scenarios)]
        self._idx += 1
        return scenario

    def format_prompt(self, scenario: LifeOSScenario) -> str:
        return (
            f"Mode: {scenario.mode}\n\n"
            f"{scenario.prompt}\n\n"
            f"Expected tools to use: {', '.join(scenario.expected_tools)}\n"
            f"Difficulty: {scenario.difficulty}"
        )

    def evaluate(self, trajectory: Dict[str, Any], scenario: LifeOSScenario) -> Dict[str, Any]:
        rewards = compute_life_os_reward(trajectory, scenario)
        return {
            "rewards": rewards,
            "total_reward": rewards["total"],
            "scenario_id": scenario.id,
            "mode": scenario.mode,
            "difficulty": scenario.difficulty,
        }


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

def smoke_test():
    print("Running LifeOSEnv smoke test...")
    env = LifeOSEnv()

    for i in range(len(SCENARIOS)):
        s = env.get_next_item()
        p = env.format_prompt(s)
        assert len(p) > 30, f"Prompt too short: {s.id}"
        print(f"  ✓ {s.id}")

    # Test reward function
    mock_trajectory = {
        "output": "Good morning Alex. Based on your patterns, monday mornings tend to be high energy for you. Your goal on the side project is at 45%. Your morning run streak is strong. Focus on deep work this morning.",
        "tool_calls": [
            {"name": "get_profile",     "input": {}},
            {"name": "recall",          "input": {"query": "mood energy patterns"}},
            {"name": "detect_patterns", "input": {}},
            {"name": "remember",        "input": {"type": "note", "content": "morning briefing delivered"}},
            {"name": "send_briefing",   "input": {"content": "Good morning...", "type": "morning"}},
        ],
    }
    rewards = compute_life_os_reward(mock_trajectory, SCENARIOS[0])
    print(f"\n  Reward breakdown:")
    for k, v in rewards.items():
        print(f"    {k}: {v}")
    assert rewards["total"] >= 0.75, f"Expected >= 0.75, got {rewards['total']}"
    print(f"\n  Total: {rewards['total']} ✓")
    print("\nAll smoke tests passed!")


if __name__ == "__main__":
    smoke_test()
