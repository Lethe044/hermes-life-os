"""Tests for demo/wrapped.py. build_wrapped_stats() is pure-data and
tested without touching matplotlib; render_wrapped_image() is tested
against a real (small) rendered PNG to catch actual rendering
failures, not just logic bugs."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))

matplotlib = pytest.importorskip("matplotlib")


@pytest.fixture()
def wrapped(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "life_score", "achievements", "wrapped"):
        if mod in sys.modules:
            del sys.modules[mod]
    import wrapped as w
    importlib.reload(w)
    import storage
    storage.set_active_profile(None)
    return w


class TestPeriodLabel:
    @pytest.mark.parametrize("days,expected", [
        (1, "Week"), (7, "Week"), (8, "Week"),
        (9, "Month"), (30, "Month"), (35, "Month"),
        (36, "Quarter"), (90, "Quarter"), (100, "Quarter"),
        (101, "Year"), (365, "Year"),
    ])
    def test_period_labels(self, wrapped, days, expected):
        assert wrapped._period_label(days) == expected


class TestAvgMetric:
    def test_empty_daily_returns_none(self, wrapped):
        assert wrapped._avg_metric({}, "mood") is None

    def test_averages_present_values(self, wrapped):
        daily = {"2026-01-01": {"mood": 6}, "2026-01-02": {"mood": 8}}
        assert wrapped._avg_metric(daily, "mood") == 7.0

    def test_ignores_days_missing_metric(self, wrapped):
        daily = {"2026-01-01": {"mood": 6}, "2026-01-02": {"sleep": 8}}
        assert wrapped._avg_metric(daily, "mood") == 6.0


class TestBuildWrappedStats:
    def test_no_data_returns_zeroed_stats(self, wrapped):
        stats = wrapped.build_wrapped_stats(30)
        assert stats["n_entries"] == 0
        assert stats["avg_life_score"] is None
        assert stats["best_day"] is None
        assert stats["earned_badges"] == []

    def test_with_data_returns_populated_stats(self, wrapped):
        import storage
        storage.write_memory({"type": "mood", "content": "great day", "score": 9})
        storage.write_memory({"type": "workout", "content": "run", "duration_min": 30})
        stats = wrapped.build_wrapped_stats(30)
        assert stats["n_entries"] == 2
        assert stats["avg_life_score"] is not None
        assert stats["best_day"] is not None
        assert any(b["id"] == "count-workout-1" for b in stats["earned_badges"])

    def test_days_field_passed_through(self, wrapped):
        stats = wrapped.build_wrapped_stats(14)
        assert stats["days"] == 14


class TestRenderWrappedImage:
    def test_renders_a_real_png_file(self, wrapped, tmp_path):
        import storage
        storage.write_memory({"type": "mood", "content": "solid day", "score": 7})
        stats = wrapped.build_wrapped_stats(30)
        out = wrapped.render_wrapped_image(stats, tmp_path / "card.png")
        assert out.exists()
        assert out.stat().st_size > 1000  # a real image, not an empty/corrupt file

    def test_renders_cleanly_with_zero_data(self, wrapped, tmp_path):
        # No entries at all - every field is None/empty; must still
        # render without raising (the CLI's own main() is what refuses
        # to run in this case, not the renderer itself).
        stats = wrapped.build_wrapped_stats(30)
        out = wrapped.render_wrapped_image(stats, tmp_path / "empty.png")
        assert out.exists()

    def test_custom_title_used(self, wrapped, tmp_path):
        import storage
        storage.write_memory({"type": "mood", "content": "day", "score": 5})
        stats = wrapped.build_wrapped_stats(30)
        out = wrapped.render_wrapped_image(stats, tmp_path / "titled.png", title="My Custom Title")
        assert out.exists()

    def test_no_missing_glyph_warnings(self, wrapped, tmp_path):
        """Regression test: badge icons used to be rendered as emoji
        directly in the image, which raised UserWarning for missing
        glyphs on fonts without emoji coverage (and looked broken)."""
        import storage
        storage.write_memory({"type": "workout", "content": "run", "duration_min": 20})
        stats = wrapped.build_wrapped_stats(30)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            out = wrapped.render_wrapped_image(stats, tmp_path / "no-warn.png")
        assert out.exists()

    def test_creates_parent_directories(self, wrapped, tmp_path):
        stats = wrapped.build_wrapped_stats(30)
        nested = tmp_path / "a" / "b" / "c" / "card.png"
        out = wrapped.render_wrapped_image(stats, nested)
        assert out.exists()

    def test_pdf_output_via_file_extension(self, wrapped, tmp_path):
        # matplotlib's savefig() picks the format from the file
        # extension automatically - render_wrapped_image() needs no
        # special-casing for this to work, but it's worth a dedicated
        # regression test since it's an advertised, user-facing feature.
        import storage
        storage.write_memory({"type": "mood", "content": "day", "score": 6})
        stats = wrapped.build_wrapped_stats(30)
        out = wrapped.render_wrapped_image(stats, tmp_path / "card.pdf")
        assert out.exists()
        assert out.read_bytes().startswith(b"%PDF")


class TestMainCli:
    def test_exits_cleanly_with_no_data(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        for mod in ("storage", "analytics", "life_score", "achievements", "wrapped"):
            if mod in sys.modules:
                del sys.modules[mod]
        import wrapped as w
        importlib.reload(w)
        monkeypatch.setattr(sys, "argv", ["wrapped.py", "--out", str(tmp_path / "out.png")])
        with pytest.raises(SystemExit) as exc_info:
            w.main()
        assert exc_info.value.code == 1

    def test_generates_file_with_data(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        for mod in ("storage", "analytics", "life_score", "achievements", "wrapped"):
            if mod in sys.modules:
                del sys.modules[mod]
        import wrapped as w
        importlib.reload(w)
        import storage
        storage.set_active_profile(None)
        storage.write_memory({"type": "mood", "content": "day", "score": 6})

        out_path = tmp_path / "cli-out.png"
        monkeypatch.setattr(sys, "argv", ["wrapped.py", "--out", str(out_path)])
        w.main()
        assert out_path.exists()
