"""Write a classified note as clean Markdown into the VitePress vault."""
from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from .classify.models import NoteResult


def slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[\s_-]+", "-", s) or "note"


def _yaml(s: str) -> str:
    """Double-quote a scalar for safe YAML (handles colons, quotes, etc.)."""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def sanitize_body(md: str) -> str:
    """Neutralize VitePress/Vue interpolation so literal braces don't crash the build."""
    return (md or "").replace("{{", "&#123;&#123;").replace("}}", "&#125;&#125;")


def render_frontmatter(title: str, date: str | None, tags: list[str]) -> str:
    tag_list = ", ".join(_yaml(x) for x in tags)
    return (
        f"---\ntitle: {_yaml(title)}\ndate: {_yaml(date or '')}\n"
        f"tags: [{tag_list}]\n---\n\n"
    )


def note_date(result: NoteResult, fallback_date: str = "") -> str:
    """The note's date, falling back to when Apple Notes last modified it.

    The classifier only emits a date when the note text mentions one, which is rare —
    without this fallback most notes land dateless and drop out of the digest,
    timeline, and dormancy checks entirely.
    """
    return (result.date or "").split("T")[0] or (fallback_date or "").split("T")[0]


def note_stem(
    result: NoteResult, note_id: str = "", fallback_date: str = ""
) -> str:
    """Stable, unique file stem: date + slug + short note-id hash (avoids collisions)."""
    prefix = note_date(result, fallback_date).split("T")[0]
    base = f"{prefix}-{slugify(result.title)}".strip("-")
    if note_id:
        base += "-" + hashlib.sha1(note_id.encode()).hexdigest()[:6]
    return base


def write_note(
    result: NoteResult,
    notes_dir: str,
    extra_markdown: str = "",
    note_id: str = "",
    fallback_date: str = "",
) -> str:
    d = Path(notes_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{note_stem(result, note_id, fallback_date)}.md"
    fm = render_frontmatter(result.title, note_date(result, fallback_date), result.tags)
    parts = []
    if result.summary:
        parts.append(f"> **TL;DR** {result.summary}\n")
    parts.append((result.markdown or "").strip())
    if result.links:
        parts.append("\n## Links\n" + "\n".join(f"- <{u}>" for u in result.links))
    body = "\n\n".join(p for p in parts if p) + extra_markdown
    path.write_text(fm + sanitize_body(body).strip() + "\n")
    return str(path)


def archive_note(md_path: str, vault_dir: str, notes_dir: str) -> None:
    """Soft-delete: move a note's .md + its assets into <vault>/archive/ (kept, unpublished)."""
    src = Path(md_path)
    stem = src.stem
    arc_notes = Path(vault_dir) / "archive" / "notes"
    arc_notes.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.move(str(src), str(arc_notes / src.name))
    assets = Path(notes_dir) / "assets" / stem
    if assets.exists():
        dest = Path(vault_dir) / "archive" / "assets" / stem
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(assets), str(dest))
