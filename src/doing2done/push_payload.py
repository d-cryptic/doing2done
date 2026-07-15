"""What actually gets embedded for semantic search.

The edge used to index the raw Apple Note — `note.name` and `note.body_html`. For a
handwritten note the raw body is a single attachment placeholder, so all 12 of them
embedded as an empty string and could never be found: the transcription that makes
them searchable lives only in the vault markdown. Raw titles were no better —
"#Tasks", "last mvp" — so results were unreadable even when they hit.

The vault note is the enriched artifact: classifier title, TL;DR, cleaned body, and
the vision transcription. That is what should be searchable.
"""
from __future__ import annotations

import re
from pathlib import Path

MAX_BODY = 8000


def _frontmatter_title(md: str) -> str:
    m = re.search(r'^title:\s*"?(.*?)"?\s*$', md, re.M)
    return m.group(1).strip() if m else ""


def _strip_frontmatter(md: str) -> str:
    return re.sub(r"^---\n.*?\n---\n", "", md, flags=re.S).strip()


def payload_for(note, state) -> dict:
    """The /ingest item for a note: the vault version when we have one, else raw."""
    md_path = state.get_md_path(note.id)
    if md_path and Path(md_path).exists():
        raw = Path(md_path).read_text()
        body = _strip_frontmatter(raw)
        # Chips are navigation, not meaning — they'd pollute the embedding.
        body = re.sub(r'<div class="v-note-tags">.*?</div>', "", body, flags=re.S)
        title = _frontmatter_title(raw) or note.name
        if body.strip():
            return {
                "note_id": note.id,
                "title": title,
                "body": body[:MAX_BODY],
                "modified": note.modified,
            }
    # todo-only notes never get a vault file; index what Apple gives us.
    return {
        "note_id": note.id,
        "title": note.name,
        "body": (note.body_html or "")[:MAX_BODY],
        "modified": note.modified,
    }
