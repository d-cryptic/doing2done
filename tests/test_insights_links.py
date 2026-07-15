"""The insight report cites notes as evidence — those citations must be walkable."""
from __future__ import annotations

from doing2done.reports import linkify_titles


def _vault(tmp_path, titles):
    for i, t in enumerate(titles):
        (tmp_path / f"note-{i}-abc{i}.md").write_text(f'---\ntitle: "{t}"\n---\n\nbody\n')
    return str(tmp_path)


def test_links_a_quoted_title(tmp_path):
    v = _vault(tmp_path, ["Hackathon Tracker"])
    out = linkify_titles('Notes like "Hackathon Tracker" show this.', v)
    assert '"[Hackathon Tracker](./notes/note-0-abc0)"' in out


def test_longest_title_wins(tmp_path):
    """A short title must not shadow the longer one it's a prefix of.

    The closing quote is what guarantees this, not the sort order — verified by
    reversing the sort and watching this still pass.
    """
    v = _vault(tmp_path, ["Hackathon", "Hackathon Brainstorm and Learning Plan"])
    out = linkify_titles('see "Hackathon Brainstorm and Learning Plan" today', v)
    assert "note-1-abc1" in out
    assert "note-0-abc0" not in out, "the short title shadowed the long one"


def test_unknown_title_is_left_alone(tmp_path):
    """A near-miss must stay text, not point at the wrong note."""
    v = _vault(tmp_path, ["Hackathon Tracker"])
    out = linkify_titles('Notes like "Some Other Note" show this.', v)
    assert "](./notes/" not in out


def test_unquoted_mentions_are_not_linked(tmp_path):
    """Only the model's own citation quotes become links — prose stays prose."""
    v = _vault(tmp_path, ["Hackathon Tracker"])
    assert "](./notes/" not in linkify_titles("Hackathon Tracker came up a lot.", v)


def test_case_insensitive(tmp_path):
    v = _vault(tmp_path, ["Hackathon Tracker"])
    assert "](./notes/note-0-abc0)" in linkify_titles('"hackathon tracker" again', v)


def test_empty_vault_is_a_noop(tmp_path):
    assert linkify_titles('"anything"', str(tmp_path)) == '"anything"'
