"""Orchestrate ingest: notes -> (OCR) -> classify -> routed todos + vault + diagrams."""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .classify.classifier import classify_note
from .config import Settings
from .notes import export as _export
from .notes import store as _store
from .notes.media import NoteMedia, media_by_note, note_pk_from_jxa_id
from .notify import notify
from .providers.base import TaskDraft
from .state import State, item_key
from .todo import TodoService
from .vault import archive_note, note_stem, write_note

MAX_CHARS = 12000  # cap note text sent to the LLM (token + cost guard)
# A note whose image we can't read is left unprocessed so the next run retries it.
# Without a cap, an image that never reads costs a vision call every sync, forever.
MAX_VISION_RETRIES = 3


def _strip_html(html: str) -> str:
    """HTML/plain note body -> clean text the LLM can reason over."""
    import html as _html

    text = re.sub(r"<[^>]+>", " ", html or "")
    text = _html.unescape(text)          # &amp; &lt; &nbsp; ...
    text = text.replace("\ufffc", " ")   # attachment placeholders (images/drawings)
    text = re.sub(r"[\u200b-\u200d\ufeff]", "", text)  # zero-width noise
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)  # keep paragraph structure, drop runs
    return text.strip()[:MAX_CHARS]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _describe_diagrams(
    items: list[NoteMedia], settings: Settings
) -> tuple[list[dict], int]:
    """Vision-describe each distinct diagram page once (transcription + caption).

    Returns (descriptions, failures). The failure count matters: a handwritten note's
    entire content lives in its image, so a transient vision error is NOT the same as
    "this image has no text" — conflating them writes a note that says the page is
    empty and watermarks it, losing the page for good.
    """
    import hashlib
    from difflib import SequenceMatcher

    from .classify.vision import describe_page

    def _norm(d: dict) -> str:
        blob = f"{d.get('transcription', '')} {d.get('caption', '')}".lower()
        return re.sub(r"\s+", " ", blob).strip()

    out: list[dict] = []
    kept: list[str] = []
    seen_img: set[str] = set()
    failures = 0
    for m in [x for x in items if x.png_paths]:
        for src in m.png_paths:
            try:
                img_hash = hashlib.md5(Path(src).read_bytes()).hexdigest()
            except OSError:
                continue
            if img_hash in seen_img:
                continue
            try:
                desc = describe_page(
                    src, api_key=settings.llm_api_key, model=settings.llm_model,
                    base_url=settings.llm_base_url,
                )
                if not (desc.get("transcription") or desc.get("caption")):
                    failures += 1  # a page that yields nothing is a failed read, not a blank page
            except Exception:
                desc = {}
                failures += 1
            norm = _norm(desc)
            if norm and any(SequenceMatcher(None, norm, k).ratio() >= 0.85 for k in kept):
                continue
            seen_img.add(img_hash)
            kept.append(norm)
            out.append({
                "src": src, "kind": desc.get("kind", ""),
                "caption": desc.get("caption", ""), "transcription": desc.get("transcription", ""),
            })
    return out, failures


def _persist_diagrams(stem: str, descs: list[dict], notes_dir: str) -> tuple[str, int]:
    """Copy + embed already-described diagram pages into the vault."""
    if not descs:
        return "", 0
    asset_dir = Path(notes_dir) / "assets" / stem
    asset_dir.mkdir(parents=True, exist_ok=True)
    out = ["\n\n## Diagrams\n"]
    for i, d in enumerate(descs, 1):
        dest = asset_dir / f"diagram-{i}.png"
        shutil.copyfile(d["src"], dest)
        kind = d.get("kind", "")
        caption = d.get("caption", "")
        transcription = d.get("transcription", "")
        label = f"diagram {i}" + (f" \u00b7 {kind}" if kind else "")
        out.append(f"\n![{label}](./assets/{stem}/diagram-{i}.png)\n")
        if caption:
            out.append(f"\n*{caption}*\n")
        if transcription:
            out.append(f"\n> **Transcription:** {transcription}\n")
    return "".join(out), len(descs)


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
    svc: TodoService | None,
    *,
    apply: bool,
    limit: int | None = None,
    force: bool = False,
    media_only: bool = False,
) -> IngestReport:
    report = IngestReport()
    read_notes = _store.list_notes if settings.notes_source != "jxa" else _export.list_notes
    media_map = media_by_note()

    # Build routing table from the user's existing TickTick lists.
    project_names: list[str] | None = None
    if svc is not None:
        svc.load_projects()
        project_names = svc.project_names

    live_ids: set[str] = set()
    for note in read_notes():
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
            # Transcribe handwriting/diagrams FIRST, then classify on the real content
            # (a handwritten note has ~no typed text — its content lives in the drawing).
            descs, vision_failures = (
                _describe_diagrams(drawings, settings) if has_media else ([], 0)
            )
            diagram_text = "\n".join(
                d["transcription"] for d in descs if d.get("transcription")
            ).strip()
            if has_media and vision_failures and not diagram_text:
                # Every word of this note is in an image we couldn't read. Writing it
                # now produces a note that claims to be empty; watermarking it means we
                # never look again. Leave it untouched so the next run retries — but
                # only so many times, or a permanently unreadable image bills us a
                # vision call every sync forever.
                tries = state.vision_failures(note.id) + 1
                if tries <= MAX_VISION_RETRIES:
                    if apply:
                        state.bump_vision_failure(note.id)
                    report.errors += 1
                    print(
                        f"  ! vision failed on '{note.name[:40]}' "
                        f"- retry {tries}/{MAX_VISION_RETRIES}"
                    )
                    continue
                # Out of retries: process it with whatever we have and stop paying for
                # it. The note keeps its image, so nothing is lost but the transcript.
                print(f"  ! vision keeps failing on '{note.name[:40]}' - giving up, "
                      "writing the note without a transcript")
                notify(f"vision unreadable after {MAX_VISION_RETRIES} tries: {note.name[:60]}")
            elif has_media and apply and diagram_text:
                state.clear_vision_failure(note.id)
            combined = (text + ("\n\n" + diagram_text if diagram_text else "")).strip()
            result = classify_note(
                combined or note.name,
                provider=settings.llm_provider,
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                base_url=settings.llm_base_url,
                projects=project_names,
            )

            md_path = None
            if not result.is_todo_only or has_media:
                if apply:
                    own_date = getattr(note, "created", "") or note.modified
                    stem = note_stem(result, note.id, own_date)
                    diagram_md, ndraw = _persist_diagrams(
                        stem, descs, settings.vault_notes_dir
                    )
                    old_md = state.get_md_path(note.id)
                    md_path = write_note(
                        result,
                        settings.vault_notes_dir,
                        diagram_md,
                        note_id=note.id,
                        fallback_date=own_date,
                    )
                    if old_md and old_md != md_path and Path(old_md).exists():
                        Path(old_md).unlink()  # note kept, title changed -> drop stale file
                        old_assets = (
                            Path(settings.vault_notes_dir) / "assets" / Path(old_md).stem
                        )
                        if old_assets.exists():
                            shutil.rmtree(old_assets)
                    report.diagrams += ndraw
                else:
                    report.diagrams += len(descs)
                report.notes_written += 1

            for todo in result.todos:
                if apply and svc is not None:
                    svc.upsert(
                        note.id,
                        TaskDraft(
                            title=todo.title,
                            due_date=todo.due_date,
                            priority=todo.priority,
                            project_id=svc.resolve_pid(todo.project),
                            items=todo.items,
                        ),
                    )
                report.todos_upserted += 1

            # reconcile: todos removed from the note -> complete their tasks
            if apply and svc is not None:
                new_keys = {item_key(note.id, td.title) for td in result.todos}
                for row in state.tasks_for_note(note.id):
                    if row["key"] in new_keys:
                        continue
                    pid = svc.resolve_task_pid(row["task_id"], row["project_id"])
                    if not pid:
                        continue  # can't complete remotely -> retry next run
                    try:
                        svc.complete(pid, row["task_id"])
                        state.mark_task_completed(row["key"])
                        report.completed += 1
                    except Exception:
                        pass

            if apply:
                state.mark_note(note.id, note.modified, md_path)
            report.processed += 1
        except Exception as e:  # one bad note must not abort the run
            report.errors += 1
            print(f"  ! error on '{note.name[:40]}': {type(e).__name__}: {str(e)[:120]}")

    # reconcile: notes deleted in Apple Notes -> complete tasks + archive vault note
    if apply and svc is not None and limit is None:
        for row in state.all_seen_notes():
            if row["note_id"] in live_ids:
                continue
            all_done = True
            for trow in state.tasks_for_note(row["note_id"]):
                pid = svc.resolve_task_pid(trow["task_id"], trow["project_id"])
                if not pid:
                    all_done = False
                    continue
                try:
                    svc.complete(pid, trow["task_id"])
                    state.mark_task_completed(trow["key"])
                    report.completed += 1
                except Exception:
                    all_done = False
            if not all_done:
                continue  # keep tracking; retry completing its tasks next run
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
