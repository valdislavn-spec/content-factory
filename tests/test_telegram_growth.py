"""Тесты Telegram-механик роста: deep links, inline mode, growth-события (без сети)."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from content_factory.config import Settings, load_network_channels
from content_factory.integrations.telegram_growth import (
    TelegramGrowthBot,
    build_inline_results,
    make_payload,
    parse_payload,
    plan_update_actions,
    start_link,
)
from content_factory.models import GeneratedPost
from content_factory.storage import Storage

PAYLOAD = "crypto_news__13__abcd1234"


class GrowthTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        base = Settings.load(load_env=False)
        raw = copy.deepcopy(base.raw)
        raw["app"].update(
            {
                "dry_run": True,
                "data_dir": str(self.root / "data"),
                "db_path": str(self.root / "data" / "factory.sqlite3"),
                "outbox_dir": str(self.root / "data" / "outbox"),
                "reports_dir": str(self.root / "data" / "reports"),
                "logs_dir": str(self.root / "data" / "logs"),
            }
        )
        self.settings = Settings(
            root=base.root,
            raw=raw,
            settings_path=base.settings_path,
            channels_path=base.channels_path,
        )
        self.settings.ensure_dirs()
        self.channels = load_network_channels(self.settings)  # только EN/ES
        self.storage = Storage(self.settings.db_path)
        self.addCleanup(self.storage.close)


class PayloadTests(GrowthTestCase):
    def test_roundtrip_for_all_channels(self):
        for channel in self.channels:
            payload = make_payload(channel.id, slot="13", post_id="abcdef123456")
            self.assertLessEqual(len(payload), 64)
            parsed = parse_payload(payload)
            self.assertIsNotNone(parsed, payload)
            self.assertEqual(parsed["channel_id"], channel.id)
            self.assertEqual(parsed["slot"], "13")

    def test_invalid_payload(self):
        self.assertIsNone(parse_payload(""))
        self.assertIsNone(parse_payload("плохой payload с пробелами"))
        self.assertIsNone(parse_payload("x" * 70))

    def test_start_link(self):
        link = start_link("@cf_growth_bot", "ai-news", slot="9", post_id="post42")
        self.assertTrue(link.startswith("https://t.me/cf_growth_bot?start="))
        parsed = parse_payload(link.split("start=", 1)[1])
        self.assertEqual(parsed["channel_id"], "ai-news")
        self.assertEqual(parsed["slot"], "9")
        self.assertEqual(parsed["post_id"], "post42")

    def test_start_link_requires_bot(self):
        with self.assertRaises(Exception):
            start_link("", "ai-news")


class InlineResultsTests(GrowthTestCase):
    def test_build_inline_results_truncates_and_adds_link(self):
        posts = [
            {"post_id": "p1", "text": "<b>GPT-5</b>\n\n" + "текст " * 200},
            {"post_id": "p2", "text": ""},
            {"post_id": "p3", "text": "Короткий пост"},
        ]
        results = build_inline_results(posts, "https://t.me/AINEWS0007")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["type"], "article")
        self.assertIn("https://t.me/AINEWS0007", results[0]["input_message_content"]["message_text"])
        self.assertLessEqual(len(results[0]["title"]), 61)
        self.assertIn("cf-p1", results[0]["id"])


class UpdatePlanTests(GrowthTestCase):
    def test_start_saves_growth_event_and_returns_button(self):
        update = {
            "update_id": 1,
            "message": {"text": f"/start {PAYLOAD}", "from": {"id": 777}},
        }
        actions = plan_update_actions(update, self.storage, self.channels, self.settings)
        self.assertEqual(len(actions), 1)
        action = actions[0]
        self.assertEqual(action["method"], "sendMessage")
        self.assertEqual(action["payload"]["chat_id"], 777)
        button = action["payload"]["reply_markup"]["inline_keyboard"][0][0]
        self.assertEqual(button["url"], "https://t.me/HOOPY0007")
        summary = self.storage.growth_summary(days=1)
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["by_event"]["start"], 1)
        self.assertEqual(summary["by_channel"]["crypto-news"], 1)

    def test_inline_query_uses_recent_posts(self):
        self.storage.save_post(
            GeneratedPost(
                id="p-1",
                channel_id="ai-news",
                cluster_id="c-1",
                format="story",
                text="<b>AI news</b>\n\nНовый релиз модели.",
            ),
            status="generated",
        )
        update = {
            "update_id": 2,
            "inline_query": {"id": "iq-1", "query": "ai-news", "from": {"id": 5}},
        }
        actions = plan_update_actions(update, self.storage, self.channels, self.settings)
        self.assertEqual(actions[0]["method"], "answerInlineQuery")
        payload = actions[0]["payload"]
        self.assertEqual(payload["inline_query_id"], "iq-1")
        self.assertGreaterEqual(len(payload["results"]), 1)
        self.assertEqual(self.storage.growth_summary(days=1)["by_event"]["inline"], 1)

    def test_unknown_update_is_ignored(self):
        self.assertEqual(plan_update_actions({"update_id": 3}, self.storage, self.channels), [])


class BotPollingTests(GrowthTestCase):
    def test_poll_once_processes_start_and_advances_offset(self):
        bot = TelegramGrowthBot("TOKEN", "cf_bot", self.storage, self.channels, self.settings)
        calls = []

        def fake_api(method, payload):
            calls.append((method, payload))
            if method == "getUpdates":
                return {
                    "ok": True,
                    "result": [
                        {
                            "update_id": 10,
                            "message": {"text": f"/start {PAYLOAD}", "from": {"id": 42}},
                        }
                    ],
                }
            return {"ok": True, "result": True}

        with mock.patch.object(bot, "_api", side_effect=fake_api):
            processed = bot.poll_once(timeout=0)
        self.assertEqual(processed, 1)
        self.assertEqual(bot.offset, 11)
        methods = [method for method, _ in calls]
        self.assertIn("sendMessage", methods)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
