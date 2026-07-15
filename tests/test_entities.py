"""Recurring named entities — CamelCase + acronyms, not note-title fragments."""
from __future__ import annotations

from doing2done.entities import extract


def _note(d, stem, title, body):
    (d / f"{stem}.md").write_text(f'---\ntitle: "{title}"\n---\n\n{body}\n')


def test_camelcase_and_acronyms_across_notes(tmp_path):
    _note(tmp_path, "a-1", "A", "We deployed with ArgoCD to IgniteTech.")
    _note(tmp_path, "b-2", "B", "IgniteTech onboarding and ArgoCD again.")
    ents = extract(str(tmp_path))
    assert set(ents) >= {"IgniteTech", "ArgoCD"}
    assert {t for t, _ in ents["IgniteTech"]} == {"A", "B"}


def test_one_off_mention_is_not_indexed(tmp_path):
    _note(tmp_path, "a-1", "A", "OnlyHere is mentioned once.")
    _note(tmp_path, "b-2", "B", "Something else entirely.")
    assert "OnlyHere" not in extract(str(tmp_path))


def test_plain_title_case_is_ignored(tmp_path):
    """'Daily Focus' etc. are note-title cross-references, not entities."""
    _note(tmp_path, "a-1", "A", "See Daily Focus and Rollover Tasks.")
    _note(tmp_path, "b-2", "B", "More on Daily Focus here.")
    assert "Daily Focus" not in extract(str(tmp_path))
    assert "Daily" not in extract(str(tmp_path))


def test_generic_acronyms_are_filtered(tmp_path):
    _note(tmp_path, "a-1", "A", "Call the API over HTTP, return HTML.")
    _note(tmp_path, "b-2", "B", "The API and HTML again.")
    ents = extract(str(tmp_path))
    assert "API" not in ents and "HTTP" not in ents and "HTML" not in ents


def test_index_is_excluded(tmp_path):
    (tmp_path / "index.md").write_text("IgniteTech IgniteTech")
    _note(tmp_path, "a-1", "A", "IgniteTech here.")
    _note(tmp_path, "b-2", "B", "IgniteTech there.")
    # index.md must not count as one of the notes
    assert all(stem != "index" for _, stem in extract(str(tmp_path))["IgniteTech"])


def test_deduped_within_a_note(tmp_path):
    _note(tmp_path, "a-1", "A", "ISRO ISRO ISRO")
    _note(tmp_path, "b-2", "B", "ISRO")
    assert len(extract(str(tmp_path))["ISRO"]) == 2  # 2 notes, not 4 mentions
