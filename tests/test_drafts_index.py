"""d2d draft publishes drafts; nothing linked to them."""
from __future__ import annotations

from pathlib import Path

from doing2done.reports import generate_drafts_index


def _vault(tmp_path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "drafts").mkdir()
    return tmp_path / "notes"


def test_lists_every_draft(tmp_path):
    notes = _vault(tmp_path)
    (tmp_path / "drafts" / "tweet-kubernetes.md").write_text("x")
    (tmp_path / "drafts" / "blog-clickhouse.md").write_text("x")
    body = Path(generate_drafts_index(str(notes))).read_text()
    assert "2 draft(s)" in body
    assert 'href="./tweet-kubernetes"' in body and 'href="./blog-clickhouse"' in body


def test_shows_kind_and_readable_title(tmp_path):
    notes = _vault(tmp_path)
    (tmp_path / "drafts" / "tweet-clickhouse-and-database-learnings.md").write_text("x")
    body = Path(generate_drafts_index(str(notes))).read_text()
    assert "<b>clickhouse and database learnings</b>" in body
    assert "<time>tweet</time>" in body


def test_empty_drafts_dir(tmp_path):
    notes = _vault(tmp_path)
    assert "Nothing drafted yet" in Path(generate_drafts_index(str(notes))).read_text()


def test_index_does_not_list_itself(tmp_path):
    notes = _vault(tmp_path)
    (tmp_path / "drafts" / "tweet-x.md").write_text("x")
    generate_drafts_index(str(notes))
    body = Path(generate_drafts_index(str(notes))).read_text()
    assert "1 draft(s)" in body


def test_titles_are_escaped(tmp_path):
    notes = _vault(tmp_path)
    (tmp_path / "drafts" / "tweet-<script>.md").write_text("x")
    assert "<script>" not in Path(generate_drafts_index(str(notes))).read_text()


def test_no_drafts_dir_is_a_noop(tmp_path):
    (tmp_path / "notes").mkdir()
    assert generate_drafts_index(str(tmp_path / "notes")) == ""
