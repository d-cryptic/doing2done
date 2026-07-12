"""Extract hand-drawn diagrams / images from Apple Notes' local store.

Apple Notes renders every drawing ('com.apple.paper') to a Preview.png in its
group container. We map attachment -> owning note (ZNOTE = note Z_PK) and resolve
the identifier to its rendered PNG. The JXA note id ('.../ICNote/p<PK>') bridges
a live note to its Z_PK. Requires Full Disk Access.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

NOTES_CONTAINER = Path.home() / "Library/Group Containers/group.com.apple.notes"
DRAWING_UTIS = ("com.apple.paper", "com.apple.drawing", "com.apple.drawing.2")
IMAGE_UTIS = ("public.png", "public.jpeg", "public.heic")


@dataclass(frozen=True)
class NoteMedia:
    identifier: str
    uti: str
    png_path: str | None
    is_drawing: bool


def note_pk_from_jxa_id(jxa_id: str) -> int | None:
    """'x-coredata://STORE/ICNote/p129' -> 129."""
    m = re.search(r"/p(\d+)\b", jxa_id or "")
    return int(m.group(1)) if m else None


def _resolve_png(identifier: str, container: Path) -> str | None:
    for d in container.glob(f"Accounts/*/Previews/{identifier}-*"):
        for png in d.rglob("Preview.png"):
            return str(png)
    for f in container.glob(f"Accounts/*/Media/{identifier}/*"):
        if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".heic"):
            return str(f)
    return None


def media_by_note(container: Path = NOTES_CONTAINER) -> dict[int, list[NoteMedia]]:
    """Map note Z_PK -> list of NoteMedia (drawings + embedded images)."""
    db = container / "NoteStore.sqlite"
    if not db.exists():
        return {}
    utis = DRAWING_UTIS + IMAGE_UTIS
    placeholders = ",".join("?" * len(utis))
    con = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
    con.row_factory = sqlite3.Row
    out: dict[int, list[NoteMedia]] = {}
    try:
        rows = con.execute(
            f"SELECT ZIDENTIFIER id, ZTYPEUTI uti, ZNOTE pk "
            f"FROM ZICCLOUDSYNCINGOBJECT "
            f"WHERE ZTYPEUTI IN ({placeholders}) AND ZNOTE IS NOT NULL",
            utis,
        ).fetchall()
    finally:
        con.close()
    for r in rows:
        out.setdefault(r["pk"], []).append(
            NoteMedia(
                identifier=r["id"],
                uti=r["uti"],
                png_path=_resolve_png(r["id"], container),
                is_drawing=r["uti"] in DRAWING_UTIS,
            )
        )
    return out
