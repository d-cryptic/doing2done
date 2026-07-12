"""Orchestrate ingest: notes -> (OCR) -> classify -> todos + vault markdown."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .classify.classifier import classify_note
from .config import Settings
from .notes.export import list_notes
from .state import State
from .ticktick.client import TickTickClient
from .vault import write_note


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "").replace("&nbsp;", " ").strip()


@dataclass
class IngestReport:
    processed: int = 0
    todos_upserted: int = 0
    notes_written: int = 0
    skipped: int = 0


def run_ingest(
    settings: Settings,
    state: State,
    tt: TickTickClient | None,
    *,
    apply: bool,
) -> IngestReport:
    report = IngestReport()
    for note in list_notes():
        if not state.note_needs_processing(note.id, note.modified):
            report.skipped += 1
            continue

        # TODO(phase-1.1): if note has drawings, OCR the rendered image instead.
        text = _strip_html(note.body_html) or note.name
        result = classify_note(
            text,
            provider=settings.llm_provider,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )

        md_path = None
        if not result.is_todo_only and result.markdown.strip():
            if apply:
                md_path = write_note(result, settings.vault_notes_dir)
            report.notes_written += 1

        for todo in result.todos:
            if apply and tt is not None:
                tt.upsert_task(
                    note.id,
                    todo.title,
                    due_date=todo.due_date,
                    priority=todo.priority,
                    project_id=settings.ticktick_default_project_id or None,
                )
            report.todos_upserted += 1

        if apply:
            state.mark_note(note.id, note.modified, md_path)
        report.processed += 1
    return report
