"""Write a classified note as clean Markdown into the VitePress vault."""
from __future__ import annotations

import re
from pathlib import Path

from .classify.models import NoteResult


def slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[\s_-]+", "-", s) or "note"


def write_note(result: NoteResult, notes_dir: str) -> str:
    """Write frontmatter + body; filename is date-prefixed + slug (stable per note)."""
    d = Path(notes_dir)
    d.mkdir(parents=True, exist_ok=True)
    prefix = (result.date or "").split("T")[0]
    stem = f"{prefix}-{slugify(result.title)}".strip("-")
    path = d / f"{stem}.md"

    tags = ", ".join(result.tags)
    fm = f"---\ntitle: {result.title}\ndate: {result.date or ''}\ntags: [{tags}]\n---\n\n"
    path.write_text(fm + (result.markdown or "").strip() + "\n")
    return str(path)
