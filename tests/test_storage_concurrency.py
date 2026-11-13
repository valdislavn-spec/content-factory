"""SQLite WAL/busy-timeout sanity for multi-process reads."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from content_factory.storage import Storage


class StorageConcurrencyTest(unittest.TestCase):
    def test_file_db_uses_wal_and_allows_two_connections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "factory.sqlite3"
            with Storage(db) as first, Storage(db) as second:
                self.assertEqual(first.conn.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
                self.assertEqual(second.conn.execute("PRAGMA busy_timeout").fetchone()[0], 30000)
                first.conn.execute("CREATE TABLE IF NOT EXISTS probe (n INTEGER)")
                first.conn.execute("INSERT INTO probe (n) VALUES (1)")
                first.conn.commit()
                self.assertEqual(second.conn.execute("SELECT COUNT(*) FROM probe").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
