"""A note should show its topics and let you walk to neighbours by tag."""
from __future__ import annotations

from doing2done.classify.models import NoteResult
from doing2done.vault import render_tag_chips, write_note


def test_renders_a_chip_per_tag():
    html = render_tag_chips(["k8s", "devops"])
    assert html.count("v-chip") == 2
    assert ">k8s<" in html and ">devops<" in html


def test_links_to_the_tag_index_anchor():
    assert 'href="../tags#open-source"' in render_tag_chips(["open source"])


def test_no_tags_adds_nothing():
    assert render_tag_chips([]) == ""


def test_tag_text_is_escaped():
    """A tag is model output; it must not become markup on the page."""
    html = render_tag_chips(["<script>x</script>"])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_written_note_carries_its_chips(tmp_path):
    r = NoteResult(title="T", date="2026-01-01", tags=["k8s"], markdown="body")
    p = write_note(r, str(tmp_path), note_id="n1")
    body = open(p).read()
    assert "v-note-tags" in body and ">k8s<" in body


def test_untagged_note_has_no_empty_container(tmp_path):
    r = NoteResult(title="T", date="2026-01-01", tags=[], markdown="body")
    assert "v-note-tags" not in open(write_note(r, str(tmp_path), note_id="n2")).read()
