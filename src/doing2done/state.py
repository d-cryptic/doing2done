"""SQLite state: note->task dedup map + processed-note watermark. Zero infra."""
from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS task_map (
    key        TEXT PRIMARY KEY,   -- sha1(note_id:item_title)
    note_id    TEXT NOT NULL,
    task_id    TEXT NOT NULL,
    title      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS notes_seen (
    note_id    TEXT PRIMARY KEY,
    modified   TEXT NOT NULL,      -- last modification timestamp we processed
    md_path    TEXT,               -- where the note's markdown was written
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def item_key(note_id: str, title: str) -> str:
    return hashlib.sha1(f"{note_id}:{title}".encode()).hexdigest()


class State:
    def __init__(self, db_path: str) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # task dedup
    def get_task_id(self, note_id: str, title: str) -> str | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT task_id FROM task_map WHERE key = ?",
                (item_key(note_id, title),),
            ).fetchone()
            return row["task_id"] if row else None

    def remember_task(self, note_id: str, title: str, task_id: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO task_map(key, note_id, task_id, title) "
                "VALUES (?, ?, ?, ?)",
                (item_key(note_id, title), note_id, task_id, title),
            )

    # note watermark
    def note_needs_processing(self, note_id: str, modified: str) -> bool:
        with self._conn() as c:
            row = c.execute(
                "SELECT modified FROM notes_seen WHERE note_id = ?", (note_id,)
            ).fetchone()
            return row is None or row["modified"] != modified

    def mark_note(self, note_id: str, modified: str, md_path: str | None) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO notes_seen(note_id, modified, md_path) "
                "VALUES (?, ?, ?)",
                (note_id, modified, md_path),
            )
