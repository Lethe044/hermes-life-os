"""Tests for demo/heatmap.py."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))


@pytest.fixture()
def heatmap(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "achievements", "heatmap"):
        if mod in sys.modules:
            del sys.modules[mod]
    import heatmap as hm
    importlib.reload(hm)
    import storage
    storage.set_active_profile(None)
    return hm


class TestComputeDailyCounts:
    def test_no_data_returns_empty_dict(self, heatmap):
        assert heatmap.compute_daily_counts(90) == {}

    def test_counts_entries_per_day(self, heatmap):
        import storage
        storage.write_memory({"type": "mood", "content": "a", "score": 5})
        storage.write_memory({"type": "mood", "content": "b", "score": 6})
        counts = heatmap.compute_daily_counts(90)
        assert sum(counts.values()) == 2
        assert len(counts) == 1  # both written "now" -> same day


class TestComputeStats:
    def test_empty_counts(self, heatmap):
        stats = heatmap.compute_stats({}, 90)
        assert stats["active_days"] == 0
        assert stats["total_entries"] == 0
        assert stats["current_streak"] == 0
        assert stats["days"] == 90

    def test_populated_counts(self, heatmap):
        counts = {"2026-01-01": 3, "2026-01-02": 1}
        stats = heatmap.compute_stats(counts, 30)
        assert stats["active_days"] == 2
        assert stats["total_entries"] == 4


class TestLevelForCount:
    def test_zero_count_is_level_zero(self, heatmap):
        assert heatmap._level_for_count(0, 10) == 0

    def test_max_count_is_level_four(self, heatmap):
        assert heatmap._level_for_count(10, 10) == 4

    def test_single_data_point_gets_level_four(self, heatmap):
        # When max_count <= 1, any positive count should be full intensity.
        assert heatmap._level_for_count(1, 1) == 4

    def test_intermediate_levels_scale(self, heatmap):
        assert heatmap._level_for_count(1, 10) == 1
        assert heatmap._level_for_count(3, 10) == 2
        assert heatmap._level_for_count(6, 10) == 3


class TestRenderSvg:
    def test_produces_valid_svg_with_no_data(self, heatmap):
        svg = heatmap.render_svg({}, days=90)
        assert svg.startswith("<svg")
        assert svg.endswith("</svg>")
        assert "<rect" in svg

    def test_produces_valid_svg_with_data(self, heatmap):
        from datetime import datetime, timedelta
        recent_date = (datetime.utcnow() - timedelta(days=5)).strftime("%Y-%m-%d")
        counts = {recent_date: 5}
        svg = heatmap.render_svg(counts, days=90)
        assert svg.startswith("<svg")
        assert recent_date in svg  # tooltip title present

    def test_larger_window_produces_wider_svg(self, heatmap):
        small = heatmap.render_svg({}, days=30)
        large = heatmap.render_svg({}, days=365)

        def _extract_width(svg):
            start = svg.index('width="') + len('width="')
            end = svg.index('"', start)
            return int(svg[start:end])

        assert _extract_width(large) > _extract_width(small)


class TestRenderHtml:
    def test_wraps_svg_with_stats(self, heatmap):
        svg = "<svg></svg>"
        stats = {"active_days": 5, "total_entries": 20, "current_streak": 3, "days": 90}
        html = heatmap.render_html(svg, stats)
        assert "<!DOCTYPE html>" in html
        assert svg in html
        assert "5 active day" in html
        assert "3-day current streak" in html


class TestMainCli:
    def test_svg_output(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        for mod in ("storage", "analytics", "achievements", "heatmap"):
            if mod in sys.modules:
                del sys.modules[mod]
        import heatmap as hm
        importlib.reload(hm)

        out_path = tmp_path / "heatmap.svg"
        monkeypatch.setattr(sys, "argv", ["heatmap.py", "--out", str(out_path)])
        hm.main()
        assert out_path.exists()
        assert out_path.read_text(encoding="utf-8").startswith("<svg")

    def test_html_output(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        for mod in ("storage", "analytics", "achievements", "heatmap"):
            if mod in sys.modules:
                del sys.modules[mod]
        import heatmap as hm
        importlib.reload(hm)

        out_path = tmp_path / "heatmap.html"
        monkeypatch.setattr(sys, "argv", ["heatmap.py", "--out", str(out_path)])
        hm.main()
        assert "<!DOCTYPE html>" in out_path.read_text(encoding="utf-8")
