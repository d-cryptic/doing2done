"""SQLite state: note->task map (with project + completion) + note watermark."""
from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS task_map (
    key        TEXT PRIMARY KEY,   -- sha1(note_id:title)
    note_id    TEXT NOT NULL,
    task_id    TEXT NOT NULL,
    project_id TEXT,
    title      TEXT NOT NULL,
    completed  INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS pushed (
    note_id    TEXT PRIMARY KEY,
    hash       TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS notes_seen (
    note_id    TEXT PRIMARY KEY,
    modified   TEXT NOT NULL,
    md_path    TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# columns added after v1 — applied idempotently for existing DBs
_MIGRATIONS = {
    "task_map": {"project_id": "TEXT", "completed": "INTEGER NOT NULL DEFAULT 0"},
}


def item_key(note_id: str, title: str) -> str:
    return hashlib.sha1(f"{note_id}:{title}".encode()).hexdigest()


class State:
    def __init__(self, db_path: str) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)
            for table, cols in _MIGRATIONS.items():
                have = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
                for col, decl in cols.items():
                    if col not in have:
                        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ── task dedup ──
    def get_task(self, note_id: str, title: str) -> sqlite3.Row | None:
        with self._conn() as c:
            return c.execute(
                "SELECT * FROM task_map WHERE key = ?", (item_key(note_id, title),)
            ).fetchone()

    def remember_task(
        self, note_id: str, title: str, task_id: str, project_id: str | None
    ) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO task_map"
                "(key, note_id, task_id, project_id, title, completed) "
                "VALUES (?, ?, ?, ?, ?, 0)",
                (item_key(note_id, title), note_id, task_id, project_id, title),
            )

    def tasks_for_note(self, note_id: str) -> list[sqlite3.Row]:
        with self._conn() as c:
            return c.execute(
                "SELECT * FROM task_map WHERE note_id = ? AND completed = 0", (note_id,)
            ).fetchall()

    def mark_task_completed(self, key: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE task_map SET completed = 1 WHERE key = ?", (key,))

    # ── note watermark ──
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

    def recently_completed(self, days: int = 1) -> list[sqlite3.Row]:
        with self._conn() as c:
            return c.execute(
                "SELECT title FROM task_map WHERE completed = 1 "
                "AND updated_at >= datetime('now', ?)",
                (f"-{days} day",),
            ).fetchall()

    def get_md_path(self, note_id: str) -> str | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT md_path FROM notes_seen WHERE note_id = ?", (note_id,)
            ).fetchone()
            return row["md_path"] if row else None

    def all_seen_notes(self) -> list[sqlite3.Row]:
        with self._conn() as c:
            return c.execute("SELECT note_id, md_path FROM notes_seen").fetchall()

    def completions_by_day(self, days: int = 14) -> list[tuple[str, int]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT date(updated_at) d, COUNT(*) n FROM task_map "
                "WHERE completed = 1 AND updated_at >= datetime('now', ?) "
                "GROUP BY d ORDER BY d",
                (f"-{days} day",),
            ).fetchall()
            return [(r["d"], r["n"]) for r in rows]

    def get_pushed_hash(self, note_id: str) -> str | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT hash FROM pushed WHERE note_id = ?", (note_id,)
            ).fetchone()
            return row["hash"] if row else None

    def set_pushed_hash(self, note_id: str, digest: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO pushed(note_id, hash, updated_at) "
                "VALUES (?, ?, datetime('now'))",
                (note_id, digest),
            )

    def get_kv(self, key: str) -> str | None:
        with self._conn() as c:
            row = c.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None

    def set_kv(self, key: str, value: str) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, value))

    def forget_note(self, note_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM notes_seen WHERE note_id = ?", (note_id,))
