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
from .state import State, item_key
from .ticktick.client import TickTickClient
from .vault import archive_note, note_stem, write_note

MAX_CHARS = 12000  # cap note text sent to the LLM (token + cost guard)


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "").replace("&nbsp;", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_CHARS]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _persist_diagrams(
    stem: str, items: list[NoteMedia], notes_dir: str, settings: Settings
) -> tuple[str, int]:
    """Vision-caption each render, dedup by content, persist distinct pages only."""
    from difflib import SequenceMatcher

    from .classify.vision import describe_page

    def _norm(d: dict) -> str:
        blob = f"{d.get('transcription', '')} {d.get('caption', '')}".lower()
        return re.sub(r"\s+", " ", blob).strip()

    drawings = [m for m in items if m.png_paths]
    if not drawings:
        return "", 0
    asset_dir = Path(notes_dir) / "assets" / stem
    asset_dir.mkdir(parents=True, exist_ok=True)
    out = ["\n\n## Diagrams\n"]
    kept: list[str] = []
    count = 0
    for m in drawings:
        for src in m.png_paths:
            try:
                desc = describe_page(
                    src,
                    api_key=settings.llm_api_key,
                    model=settings.llm_model,
                    base_url=settings.llm_base_url,
                )
            except Exception:
                desc = {}
            norm = _norm(desc)
            # skip near-duplicate renders of the same page
            if norm and any(SequenceMatcher(None, norm, k).ratio() >= 0.85 for k in kept):
                continue
            kept.append(norm)
            count += 1
            dest = asset_dir / f"diagram-{count}.png"
            shutil.copyfile(src, dest)
            kind = desc.get("kind", "")
            caption = desc.get("caption", "")
            transcription = desc.get("transcription", "")
            label = f"diagram {count}" + (f" \u00b7 {kind}" if kind else "")
            out.append(f"\n![{label}](./assets/{stem}/diagram-{count}.png)\n")
            if caption:
                out.append(f"\n*{caption}*\n")
            if transcription:
                out.append(f"\n> **Transcription:** {transcription}\n")
    return "".join(out), count


@dataclass
class IngestReport:
    processed: int = 0
    todos_upserted: int = 0
    notes_written: int = 0
    diagrams: int = 0
    completed: int = 0
    archived: int = 0
    skipped: int = 0
    errors: int = 0


def run_ingest(
    settings: Settings,
    state: State,
    tt: TickTickClient | None,
    *,
    apply: bool,
    limit: int | None = None,
    force: bool = False,
    media_only: bool = False,
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

    # Resolve a task's project (fallback: scan project data) so we can complete it.
    pid_cache: dict[str, str] = {}
    pid_built = {"done": False}

    def resolve_task_pid(task_id: str, stored_pid: str | None) -> str | None:
        if stored_pid:
            return stored_pid
        if not pid_built["done"] and tt is not None:
            pid_built["done"] = True
            for pid in set(name2id.values()):
                try:
                    for tsk in tt.project_data(pid).get("tasks") or []:
                        pid_cache[tsk["id"]] = pid
                except Exception:
                    pass
        return pid_cache.get(task_id)

    live_ids: set[str] = set()
    for note in list_notes():
        if limit is not None and report.processed >= limit:
            break
        live_ids.add(note.id)

        drawings = media_map.get(note_pk_from_jxa_id(note.id) or -1, [])
        has_media = any(m.png_paths for m in drawings)
        if media_only and not has_media:
            report.skipped += 1
            continue
        if not force and not state.note_needs_processing(note.id, note.modified):
            report.skipped += 1
            continue
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
                        stem, drawings, settings.vault_notes_dir, settings
                    )
                    md_path = write_note(result, settings.vault_notes_dir, diagram_md)
                    report.diagrams += ndraw
                else:
                    report.diagrams += sum(len(m.png_paths) for m in drawings)
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

            # reconcile: todos removed from the note -> complete their tasks
            if apply and tt is not None:
                new_keys = {item_key(note.id, td.title) for td in result.todos}
                for row in state.tasks_for_note(note.id):
                    if row["key"] in new_keys:
                        continue
                    pid = resolve_task_pid(row["task_id"], row["project_id"])
                    if pid:
                        try:
                            tt.complete(pid, row["task_id"])
                        except Exception:
                            pass
                    state.mark_task_completed(row["key"])
                    report.completed += 1

            if apply:
                state.mark_note(note.id, note.modified, md_path)
            report.processed += 1
        except Exception as e:  # one bad note must not abort the run
            report.errors += 1
            print(f"  ! error on '{note.name[:40]}': {type(e).__name__}: {str(e)[:120]}")

    # reconcile: notes deleted in Apple Notes -> complete tasks + archive vault note
    if apply and tt is not None and limit is None:
        for row in state.all_seen_notes():
            if row["note_id"] in live_ids:
                continue
            for trow in state.tasks_for_note(row["note_id"]):
                pid = resolve_task_pid(trow["task_id"], trow["project_id"])
                if pid:
                    try:
                        tt.complete(pid, trow["task_id"])
                    except Exception:
                        pass
                state.mark_task_completed(trow["key"])
                report.completed += 1
            if row["md_path"]:
                try:
                    archive_note(
                        row["md_path"], settings.vault_dir, settings.vault_notes_dir
                    )
                    report.archived += 1
                except Exception:
                    pass
            state.forget_note(row["note_id"])

    return report
