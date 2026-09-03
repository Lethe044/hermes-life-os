"""Tests for demo/life_review.py. build_life_review_data() is
pure-data and tested without matplotlib; render_html()/main() exercise
real (fast, headless) matplotlib rendering to catch actual failures,
not just logic bugs."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))

matplotlib = pytest.importorskip("matplotlib")


@pytest.fixture()
def life_review(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "analytics", "patterns", "life_score", "achievements",
                "dashboard", "life_review"):
        if mod in sys.modules:
            del sys.modules[mod]
    import life_review as lr
    importlib.reload(lr)
    import storage
    storage.set_active_profile(None)
    return lr


class TestPeriodLabel:
    @pytest.mark.parametrize("days,expected", [
        (7, "Month"), (35, "Month"),
        (36, "Quarter"), (90, "Quarter"), (100, "Quarter"),
        (101, "Year"), (365, "Year"),
    ])
    def test_period_labels(self, life_review, days, expected):
        assert life_review._period_label(days) == expected


class TestBuildLifeReviewData:
    def test_no_data_returns_zeroed_structure(self, life_review):
        data = life_review.build_life_review_data(90)
        assert data["entry_count"] == 0
        assert data["avg_life_score"] is None
        assert data["best_day"] is None
        assert data["worst_day"] is None
        assert data["earned_badges"] == []

    def test_with_data_populates_fields(self, life_review):
        import storage
        storage.write_memory({"type": "mood", "content": "good day", "score": 8})
        storage.write_memory({"type": "workout", "content": "run", "duration_min": 30})
        data = life_review.build_life_review_data(90)
        assert data["entry_count"] == 2
        assert data["avg_life_score"] is not None
        assert data["best_day"] is not None
        assert any(b["id"] == "count-workout-1" for b in data["earned_badges"])

    def test_compare_days_defaults_to_days(self, life_review):
        data = life_review.build_life_review_data(60)
        assert data["compare_days"] == 60

    def test_compare_days_overridable(self, life_review):
        data = life_review.build_life_review_data(90, compare_days=30)
        assert data["compare_days"] == 30
        assert data["days"] == 90

    def test_period_label_included(self, life_review):
        data = life_review.build_life_review_data(365)
        assert data["period_label"] == "Year"


class TestRenderHtml:
    def test_renders_valid_html_with_no_data(self, life_review):
        data = life_review.build_life_review_data(90)
        html = life_review.render_html(data)
        assert html.startswith("<!DOCTYPE html>")
        assert "Life Review" in html or "with Hermes" in html
        assert "N/A" in html  # no life score yet

    def test_renders_with_data_including_chart(self, life_review):
        import storage
        for score in (5, 6, 7, 8):
            storage.write_memory({"type": "mood", "content": "day", "score": score})
        data = life_review.build_life_review_data(90)
        html = life_review.render_html(data)
        assert "<!DOCTYPE html>" in html
        # a real avg score should appear, not the N/A placeholder
        assert str(data["avg_life_score"]) in html

    def test_no_missing_glyph_warnings(self, life_review):
        import storage, warnings
        storage.write_memory({"type": "mood", "content": "day", "score": 7})
        data = life_review.build_life_review_data(90)
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            html = life_review.render_html(data)
        assert html


class TestRenderPdf:
    def test_renders_a_real_pdf_with_no_data(self, life_review, tmp_path):
        data = life_review.build_life_review_data(90)
        out = life_review.render_pdf(data, tmp_path / "review.pdf")
        assert out.exists()
        assert out.read_bytes().startswith(b"%PDF")

    def test_renders_with_data(self, life_review, tmp_path):
        import storage
        for score in (5, 6, 7, 8):
            storage.write_memory({"type": "mood", "content": "day", "score": score})
        storage.write_memory({"type": "workout", "content": "run", "duration_min": 30})
        data = life_review.build_life_review_data(90)
        out = life_review.render_pdf(data, tmp_path / "review.pdf")
        assert out.exists()
        assert out.stat().st_size > 2000  # a real multi-page PDF, not an empty/corrupt file

    def test_creates_parent_directories(self, life_review, tmp_path):
        data = life_review.build_life_review_data(90)
        nested = tmp_path / "a" / "b" / "review.pdf"
        out = life_review.render_pdf(data, nested)
        assert out.exists()

    def test_no_missing_glyph_warnings(self, life_review, tmp_path):
        import storage, warnings
        storage.write_memory({"type": "workout", "content": "run", "duration_min": 20})
        data = life_review.build_life_review_data(90)
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            out = life_review.render_pdf(data, tmp_path / "review.pdf")
        assert out.exists()

    def test_handles_long_correlation_text_without_raising(self, life_review, tmp_path):
        # format_correlation_insights() strings can be long - render_pdf()
        # truncates via textwrap.shorten() rather than overflowing the page.
        data = life_review.build_life_review_data(90)
        data["insights"] = ["This is a very long correlation insight string " * 5]
        out = life_review.render_pdf(data, tmp_path / "review.pdf")
        assert out.exists()


class TestMainCli:
    def test_generates_file_with_no_data(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        for mod in ("storage", "analytics", "patterns", "life_score", "achievements",
                    "dashboard", "life_review"):
            if mod in sys.modules:
                del sys.modules[mod]
        import life_review as lr
        importlib.reload(lr)

        out_path = tmp_path / "review.html"
        monkeypatch.setattr(sys, "argv", ["life_review.py", "--out", str(out_path), "--no-open"])
        lr.main()
        assert out_path.exists()
        assert "<!DOCTYPE html>" in out_path.read_text(encoding="utf-8")

    def test_no_open_does_not_call_webbrowser(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        for mod in ("storage", "analytics", "patterns", "life_score", "achievements",
                    "dashboard", "life_review"):
            if mod in sys.modules:
                del sys.modules[mod]
        import life_review as lr
        importlib.reload(lr)

        out_path = tmp_path / "review2.html"
        monkeypatch.setattr(sys, "argv", ["life_review.py", "--out", str(out_path), "--no-open"])
        with pytest.MonkeyPatch.context() as mp:
            called = []
            mp.setattr(lr.webbrowser, "open", lambda *a, **k: called.append(a))
            lr.main()
        assert called == []

    def test_format_pdf_generates_a_pdf(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        for mod in ("storage", "analytics", "patterns", "life_score", "achievements",
                    "dashboard", "life_review"):
            if mod in sys.modules:
                del sys.modules[mod]
        import life_review as lr
        importlib.reload(lr)

        out_path = tmp_path / "review.pdf"
        monkeypatch.setattr(sys, "argv", ["life_review.py", "--format", "pdf",
                                           "--out", str(out_path), "--no-open"])
        lr.main()
        assert out_path.exists()
        assert out_path.read_bytes().startswith(b"%PDF")

    def test_default_out_path_matches_format(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.chdir(tmp_path)
        for mod in ("storage", "analytics", "patterns", "life_score", "achievements",
                    "dashboard", "life_review"):
            if mod in sys.modules:
                del sys.modules[mod]
        import life_review as lr
        importlib.reload(lr)

        monkeypatch.setattr(sys, "argv", ["life_review.py", "--format", "pdf", "--no-open"])
        lr.main()
        assert (tmp_path / "hermes-life-review.pdf").exists()
