"""Тесты read-only MCP-сервера фабрики (tools/factory_mcp.py)."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import tools.factory_mcp as mcp


class FactoryMcpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.sqlite3"
        conn = sqlite3.connect(self.db)
        conn.executescript(
            """
            CREATE TABLE posts (channel_id TEXT, format TEXT, created_at TEXT, status TEXT);
            INSERT INTO posts VALUES ('ai-news', 'story', '2026-11-07T19:00:00+00:00', 'generated');
            INSERT INTO posts VALUES ('ai-news', 'story', '2026-11-07T19:01:00+00:00', 'published');
            INSERT INTO posts VALUES ('crypto-news', 'story', '2026-11-07T19:02:00+00:00', 'published');
            -- Реальная схема runs: без status (его не должно требовать).
            CREATE TABLE runs (channel_id TEXT, started_at TEXT, posts_published INT);
            INSERT INTO runs VALUES ('ai-news', '2026-11-07T19:00:00+00:00', 1);
            """
        )
        conn.commit()
        conn.close()
        self._original_db = mcp.DB_PATH
        mcp.DB_PATH = self.db

    def tearDown(self):
        mcp.DB_PATH = self._original_db
        self.tmp.cleanup()

    def test_select_is_allowed(self):
        result = mcp.tool_factory_query(
            "SELECT channel_id, COUNT(*) AS cnt FROM posts GROUP BY channel_id"
        )
        self.assertEqual(result["columns"], ["channel_id", "cnt"])
        self.assertEqual(result["count"], 2)

    def test_write_is_rejected(self):
        for sql in (
            "DELETE FROM posts",
            "UPDATE posts SET status='x'",
            "DROP TABLE posts",
            "INSERT INTO posts VALUES ('x','y')",
        ):
            with self.assertRaises(ValueError):
                mcp.tool_factory_query(sql)

    def test_multiple_statements_rejected(self):
        with self.assertRaises(ValueError):
            mcp.tool_factory_query("SELECT 1; DROP TABLE posts")

    def test_empty_sql_rejected(self):
        with self.assertRaises(ValueError):
            mcp.tool_factory_query("   ")

    def test_initialize_handshake(self):
        response = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(response["result"]["protocolVersion"], mcp.PROTOCOL_VERSION)
        self.assertEqual(response["result"]["serverInfo"]["name"], "factory-mcp")

    def test_tools_list(self):
        response = mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertEqual(
            names,
            {
                "factory_status",
                "factory_query",
                "factory_schema",
                "trends_now",
                "hackernews_top",
                "web_search",
            },
        )

    def test_unknown_method_error(self):
        response = mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "does/not/exist"})
        self.assertEqual(response["error"]["code"], -32601)

    def test_tool_error_is_reported(self):
        response = mcp.handle(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "factory_query", "arguments": {"sql": "DELETE FROM posts"}},
            }
        )
        self.assertTrue(response["result"]["isError"])
        text = response["result"]["content"][0]["text"]
        self.assertTrue(
            "только для чтения" in text or "разрешены только SELECT" in text,
            text,
        )

    def test_schema_lists_tables(self):
        result = mcp.tool_factory_schema()
        self.assertIn("posts", result["tables"])
        self.assertIn("runs", result["tables"])
        self.assertTrue(any(column["name"] == "channel_id" for column in result["tables"]["posts"]))

    def test_status_tool_returns_json(self):
        try:
            result = mcp.tool_factory_status()
        except Exception as exc:  # конфиг каналов в тестовом окружении может не найтись
            self.skipTest(f"config недоступен: {exc}")
        self.assertTrue(isinstance(result, dict))
        self.assertNotIn("db_error", result, result.get("db_error"))
        self.assertEqual(result["latest_runs"][0]["channel_id"], "ai-news")
        self.assertIn("db", result)


if __name__ == "__main__":
    unittest.main()
