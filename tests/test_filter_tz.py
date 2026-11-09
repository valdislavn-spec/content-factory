"""filter_articles не падает на смеси naive/aware published_at."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from content_factory.config import Settings
from content_factory.models import Article, ChannelConfig
from content_factory.pipeline import filter_articles


class FilterTimezoneTest(unittest.TestCase):
    def test_mixed_timezones_are_ok(self):
        settings = Settings.load(load_env=False)
        channel = ChannelConfig(
            id="crypto-news",
            title="Crypto",
            topics=["bitcoin"],
            schedule=["09:00"],
            language="en",
            min_relevance=0.1,
        )
        naive = Article(
            id="a1",
            title="Bitcoin news",
            url="https://example.com/1",
            source_id="s",
            source_name="S",
            published_at=datetime(2026, 11, 8, 12, 0),
            text="bitcoin text",
        )
        aware = Article(
            id="a2",
            title="Bitcoin update",
            url="https://example.com/2",
            source_id="s",
            source_name="S",
            published_at=datetime(2026, 11, 8, 13, 0, tzinfo=timezone.utc),
            text="bitcoin text",
        )
        fixed_now = datetime(2026, 11, 8, 13, 30, tzinfo=timezone.utc)
        result = filter_articles(channel, [naive, aware], settings, now=fixed_now)
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
