"""A note with no date in its text still needs a real date — from Apple Notes."""
from __future__ import annotations

from doing2done.classify.models import NoteResult
from doing2done.vault import note_date, note_stem, write_note


def _result(date: str = "") -> NoteResult:
    return NoteResult(title="Kubernetes concepts", date=date, tags=["k8s"], markdown="body")


def test_uses_the_notes_own_timestamp_when_the_classifier_finds_no_date():
    assert note_date(_result(""), "2026-06-01T09:30:00") == "2026-06-01"


def test_the_notes_own_timestamp_beats_the_classifiers_reading():
    """The note's date must not move when the pipeline re-runs.

    The classifier resolves relative dates against the run date, so a note reading
    "Date: Today" gets re-dated on every ingest — the timeline reshuffled under us.
    Apple Notes' own timestamp is the only stable answer to "when was this written".
    """
    assert note_date(_result("2026-05-02"), "2026-06-01T09:30:00") == "2026-06-01"


def test_classifier_date_is_the_last_resort():
    """Still better than dateless when Apple Notes gives us nothing."""
    assert note_date(_result("2026-05-02"), "") == "2026-05-02"


def test_no_date_anywhere_stays_empty():
    assert note_date(_result(""), "") == ""


def test_written_frontmatter_carries_the_fallback_date(tmp_path):
    p = write_note(_result(""), str(tmp_path), note_id="n1", fallback_date="2026-06-01T09:30:00")
    assert 'date: "2026-06-01"' in open(p).read()


def test_stem_is_date_prefixed_via_fallback():
    assert note_stem(_result(""), "n1", "2026-06-01T09:30:00").startswith("2026-06-01-")
