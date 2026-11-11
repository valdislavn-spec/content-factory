"""Тесты настройки бота через Bot API (без сети)."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    path = ROOT / "scripts" / "bot_setup.py"
    spec = importlib.util.spec_from_file_location("bot_setup_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class BotSetupTests(unittest.TestCase):
    def setUp(self):
        self.module = _load_script()

    def test_setup_calls(self):
        calls = self.module.build_setup_calls()
        methods = [call["method"] for call in calls]
        self.assertEqual(
            methods,
            ["setMyCommands", "setMyDescription", "setMyShortDescription", "setChatMenuButton"],
        )
        commands = calls[0]["payload"]["commands"]
        self.assertIn("start", [item["command"] for item in commands])
        self.assertLessEqual(len(calls[1]["payload"]["description"]), 512)
        self.assertLessEqual(len(calls[2]["payload"]["short_description"]), 120)

    def test_dry_run_does_not_call_network(self):
        with mock.patch.object(self.module, "_api", side_effect=AssertionError("сеть не ожидалась")):
            applied = self.module.apply_setup("token", dry_run=True)
        self.assertEqual(len(applied), 4)
        self.assertTrue(all(line.startswith("[dry-run]") for line in applied))

    def test_apply_sends_calls(self):
        with mock.patch.object(self.module, "_api", return_value={"ok": True}) as mocked:
            applied = self.module.apply_setup("token", dry_run=False)
        self.assertEqual(applied, ["setMyCommands", "setMyDescription", "setMyShortDescription", "setChatMenuButton"])
        self.assertEqual(mocked.call_count, 4)

    def test_check_bot(self):
        responses = {
            "getMe": {"ok": True, "result": {"username": "cf_bot", "first_name": "CF"}},
            "getMyCommands": {"ok": True, "result": [{"command": "start"}]},
            "getMyShortDescription": {"ok": True, "result": {"short_description": "desc"}},
        }

        def fake(token, method, payload=None):
            return responses[method]

        with mock.patch.object(self.module, "_api", side_effect=fake):
            data = self.module.check_bot("token")
        self.assertEqual(data["username"], "cf_bot")
        self.assertEqual(data["commands"], ["start"])

    def test_botfather_checklist_mentions_stars(self):
        checklist = " ".join(self.module.botfather_checklist())
        self.assertIn("Stars", checklist)
        self.assertIn("/setinline", checklist)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
