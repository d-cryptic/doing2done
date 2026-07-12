"""Orchestrate ingest: notes -> (OCR) -> classify -> routed todos + vault + diagrams."""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .classify.classifier import classify_note
from .config import Settings
from .notes.export import list_notes
from .notes.media import NoteMedia, media_by_note, note_pk_from_jxa_id
from .state import State
from .ticktick.client import TickTickClient
from .vault import note_stem, write_note

MAX_CHARS = 12000  # cap note text sent to the LLM (token + cost guard)


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "").replace("&nbsp;", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_CHARS]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _persist_diagrams(stem: str, items: list[NoteMedia], notes_dir: str) -> tuple[str, int]:
    from .notes.ocr import recognize  # lazy: needs the 'ocr' extra

    drawings = [m for m in items if m.png_path]
    if not drawings:
        return "", 0
    asset_dir = Path(notes_dir) / "assets" / stem
    asset_dir.mkdir(parents=True, exist_ok=True)
    out = ["\n\n## Diagrams\n"]
    for i, m in enumerate(drawings, 1):
        dest = asset_dir / f"diagram-{i}.png"
        shutil.copyfile(m.png_path, dest)
        out.append(f"\n![diagram {i}](./assets/{stem}/diagram-{i}.png)\n")
        try:
            txt = recognize(dest).strip()
            if txt:
                out.append(f"\n> **OCR {i}:** {txt}\n")
        except Exception:
            pass
    return "".join(out), len(drawings)


@dataclass
class IngestReport:
    processed: int = 0
    todos_upserted: int = 0
    notes_written: int = 0
    diagrams: int = 0
    skipped: int = 0
    errors: int = 0


def run_ingest(
    settings: Settings,
    state: State,
    tt: TickTickClient | None,
    *,
    apply: bool,
    limit: int | None = None,
) -> IngestReport:
    report = IngestReport()
    media_map = media_by_note()

    # Build routing table from the user's existing TickTick lists.
    name2id: dict[str, str] = {}
    norm2id: dict[str, str] = {}
    project_names: list[str] | None = None
    if tt is not None:
        for p in tt.projects():
            name2id[p["name"]] = p["id"]
            norm2id[_norm(p["name"])] = p["id"]
        project_names = list(name2id)

    def resolve_pid(proj: str | None) -> str | None:
        default = settings.ticktick_default_project_id or None
        if not proj:
            return default
        if proj in name2id:
            return name2id[proj]
        n = _norm(proj)
        if n in norm2id:
            return norm2id[n]
        for k, v in norm2id.items():
            if n and (n in k or k in n):
                return v
        return default

    for note in list_notes():
        if limit is not None and report.processed >= limit:
            break
        if not state.note_needs_processing(note.id, note.modified):
            report.skipped += 1
            continue

        drawings = media_map.get(note_pk_from_jxa_id(note.id) or -1, [])
        has_media = any(m.png_path for m in drawings)
        text = _strip_html(note.body_html)
        if len(text) < 3 and not has_media:
            if apply:
                state.mark_note(note.id, note.modified, None)
            report.skipped += 1
            continue

        try:
            result = classify_note(
                text or note.name,
                provider=settings.llm_provider,
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                base_url=settings.llm_base_url,
                projects=project_names,
            )

            md_path = None
            if not result.is_todo_only or has_media:
                if apply:
                    stem = note_stem(result)
                    diagram_md, ndraw = _persist_diagrams(
                        stem, drawings, settings.vault_notes_dir
                    )
                    md_path = write_note(result, settings.vault_notes_dir, diagram_md)
                    report.diagrams += ndraw
                else:
                    report.diagrams += sum(1 for m in drawings if m.png_path)
                report.notes_written += 1

            for todo in result.todos:
                if apply and tt is not None:
                    tt.upsert_task(
                        note.id,
                        todo.title,
                        due_date=todo.due_date,
                        priority=todo.priority,
                        project_id=resolve_pid(todo.project),
                    )
                report.todos_upserted += 1

            if apply:
                state.mark_note(note.id, note.modified, md_path)
            report.processed += 1
        except Exception as e:  # one bad note must not abort the run
            report.errors += 1
            print(f"  ! error on '{note.name[:40]}': {type(e).__name__}: {str(e)[:120]}")

    return report
