"""The README, changelog and community files stay consistent."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _text(name):
    return (ROOT / name).read_text(encoding="utf-8")


def _slug(heading):
    s = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return s.replace(" ", "-")


def _headings(md):
    out, fenced = [], False
    for line in md.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and re.match(r"#{1,6} ", line):
            out.append(line.lstrip("#").strip())
    return out


def test_readme_anchor_links_resolve():
    md = _text("README.md")
    slugs = {_slug(h) for h in _headings(md)}
    missing = sorted({a for a in re.findall(r"\]\(#([^)]+)\)", md) if a not in slugs})
    assert missing == []


def test_readme_local_links_and_images_exist():
    md = _text("README.md")
    for target in re.findall(r"\]\(((?!https?:|#|mailto:)[^)\s]+)\)", md) + re.findall(r'src="((?!https?:)[^"]+)"', md):
        assert (ROOT / target.split("#")[0]).exists(), target


def test_readme_keeps_its_diagram_and_balanced_fences():
    md = _text("README.md")
    assert md.count("```mermaid") == 3
    assert md.count("```") % 2 == 0


def test_changelog_has_every_recent_release_once():
    log = _text("CHANGELOG.md")
    for v in ("1.49.0", "1.48.0", "1.47.0", "1.46.1", "1.46.0", "1.45.0"):
        assert len(re.findall(rf"^\*\*v{re.escape(v)} - ", log, re.M)) == 1
    assert re.search(r"^\*\*v1\.49\.0 - ", _text("README.md"), re.M)


def test_version_matches_the_newest_changelog_entry():
    version = re.search(r'^version = "([^"]+)"', _text("pyproject.toml"), re.M).group(1)
    newest = re.search(r"^\*\*v(\d+\.\d+\.\d+) - ", _text("CHANGELOG.md"), re.M).group(1)
    assert version == newest


def test_community_files_exist():
    for name in ("SECURITY.md", "CONTRIBUTING.md", "LICENSE", ".github/pull_request_template.md",
                 "docs/images/social-preview.png", "docs/images/demo.svg"):
        assert (ROOT / name).exists(), name


def test_readme_tool_count_matches_the_tool_reference():
    total = re.search(r"\((\d+) in total\)", _text("docs/TOOLS.md")).group(1)
    assert f"All {total} tools are listed" in _text("README.md")
