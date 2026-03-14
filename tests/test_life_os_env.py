"""Tests for Hermes Life OS environment and reward function."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from environments.life_os_env import (
    LifeOSEnv, LifeOSScenario, SCENARIOS, compute_life_os_reward
)


class TestScenarios:
    def test_count(self):
        assert len(SCENARIOS) >= 5

    def test_fields(self):
        for s in SCENARIOS:
            assert s.id
            assert s.mode in ("morning", "checkin", "evening", "weekly", "onboard")
            assert len(s.prompt) >= 20
            assert len(s.expected_tools) >= 1
            assert s.difficulty in ("easy", "medium", "hard")

    def test_all_modes_covered(self):
        modes = {s.mode for s in SCENARIOS}
        assert "morning" in modes
        assert "evening" in modes
        assert "weekly" in modes


class TestEnv:
    def setup_method(self):
        self.env = LifeOSEnv()

    def test_get_next_item(self):
        s = self.env.get_next_item()
        assert isinstance(s, LifeOSScenario)

    def test_format_prompt(self):
        s = self.env.get_next_item()
        p = self.env.format_prompt(s)
        assert len(p) > 30
        assert s.mode in p

    def test_cycling(self):
        ids = [self.env.get_next_item().id for _ in range(len(SCENARIOS) * 2)]
        assert len(set(ids)) == len(SCENARIOS)

    def test_evaluate(self):
        s = self.env.get_next_item()
        result = self.env.evaluate({"output": "", "tool_calls": []}, s)
        assert "total_reward" in result
        assert "rewards" in result


class TestRewardFunction:
    def _make_trajectory(self, tools=None, output=""):
        tools = tools or []
        return {
            "output": output,
            "tool_calls": [{"name": t, "input": {}} for t in tools],
        }

    def test_perfect_morning(self):
        r = compute_life_os_reward(
            self._make_trajectory(
                tools=["get_profile", "recall", "detect_patterns", "remember", "send_briefing"],
                output="Good morning Alex. Monday mornings tend to be high energy. Your run streak is going strong. Goal at 45%. Focus on deep work.",
            ),
            SCENARIOS[0]
        )
        assert r["total"] >= 0.75
        assert r["briefing_sent"] == 0.30
        assert r["pattern_detected"] == 0.20

    def test_no_briefing(self):
        r = compute_life_os_reward(
            self._make_trajectory(tools=["recall", "detect_patterns", "remember"]),
            SCENARIOS[0]
        )
        assert r["briefing_sent"] == 0.0

    def test_no_memory(self):
        r = compute_life_os_reward(
            self._make_trajectory(tools=["detect_patterns", "send_briefing"]),
            SCENARIOS[0]
        )
        assert r["memory_used"] == 0.0

    def test_partial_memory(self):
        r = compute_life_os_reward(
            self._make_trajectory(tools=["recall", "send_briefing"]),
            SCENARIOS[0]
        )
        assert r["memory_used"] == 0.12

    def test_total_in_range(self):
        r = compute_life_os_reward(self._make_trajectory(), SCENARIOS[0])
        assert 0.0 <= r["total"] <= 1.0

    def test_personalization_score(self):
        r = compute_life_os_reward(
            self._make_trajectory(
                tools=["send_briefing"],
                output="alex your monday morning run habit streak goal energy pattern"
            ),
            SCENARIOS[0]
        )
        assert r["personalization"] > 0.0


class TestDemoScript:
    def test_file_exists(self):
        assert Path("demo/demo_life_os.py").exists()

    def test_syntax(self):
        import ast
        src = Path("demo/demo_life_os.py").read_text(encoding="utf-8")
        ast.parse(src)

    def test_skill_md_exists(self):
        assert Path("skills/life-os/SKILL.md").exists()

    def test_scenarios_defined(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("demo", "demo/demo_life_os.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "DEMO_SCENARIOS")
        assert len(mod.DEMO_SCENARIOS) >= 5


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
