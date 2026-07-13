CREATE TABLE IF NOT EXISTS captures (
  id TEXT PRIMARY KEY, source TEXT NOT NULL, text TEXT NOT NULL, reply TEXT,
  created TEXT NOT NULL DEFAULT (datetime('now')), processed INTEGER NOT NULL DEFAULT 0
);
