-- Public, revocable links to a single note. Nothing is shared unless a token exists.
CREATE TABLE IF NOT EXISTS shares (
  token      TEXT PRIMARY KEY,       -- secrets.token_urlsafe(32), unguessable
  note_id    TEXT,
  title      TEXT NOT NULL,
  html       TEXT NOT NULL,          -- pre-rendered at share time (no raw HTML from notes)
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  expires_at TEXT,                   -- NULL = no expiry
  revoked    INTEGER NOT NULL DEFAULT 0,
  views      INTEGER NOT NULL DEFAULT 0
);
