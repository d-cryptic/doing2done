from doing2done.classify.models import NoteResult
from doing2done.vault import slugify, write_note


def test_slugify():
    assert slugify("Meeting Notes: Q3!") == "meeting-notes-q3"


def test_write_note(tmp_path):
    r = NoteResult(title="Hello World", date="2026-07-12", tags=["a", "b"], markdown="# Hi")
    p = write_note(r, str(tmp_path))
    assert p.endswith("2026-07-12-hello-world.md")
    txt = open(p).read()
    assert "title: Hello World" in txt and "tags: [a, b]" in txt and "# Hi" in txt
