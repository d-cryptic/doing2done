"""Read Apple Notes directly from NoteStore.sqlite — FDA-only, no Automation.

Note bodies live gzip/zlib-compressed in ZICNOTEDATA.ZDATA as a protobuf
(document[2] -> note[3] -> note_text[2]). We rebuild the exact Core-Data note id
('x-coredata://<store-uuid>/ICNote/p<PK>') so dedup/state stays continuous with the
old JXA reader, and skip notes marked for deletion so reconciliation can archive them.
"""
from __future__ import annotations

import datetime as dt
import gzip
import sqlite3
import zlib
from collections.abc import Iterator
from pathlib import Path

from .export import RawNote
from .media import NOTES_CONTAINER

_CD_EPOCH = dt.datetime(2001, 1, 1, tzinfo=dt.UTC)


def _decompress(raw: bytes) -> bytes:
    for fn in (
        lambda b: zlib.decompress(b),
        lambda b: gzip.decompress(b),
        lambda b: zlib.decompress(b, -zlib.MAX_WBITS),
    ):
        try:
            return fn(raw)
        except Exception:
            continue
    return b""


def _pb_fields(b: bytes) -> Iterator[tuple[int, int, bytes | int]]:
    i = 0
    n = len(b)
    while i < n:
        tag = b[i]
        fn, wt = tag >> 3, tag & 7
        i += 1
        if wt == 0:  # varint
            v = s = 0
            while True:
                if i >= n:
                    return
                v |= (b[i] & 0x7F) << s
                s += 7
                brk = not b[i] & 0x80
                i += 1
                if brk:
                    break
            yield fn, wt, v
        elif wt == 2:  # length-delimited
            ln = s = 0
            while True:
                if i >= n:
                    return
                ln |= (b[i] & 0x7F) << s
                s += 7
                brk = not b[i] & 0x80
                i += 1
                if brk:
                    break
            yield fn, wt, b[i : i + ln]
            i += ln
        elif wt == 5:
            i += 4
        elif wt == 1:
            i += 8
        else:
            break


def _pb_get(b: bytes | None, field: int) -> bytes | None:
    if not b:
        return None
    for fn, wt, val in _pb_fields(b):
        if fn == field and wt == 2 and isinstance(val, bytes):
            return val
    return None


def _note_text(blob: bytes) -> str:
    doc = _pb_get(blob, 2)
    note = _pb_get(doc, 3)
    text = _pb_get(note, 2)
    return text.decode("utf-8", "replace") if text else ""




def list_notes(container: Path = NOTES_CONTAINER) -> list[RawNote]:
    db = container / "NoteStore.sqlite"
    con = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
    con.row_factory = sqlite3.Row
    try:
        uuid = con.execute("SELECT Z_UUID FROM Z_METADATA").fetchone()["Z_UUID"]
        folders = {
            r["Z_PK"]: (r["ZTITLE2"] or "")
            for r in con.execute("SELECT Z_PK, ZTITLE2 FROM ZICCLOUDSYNCINGOBJECT")
        }
        rows = con.execute(
            "SELECT n.Z_PK pk, n.ZTITLE1 title, n.ZMODIFICATIONDATE1 modf, "
            "n.ZFOLDER folder, d.ZDATA data "
            "FROM ZICCLOUDSYNCINGOBJECT n "
            "JOIN ZICNOTEDATA d ON n.ZNOTEDATA = d.Z_PK "
            "WHERE n.ZNOTEDATA IS NOT NULL"
        ).fetchall()
    finally:
        con.close()

    notes: list[RawNote] = []
    for r in rows:
        folder_name = folders.get(r["folder"], "")
        if folder_name == "Recently Deleted":
            continue  # treat as deleted -> reconciliation archives it
        try:
            text = _note_text(_decompress(r["data"])) if r["data"] else ""
        except Exception:
            text = ""  # a single corrupt blob must not abort the whole read
        name = r["title"]
        if not name:  # null title -> derive from first non-empty line
            first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
            name = first[:60] or "Untitled"
        modified = (
            (_CD_EPOCH + dt.timedelta(seconds=r["modf"])).isoformat() if r["modf"] else ""
        )
        notes.append(
            RawNote(
                id=f"x-coredata://{uuid}/ICNote/p{r['pk']}",
                name=name,
                modified=modified,
                body_html=text,
                folder=folder_name,
            )
        )
    return notes
