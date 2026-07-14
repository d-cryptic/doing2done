"""Orchestration tests — the dedup / watermark / reconciliation logic that guards TickTick.

Uses the real Markdown provider + real State, with the notes reader and LLM stubbed,
so the actual pipeline flow is exercised (not mocks asserting on mocks).
"""
from pathlib import Path

import pytest

from doing2done import pipeline
from doing2done.classify.models import NoteResult, Todo
from doing2done.config import Settings
from doing2done.notes.export import RawNote
from doing2done.providers.markdown import MarkdownProvider
from doing2done.state import State
from doing2done.todo import TodoService

NID = "x-coredata://STORE/ICNote/p1"


def _settings(tmp_path) -> Settings:
    return Settings(
        state_db=str(tmp_path / "s.db"),
        vault_dir=str(tmp_path / "vault"),
        vault_notes_dir=str(tmp_path / "vault" / "docs" / "notes"),
        todo_provider="markdown",
        todo_file=str(tmp_path / "todos.md"),
        llm_api_key="stub",
    )


def _note(body="ship the api", modified="2026-07-14T10:00:00", nid=NID, name="Work note"):
    return RawNote(id=nid, name=name, modified=modified, body_html=body, folder="Notes")


def _result(todos, markdown="Some prose worth keeping.", title="Work Note"):
    return NoteResult(
        title=title, date="2026-07-14", tags=["work"], markdown=markdown,
        todos=[Todo(title=t) for t in todos], is_todo_only=False,
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Wire the pipeline with stubbed notes+LLM but real state/provider/vault."""
    s = _settings(tmp_path)
    state = State(s.state_db)
    svc = TodoService(MarkdownProvider(s.todo_file), state, "")
    notes = [_note()]
    result = {"value": _result(["Ship the API", "Review PRs"])}

    monkeypatch.setattr(pipeline._store, "list_notes", lambda: list(notes))
    monkeypatch.setattr(pipeline, "media_by_note", lambda: {})
    monkeypatch.setattr(pipeline, "classify_note", lambda *a, **k: result["value"])
    return {"s": s, "state": state, "svc": svc, "notes": notes, "result": result}


def test_ingest_creates_todos_and_vault_note(env):
    rep = pipeline.run_ingest(env["s"], env["state"], env["svc"], apply=True)
    assert rep.processed == 1
    assert rep.todos_upserted == 2
    titles = [t.title for t in env["svc"].p.open_tasks("Inbox")]
    assert "Ship the API" in titles and "Review PRs" in titles
    assert list(Path(env["s"].vault_notes_dir).glob("*.md")), "vault note should be written"


def test_watermark_skips_unchanged_note(env):
    pipeline.run_ingest(env["s"], env["state"], env["svc"], apply=True)
    rep = pipeline.run_ingest(env["s"], env["state"], env["svc"], apply=True)
    assert rep.processed == 0 and rep.skipped == 1, "unchanged note must not reprocess"


def test_reprocess_does_not_duplicate_todos(env):
    pipeline.run_ingest(env["s"], env["state"], env["svc"], apply=True)
    pipeline.run_ingest(env["s"], env["state"], env["svc"], apply=True, force=True)
    assert len(env["svc"].p.open_tasks("Inbox")) == 2, "dedup must prevent duplicates"


def test_removed_todo_is_completed(env):
    pipeline.run_ingest(env["s"], env["state"], env["svc"], apply=True)
    # the note now only mentions one of the two todos
    env["result"]["value"] = _result(["Ship the API"])
    pipeline.run_ingest(env["s"], env["state"], env["svc"], apply=True, force=True)
    open_titles = [t.title for t in env["svc"].p.open_tasks("Inbox")]
    assert "Ship the API" in open_titles
    assert "Review PRs" not in open_titles, "todo removed from the note must be completed"


def test_deleted_note_completes_tasks_and_archives(env):
    pipeline.run_ingest(env["s"], env["state"], env["svc"], apply=True)
    env["notes"].clear()  # note deleted in Apple Notes
    rep = pipeline.run_ingest(env["s"], env["state"], env["svc"], apply=True)
    assert env["svc"].p.open_tasks("Inbox") == [], "deleted note's tasks must be completed"
    assert rep.archived == 1
    archived = list((Path(env["s"].vault_dir) / "archive" / "notes").glob("*.md"))
    assert archived, "deleted note should be archived, not lost"


def test_dry_run_writes_nothing(env):
    rep = pipeline.run_ingest(env["s"], env["state"], env["svc"], apply=False)
    assert rep.processed == 1 and rep.todos_upserted == 2  # reported...
    assert env["svc"].p.open_tasks("Inbox") == [], "...but nothing actually created"
    assert not list(Path(env["s"].vault_notes_dir).glob("*.md"))
