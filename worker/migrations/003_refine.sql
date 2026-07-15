-- Maps a bot confirmation message -> the tasks it created, so a reply can correct them.
CREATE TABLE IF NOT EXISTS tg_replies (
  chat_id    TEXT NOT NULL,
  message_id INTEGER NOT NULL,
  capture_id TEXT,
  tasks      TEXT NOT NULL,          -- json: [{taskId, projectId, title}]
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (chat_id, message_id)
);

-- Every correction you make, kept as training signal for the classifier evals.
CREATE TABLE IF NOT EXISTS corrections (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  capture_id TEXT,
  original   TEXT NOT NULL,          -- what you originally sent
  correction TEXT NOT NULL,          -- what you replied
  action     TEXT NOT NULL,          -- delete | update | none
  detail     TEXT,                   -- json of the applied change
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
