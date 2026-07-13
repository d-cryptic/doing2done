CREATE TABLE IF NOT EXISTS task_map (
  key TEXT PRIMARY KEY, note_id TEXT NOT NULL, task_id TEXT NOT NULL,
  project_id TEXT, title TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS notes_seen (
  note_id TEXT PRIMARY KEY, modified TEXT NOT NULL, md_path TEXT,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS notes (
  note_id TEXT PRIMARY KEY, title TEXT, body TEXT, modified TEXT,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
