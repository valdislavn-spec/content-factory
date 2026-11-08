"""Tumblr-дайджест: текст, аналитика и дневной бюджет (без сети)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import tumblr_digest  # noqa: E402

from content_factory.models import Article  # noqa: E402


def _article(title: str, source: str = "Test", n: int = 1, text: str = "some text") -> Article:
    return Article(
        id=f"a{n}",
        title=title,
        url=f"https://example.com/{n}",
        source_id="s",
        source_name=source,
        published_at=datetime.now(timezone.utc),
        text=text,
        summary=text,
    )


class TumblrDigestTests(unittest.TestCase):
    def test_build_text_has_items_sources_and_analytics(self):
        items = [
            ("crypto-news", _article("Bitcoin hits new high", "CoinDesk", 1, "Bitcoin rallied past 100k today.")),
            ("ai-news", _article("Nvidia earnings beat", "The Verge", 2, "Nvidia reported strong quarterly results.")),
            ("sport-news", _article("Lakers win again", "ESPN", 3, "The Lakers won their fourth straight game.")),
        ]
        text = tumblr_digest.build_text(items, hours=5)
        self.assertIn("подробный дайджест новостей за 5 ч", text)
        self.assertIn("1. Bitcoin hits new high", text)
        self.assertIn("Источник: CoinDesk", text)
        self.assertIn("https://example.com/1", text)
        self.assertIn("Аналитика:", text)
        self.assertIn("По темам:", text)
        self.assertIn("Новостей в сводке: 3", text)
        self.assertLessEqual(len(text), tumblr_digest.MAX_TEXT)

    def test_build_post_meta(self):
        items = [("ai-news", _article("AI news", "Verge", 1))]
        post = tumblr_digest.build_post(items, hours=5)
        self.assertEqual(post.format, "digest")
        self.assertEqual(post.channel_id, "tumblr-digest")
        self.assertIn("news", post.hashtags)
        self.assertEqual(post.sources[0]["url"], "https://example.com/1")

    def test_digest_channel_has_no_telegram_link(self):
        channel = tumblr_digest.digest_channel()
        self.assertEqual(channel.description, "")
        self.assertEqual(channel.id, "tumblr-digest")

    def test_budget_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            budget = Path(tmp) / "tumblr_usage.json"
            with mock.patch.object(tumblr_digest, "BUDGET", budget):
                self.assertEqual(tumblr_digest.budget_left(5), 5)
                tumblr_digest.spend_budget()
                self.assertEqual(tumblr_digest.budget_left(5), 4)
                data = json.loads(budget.read_text())
                self.assertEqual(data["count"], 1)

    def test_collect_selection_is_round_robin(self):
        # без сети: подменяем fetch на пустой список → collect вернёт []
        with mock.patch("tumblr_digest.get_adapter") as adapter:
            adapter.return_value.fetch.return_value = []
            self.assertEqual(tumblr_digest.collect(5, 3), [])


if __name__ == "__main__":
    unittest.main()
