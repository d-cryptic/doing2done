"""Orphan detection must never touch a note's live file."""
from __future__ import annotations

import hashlib

from doing2done.vault import find_orphans


def _h(note_id: str) -> str:
    return hashlib.sha1(note_id.encode()).hexdigest()[:6]


def test_finds_the_stale_rename(tmp_path):
    live = tmp_path / f"2026-07-13-new-title-{_h('n1')}.md"
    stale = tmp_path / f"old-title-{_h('n1')}.md"
    live.write_text("x")
    stale.write_text("x")
    assert find_orphans(str(tmp_path), {str(live)}, ["n1"]) == [str(stale)]


def test_never_removes_a_live_path_even_on_hash_collision(tmp_path):
    """Two notes whose ids collide in 6 hex chars must both keep their files."""
    a = tmp_path / f"note-a-{_h('n1')}.md"
    b = tmp_path / f"note-b-{_h('n1')}.md"   # same hash, both live
    a.write_text("x")
    b.write_text("x")
    assert find_orphans(str(tmp_path), {str(a), str(b)}, ["n1"]) == []


def test_ignores_files_from_unknown_notes(tmp_path):
    """A file whose hash matches no known note is not ours to delete."""
    (tmp_path / "something-else-abcdef.md").write_text("x")
    assert find_orphans(str(tmp_path), set(), ["n1"]) == []


def test_ignores_index_and_unhashed_files(tmp_path):
    (tmp_path / "index.md").write_text("x")
    (tmp_path / "handwritten.md").write_text("x")
    assert find_orphans(str(tmp_path), set(), ["n1"]) == []


def test_clean_vault_yields_nothing(tmp_path):
    live = tmp_path / f"only-{_h('n1')}.md"
    live.write_text("x")
    assert find_orphans(str(tmp_path), {str(live)}, ["n1"]) == []
