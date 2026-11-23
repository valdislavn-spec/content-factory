-- Durable queue for the travel growth funnel.
-- Both GitHub Actions and the local Playwright fallback read/write this table.
CREATE TABLE IF NOT EXISTS growth_queue (
  id TEXT PRIMARY KEY,
  platform TEXT NOT NULL,
  due TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  payload TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  published_at TEXT,
  published_url TEXT,
  message_id INTEGER,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_growth_queue_due
  ON growth_queue(platform, status, due);
