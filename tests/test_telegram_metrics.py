"""Тесты Telegram-метрик: посты, ER, storage, отчёт."""

from __future__ import annotations

import copy
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from content_factory.analytics.report import build_report, render_html, render_markdown
from content_factory.analytics.telegram_metrics import (
    collect_channel_telegram_metrics,
    fetch_channel_posts,
    message_to_post,
    summarize_posts,
)
from content_factory.config import DEFAULT_SETTINGS, Settings
from content_factory.models import ChannelConfig
from content_factory.storage import Storage


class Reaction:
    def __init__(self, count: int) -> None:
        self.count = count


class Reactions:
    def __init__(self, *counts: int) -> None:
        self.results = [Reaction(count) for count in counts]


class Message:
    def __init__(
        self,
        message_id: int,
        views: int = 100,
        forwards: int = 2,
        reactions: Reactions | None = None,
        text: str = "<b>Тестовый пост</b>",
        date: datetime | None = None,
    ) -> None:
        self.id = message_id
        self.views = views
        self.forwards = forwards
        self.reactions = reactions
        self.message = text
        self.date = date or datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
        self.replies = None


class TelegramMetricsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        raw = copy.deepcopy(DEFAULT_SETTINGS)
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
            root=self.root,
            raw=raw,
            settings_path=self.root / "config" / "settings.yaml",
            channels_path=self.root / "config" / "channels.yaml",
        )
        self.storage = Storage(self.settings.db_path)
        self.addCleanup(self.storage.close)
        self.channel = ChannelConfig(
            id="tech-ai",
            title="Технологии и ИИ",
            telegram_chat_id="@test_channel",
        )


class PostMetricsTests(TelegramMetricsTestCase):
    def test_message_to_post(self) -> None:
        message = Message(42, views=1500, forwards=7, reactions=Reactions(10, 5))
        post = message_to_post(message, self.channel, username="test_channel")
        self.assertEqual(post["message_id"], 42)
        self.assertEqual(post["views"], 1500)
        self.assertEqual(post["forwards"], 7)
        self.assertEqual(post["reactions"], 15)
        self.assertEqual(post["url"], "https://t.me/test_channel/42")
        self.assertIn("Тестовый пост", post["text_preview"])
        self.assertTrue(post["posted_at"])

    def test_summarize_posts(self) -> None:
        posts = [
            {"message_id": 1, "views": 100, "reactions": 5, "forwards": 1, "replies": 0},
            {"message_id": 2, "views": 200, "reactions": 10, "forwards": 2, "replies": 1},
        ]
        summary = summarize_posts(posts)
        self.assertEqual(summary["posts_analyzed"], 2)
        self.assertEqual(summary["total_views"], 300)
        self.assertEqual(summary["avg_views"], 150.0)
        self.assertEqual(summary["total_reactions"], 15)
        self.assertEqual(summary["total_forwards"], 3)
        self.assertEqual(summary["er"], 6.0)  # 18/300*100
        self.assertEqual(summary["top_posts"][0]["message_id"], 2)

    def test_summarize_empty(self) -> None:
        summary = summarize_posts([])
        self.assertEqual(summary["posts_analyzed"], 0)
        self.assertEqual(summary["avg_views"], 0.0)
        self.assertEqual(summary["er"], 0.0)

    def test_fetch_without_keys_returns_empty(self) -> None:
        with mock.patch.dict(os.environ, {"TG_API_ID": "", "TG_API_HASH": ""}, clear=False):
            self.assertEqual(fetch_channel_posts(self.channel, self.settings, limit=5), [])


class StorageTests(TelegramMetricsTestCase):
    def test_save_upsert_and_read(self) -> None:
        posts = [
            {"message_id": 1, "posted_at": "2026-11-07T12:00:00+00:00", "views": 100,
             "forwards": 1, "reactions": 2, "replies": 0, "text_preview": "a", "url": ""},
        ]
        self.assertEqual(self.storage.save_telegram_posts("tech-ai", posts), 1)
        self.storage.save_telegram_posts(
            "tech-ai",
            [{"message_id": 1, "views": 150, "reactions": 3}],
        )
        rows = self.storage.telegram_posts("tech-ai", days=7)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["views"], 150)
        self.assertEqual(rows[0]["reactions"], 3)

        self.storage.save_telegram_channel_metrics(
            "tech-ai",
            {
                "subscribers": 1000,
                "posts_analyzed": 1,
                "total_views": 150,
                "avg_views": 150.0,
                "total_reactions": 3,
                "total_forwards": 1,
                "er": 2.67,
            },
        )
        latest = self.storage.latest_telegram_channel_metrics("tech-ai")
        self.assertIsNotNone(latest)
        self.assertEqual(latest["subscribers"], 1000)
        self.assertEqual(len(self.storage.telegram_channel_history("tech-ai", days=7)), 1)


class CollectTests(TelegramMetricsTestCase):
    def test_collect_with_mocked_sources(self) -> None:
        posts = [
            {"message_id": 1, "views": 100, "reactions": 5, "forwards": 1, "replies": 0,
             "posted_at": "", "text_preview": "", "url": ""},
            {"message_id": 2, "views": 200, "reactions": 10, "forwards": 2, "replies": 0,
             "posted_at": "", "text_preview": "", "url": ""},
        ]
        with mock.patch(
            "content_factory.analytics.telegram_metrics.fetch_channel_posts",
            return_value=posts,
        ), mock.patch(
            "content_factory.analytics.telegram_metrics.fetch_subscribers",
            return_value=500,
        ), mock.patch(
            "content_factory.analytics.telegram_metrics._telegram_token",
            return_value="123:token",
        ):
            summary = collect_channel_telegram_metrics(
                self.channel, self.settings, self.storage, limit=10
            )
        self.assertEqual(summary["subscribers"], 500)
        self.assertEqual(summary["posts_analyzed"], 2)
        self.assertEqual(summary["er"], 6.0)
        self.assertIsNotNone(self.storage.latest_telegram_channel_metrics("tech-ai"))
        self.assertEqual(len(self.storage.telegram_posts("tech-ai", days=7)), 2)

    def test_collect_without_posts(self) -> None:
        with mock.patch(
            "content_factory.analytics.telegram_metrics.fetch_channel_posts",
            return_value=[],
        ), mock.patch(
            "content_factory.analytics.telegram_metrics.fetch_subscribers",
            return_value=None,
        ), mock.patch(
            "content_factory.analytics.telegram_metrics._telegram_token",
            return_value="",
        ):
            summary = collect_channel_telegram_metrics(
                self.channel, self.settings, self.storage, limit=10
            )
        self.assertIsNone(summary["subscribers"])
        self.assertEqual(summary["posts_analyzed"], 0)
        self.assertEqual(summary["er"], 0.0)


class ReportTests(TelegramMetricsTestCase):
    def test_report_contains_telegram_section(self) -> None:
        self.storage.save_telegram_posts(
            "tech-ai",
            [
                {"message_id": 1, "posted_at": "2026-11-07T12:00:00+00:00", "views": 100,
                 "forwards": 1, "reactions": 2, "replies": 0, "text_preview": "a",
                 "url": "https://t.me/test_channel/1"},
            ],
        )
        self.storage.save_telegram_channel_metrics(
            "tech-ai",
            {
                "subscribers": 1000,
                "posts_analyzed": 1,
                "total_views": 100,
                "avg_views": 100.0,
                "total_reactions": 2,
                "total_forwards": 1,
                "er": 3.0,
            },
        )
        data = build_report(self.settings, self.storage, [self.channel], days=7)
        self.assertTrue(data["telegram"]["has_data"])
        self.assertEqual(data["telegram"]["totals"]["subscribers"], 1000)
        html = render_html(data)
        markdown = render_markdown(data)
        self.assertIn("Telegram-метрики", html)
        self.assertIn("Telegram-метрики", markdown)
        self.assertIn("ER", html)
        self.assertIn("Технологии и ИИ", html)
        self.assertIn("3.0%", markdown)


if __name__ == "__main__":
    unittest.main()
