"""Tapping Daily should answer 'what am I doing today', not describe the feature."""
from __future__ import annotations

from pathlib import Path

from doing2done.reports import generate_daily_index, generate_weekly_index


def _daily(tmp_path, day, focus):
    d = tmp_path / "daily"
    d.mkdir(exist_ok=True)
    (d / f"{day}.md").write_text(
        f"---\ntitle: 'Daily — {day}'\n---\n\n# Daily — {day}\n\n## Focus\n- [ ] {focus}\n"
    )


def test_latest_brief_is_inlined(tmp_path):
    _daily(tmp_path, "2026-07-14", "old thing")
    _daily(tmp_path, "2026-07-15", "today thing")
    body = Path(generate_daily_index(str(tmp_path))).read_text()
    assert "today thing" in body, "the landing page must show today's brief"
    assert "Daily — 2026-07-15" in body


def test_earlier_days_are_listed_not_inlined(tmp_path):
    _daily(tmp_path, "2026-07-14", "old thing")
    _daily(tmp_path, "2026-07-15", "today thing")
    body = Path(generate_daily_index(str(tmp_path))).read_text()
    assert "old thing" not in body, "only today's brief should be inline"
    assert 'href="./2026-07-14"' in body


def test_frontmatter_is_stripped(tmp_path):
    _daily(tmp_path, "2026-07-15", "x")
    body = Path(generate_daily_index(str(tmp_path))).read_text()
    assert "title: 'Daily" not in body


def test_no_briefs_yet(tmp_path):
    (tmp_path / "daily").mkdir()
    body = Path(generate_daily_index(str(tmp_path))).read_text()
    assert "No daily brief yet" in body


def test_missing_dir_is_a_noop(tmp_path):
    assert generate_daily_index(str(tmp_path)) == ""


def test_weekly_index_inlines_the_latest_review(tmp_path):
    """d2d weekly wrote these all along and nothing ever linked to them."""
    d = tmp_path / "weekly"
    d.mkdir()
    (d / "2026-07-08.md").write_text(
        "---\ntitle: 'W'\n---\n\n# Weekly — 2026-07-08\n\nold review\n"
    )
    (d / "2026-07-15.md").write_text(
        "---\ntitle: 'W'\n---\n\n# Weekly — 2026-07-15\n\nthis week\n"
    )
    body = Path(generate_weekly_index(str(tmp_path))).read_text()
    assert "this week" in body
    assert "old review" not in body, "only the latest belongs inline"
    assert 'href="./2026-07-08"' in body


def test_weekly_and_daily_do_not_collide(tmp_path):
    """They share a generator; each must write into its own directory."""
    for sub, txt in (("daily", "todays brief"), ("weekly", "the review")):
        d = tmp_path / sub
        d.mkdir()
        (d / "2026-07-15.md").write_text(f"---\ntitle: 'x'\n---\n\n{txt}\n")
    assert "todays brief" in Path(generate_daily_index(str(tmp_path))).read_text()
    assert "the review" in Path(generate_weekly_index(str(tmp_path))).read_text()


def test_no_weekly_dir_is_a_noop(tmp_path):
    assert generate_weekly_index(str(tmp_path)) == ""
