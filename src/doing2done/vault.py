"""Write a classified note as clean Markdown into the VitePress vault."""
from __future__ import annotations

import re
from pathlib import Path

from .classify.models import NoteResult


def slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[\s_-]+", "-", s) or "note"


def note_stem(result: NoteResult) -> str:
    """Stable, date-prefixed file stem for a note (also names its asset folder)."""
    prefix = (result.date or "").split("T")[0]
    return f"{prefix}-{slugify(result.title)}".strip("-")


def write_note(result: NoteResult, notes_dir: str, extra_markdown: str = "") -> str:
    d = Path(notes_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{note_stem(result)}.md"
    tags = ", ".join(result.tags)
    fm = f"---\ntitle: {result.title}\ndate: {result.date or ''}\ntags: [{tags}]\n---\n\n"
    body = (result.markdown or "").strip() + extra_markdown
    path.write_text(fm + body.strip() + "\n")
    return str(path)
