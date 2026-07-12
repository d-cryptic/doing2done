"""Extract hand-drawn diagrams (all pages) from Apple Notes' local store.

Apple Notes renders each handwriting page ('com.apple.paper') to a Preview.png in
'Previews/<id>-1-768x768-<page>/…/Preview.png'. We collect ALL pages ordered by
<page>, map attachment -> owning note (ZNOTE = note Z_PK), and bridge live notes
via the JXA id '.../ICNote/p<PK>'. Requires Full Disk Access.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

NOTES_CONTAINER = Path.home() / "Library/Group Containers/group.com.apple.notes"
DRAWING_UTIS = ("com.apple.paper", "com.apple.drawing", "com.apple.drawing.2")
IMAGE_UTIS = ("public.png", "public.jpeg", "public.heic")
_IMG_EXTS = (".png", ".jpg", ".jpeg", ".heic")


@dataclass(frozen=True)
class NoteMedia:
    identifier: str
    uti: str
    png_paths: tuple[str, ...]  # one per page, ordered
    is_drawing: bool


def note_pk_from_jxa_id(jxa_id: str) -> int | None:
    """'x-coredata://STORE/ICNote/p129' -> 129."""
    m = re.search(r"/p(\d+)\b", jxa_id or "")
    return int(m.group(1)) if m else None


def _resolve_pngs(identifier: str, container: Path) -> tuple[str, ...]:
    # 1) FULL-resolution render — captures the ENTIRE note (long/multi-screen),
    #    not just the first-screen 768x768 thumbnail.
    candidates: list[str] = [
        str(p)
        for p in container.glob(
            f"Accounts/*/FallbackImages/{identifier}/**/FallbackImage.png"
        )
    ]
    # 2) fallback to preview thumbnails only if no full render exists
    if not candidates:
        for d in container.glob(f"Accounts/*/Previews/{identifier}-*"):
            candidates += [str(p) for p in d.rglob("Preview.png")]
    if not candidates:
        for f in container.glob(f"Accounts/*/Media/{identifier}/*"):
            if f.suffix.lower() in _IMG_EXTS:
                candidates.append(str(f))
    # dedup identical renders, keep order
    seen: set[str] = set()
    pages: list[str] = []
    for p in candidates:
        try:
            h = hashlib.md5(Path(p).read_bytes()).hexdigest()
        except OSError:
            continue
        if h not in seen:
            seen.add(h)
            pages.append(p)
    return tuple(pages)

def media_by_note(container: Path = NOTES_CONTAINER) -> dict[int, list[NoteMedia]]:
    db = container / "NoteStore.sqlite"
    if not db.exists():
        return {}
    utis = DRAWING_UTIS + IMAGE_UTIS
    placeholders = ",".join("?" * len(utis))
    con = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            f"SELECT ZIDENTIFIER id, ZTYPEUTI uti, ZNOTE pk "
            f"FROM ZICCLOUDSYNCINGOBJECT "
            f"WHERE ZTYPEUTI IN ({placeholders}) AND ZNOTE IS NOT NULL",
            utis,
        ).fetchall()
    finally:
        con.close()
    out: dict[int, list[NoteMedia]] = {}
    for r in rows:
        out.setdefault(r["pk"], []).append(
            NoteMedia(
                identifier=r["id"],
                uti=r["uti"],
                png_paths=_resolve_pngs(r["id"], container),
                is_drawing=r["uti"] in DRAWING_UTIS,
            )
        )
    return out
