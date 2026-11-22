CREATE TABLE IF NOT EXISTS scheduler_state (
  name TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS publish_retries (
  post_id TEXT NOT NULL,
  publisher TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  post_json TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT NOT NULL,
  last_error TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (post_id, publisher)
);

CREATE INDEX IF NOT EXISTS idx_publish_retries_due
  ON publish_retries(channel_id, next_attempt_at);

CREATE TABLE IF NOT EXISTS channel_health (
  channel_id TEXT PRIMARY KEY,
  last_tick_at TEXT,
  last_post_at TEXT,
  last_error TEXT DEFAULT '',
  updated_at TEXT NOT NULL
);
