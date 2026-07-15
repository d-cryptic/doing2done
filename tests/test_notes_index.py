"""The notes index should list the notes, not describe itself."""
from __future__ import annotations

from pathlib import Path

from doing2done.reports import generate_notes_index


def _note(d, stem, title, date, summary="", drawn=False):
    body = f'---\ntitle: "{title}"\ndate: "{date}"\n---\n\n'
    if summary:
        body += f"> **TL;DR** {summary}\n\n"
    body += "text\n"
    if drawn:
        body += "\n## Diagrams\n\n![d](./assets/x/diagram-1.png)\n"
    (d / f"{stem}.md").write_text(body)


def test_lists_every_note(tmp_path):
    _note(tmp_path, "a-1", "Alpha", "2026-01-01")
    _note(tmp_path, "b-2", "Beta", "2026-02-01")
    body = Path(generate_notes_index(str(tmp_path))).read_text()
    assert "2 notes" in body
    assert 'href="./a-1"' in body and 'href="./b-2"' in body


def test_newest_first(tmp_path):
    _note(tmp_path, "old-1", "Old", "2020-01-01")
    _note(tmp_path, "new-2", "New", "2026-02-01")
    body = Path(generate_notes_index(str(tmp_path))).read_text()
    assert body.index("New") < body.index("Old")


def test_marks_handwritten_notes(tmp_path):
    _note(tmp_path, "typed-1", "Typed", "2026-01-01")
    _note(tmp_path, "drawn-2", "Drawn", "2026-01-02", drawn=True)
    body = Path(generate_notes_index(str(tmp_path))).read_text()
    assert "1 are handwritten" in body
    assert body.count("v-pen") == 1


def test_shows_the_summary(tmp_path):
    _note(tmp_path, "a-1", "Alpha", "2026-01-01", summary="what it says")
    assert "what it says" in Path(generate_notes_index(str(tmp_path))).read_text()


def test_titles_are_escaped(tmp_path):
    _note(tmp_path, "a-1", "<script>x</script>", "2026-01-01")
    body = Path(generate_notes_index(str(tmp_path))).read_text()
    assert "<script>" not in body and "&lt;script&gt;" in body


def test_index_is_not_listed_in_itself(tmp_path):
    _note(tmp_path, "a-1", "Alpha", "2026-01-01")
    generate_notes_index(str(tmp_path))
    body = Path(generate_notes_index(str(tmp_path))).read_text()  # run twice
    assert "1 notes" in body, "the index must not list itself on a second run"
