"""A handwritten note's searchable content is its transcription, not its raw body."""
from __future__ import annotations

from doing2done.push_payload import payload_for


class _Note:
    def __init__(self, body="", name="Raw Name"):
        self.id = "n1"
        self.name = name
        self.body_html = body
        self.modified = "2026-07-15T00:00:00"


class _State:
    def __init__(self, path=None):
        self._p = path

    def get_md_path(self, _note_id):
        return self._p


def test_handwritten_note_indexes_its_transcription(tmp_path):
    """The bug: raw body is one placeholder char, so it embedded as nothing."""
    md = tmp_path / "n.md"
    md.write_text(
        '---\ntitle: "Project Tasks and Personal Goals"\n---\n\n'
        "> **TL;DR** work and personal goals\n\n> **Transcription:** Respan PRS, Azure migration\n"
    )
    item = payload_for(_Note(body="￼"), _State(str(md)))
    assert "Respan PRS" in item["body"], "the transcription must be what gets embedded"
    assert item["title"] == "Project Tasks and Personal Goals"


def test_uses_the_readable_title_not_the_raw_one(tmp_path):
    md = tmp_path / "n.md"
    md.write_text('---\ntitle: "Kubernetes Concepts"\n---\n\nbody\n')
    assert payload_for(_Note(name="#Tasks"), _State(str(md)))["title"] == "Kubernetes Concepts"


def test_frontmatter_is_not_embedded(tmp_path):
    md = tmp_path / "n.md"
    md.write_text('---\ntitle: "T"\ndate: "2026-01-01"\ntags: ["a"]\n---\n\nreal body\n')
    body = payload_for(_Note(), _State(str(md)))["body"]
    assert body == "real body"


def test_tag_chips_are_not_embedded(tmp_path):
    """Chips are navigation; embedding them pollutes the vector."""
    md = tmp_path / "n.md"
    md.write_text(
        '---\ntitle: "T"\n---\n\nreal body\n\n<div class="v-note-tags"><a>k8s</a></div>\n'
    )
    assert "v-note-tags" not in payload_for(_Note(), _State(str(md)))["body"]


def test_todo_only_note_falls_back_to_raw(tmp_path):
    """Notes with no vault file still need to be searchable."""
    item = payload_for(_Note(body="buy milk", name="Errands"), _State(None))
    assert item["body"] == "buy milk" and item["title"] == "Errands"


def test_empty_vault_file_falls_back_to_raw(tmp_path):
    md = tmp_path / "n.md"
    md.write_text('---\ntitle: "T"\n---\n\n')
    assert payload_for(_Note(body="raw text"), _State(str(md)))["body"] == "raw text"


def test_body_is_capped(tmp_path):
    md = tmp_path / "n.md"
    md.write_text('---\ntitle: "T"\n---\n\n' + "x" * 20000)
    assert len(payload_for(_Note(), _State(str(md)))["body"]) == 8000
