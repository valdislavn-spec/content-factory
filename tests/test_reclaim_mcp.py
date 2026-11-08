"""Тесты Reclaim.ai MCP-сервера и синхронизации задач (без сети)."""
import json
import unittest

import scripts.reclaim_sync as sync
import tools.reclaim_mcp as reclaim


class FakeApi:
    def __init__(self, tasks=None):
        self.tasks = tasks or []
        self.created = []

    def list_tasks(self, include_completed=False):
        return {"count": len(self.tasks), "tasks": [{"title": t} for t in self.tasks]}

    def create_task(self, title, notes="", minutes=30, priority="P3", due=""):
        self.created.append({"title": title, "minutes": minutes, "priority": priority})
        return {"id": len(self.created), "title": title}


class ReclaimMcpProtocolTests(unittest.TestCase):
    def test_initialize(self):
        response = reclaim.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(response["result"]["serverInfo"]["name"], "reclaim-mcp")

    def test_tools_list(self):
        response = reclaim.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [tool["name"] for tool in response["result"]["tools"]]
        self.assertEqual(
            names,
            [
                "reclaim_whoami",
                "reclaim_list_tasks",
                "reclaim_create_task",
                "reclaim_complete_task",
                "reclaim_list_events",
            ],
        )

    def test_missing_key_is_clear(self):
        response = reclaim.handle(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "reclaim_list_tasks", "arguments": {}},
            }
        )
        self.assertTrue(response["result"]["isError"])
        self.assertIn("RECLAIM_API_KEY", response["result"]["content"][0]["text"])

    def test_create_task_payload(self):
        calls = {}

        def fake_request(method, path, payload=None, params=None, timeout=30):
            calls.update(method=method, path=path, payload=payload)
            return {"id": 42, "title": "Test task", "status": "NEW", "timeChunksRequired": 2}

        original = reclaim._request
        reclaim._request = fake_request
        try:
            task = reclaim.create_task("Test task", "notes", 30, "P2", "2026-11-10T12:00:00Z")
        finally:
            reclaim._request = original
        self.assertEqual(calls["path"], "/tasks")
        self.assertEqual(calls["payload"]["timeChunksRequired"], 2)
        self.assertEqual(calls["payload"]["priority"], "P2")
        self.assertEqual(task["id"], 42)

    def test_empty_title_rejected(self):
        with self.assertRaises(reclaim.ReclaimError):
            reclaim.create_task("   ")


class ReclaimSyncTests(unittest.TestCase):
    def test_missing_tasks_skips_existing(self):
        existing = [sync.WORK_TASKS[0]["title"]]
        todo = sync.missing_tasks(existing)
        self.assertNotIn(sync.WORK_TASKS[0]["title"], [task["title"] for task in todo])
        self.assertEqual(len(todo), len(sync.WORK_TASKS) - 1)

    def test_dry_run_creates_nothing(self):
        fake = FakeApi()
        original = sync.API
        sync.API = fake
        try:
            result = sync.run(dry_run=True)
        finally:
            sync.API = original
        self.assertTrue(result["dry_run"])
        self.assertEqual(fake.created, [])
        self.assertEqual(len(result["planned"]), len(sync.WORK_TASKS))

    def test_apply_creates_only_missing(self):
        fake = FakeApi(tasks=[sync.WORK_TASKS[0]["title"]])
        original = sync.API
        sync.API = fake
        try:
            result = sync.run(dry_run=False)
        finally:
            sync.API = original
        self.assertEqual(len(fake.created), len(sync.WORK_TASKS) - 1)
        self.assertEqual(len(result["created"]), len(sync.WORK_TASKS) - 1)

    def test_apply_second_time_is_idempotent(self):
        fake = FakeApi(tasks=[task["title"] for task in sync.WORK_TASKS])
        original = sync.API
        sync.API = fake
        try:
            result = sync.run(dry_run=False)
        finally:
            sync.API = original
        self.assertEqual(fake.created, [])
        self.assertEqual(result["planned"], [])


if __name__ == "__main__":
    unittest.main()
