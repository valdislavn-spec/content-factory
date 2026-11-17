-- Human clicks are aggregated in the clicks table.
-- Bot and preview-crawler clicks are retained here with is_bot = 1.
ALTER TABLE click_log ADD COLUMN is_bot INTEGER NOT NULL DEFAULT 0;
