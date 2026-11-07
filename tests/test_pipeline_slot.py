"""Регрессия: при автопостинге слот не теряется из-за короткого первого сюжета."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from content_factory import pipeline as pipeline_module
from content_factory.config import Settings
from content_factory.models import Article, ChannelConfig, StoryCluster

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
LONG_TEXT = (
    "OpenAI released a new reasoning model with a two-million-token context window. "
    "The company said the model is available in the API starting today and costs "
    "30 percent less than the previous version. Developers can use it for long "
    "document analysis, coding assistants and multi-step agent workflows. "
    "The release also includes updated safety evaluations, according to the company. "
) * 2


def _cluster(cluster_id: str, title: str, text: str) -> StoryCluster:
    article = Article(
        id="a-" + cluster_id,
        title=title,
        url="https://example.com/" + cluster_id,
        source_id="test",
        source_name="Test",
        published_at=NOW,
        text=text,
        language="en",
    )
    return StoryCluster(id=cluster_id, title=title, articles=[article])


class FakeStorage:
    def get_posts(self, *args, **kwargs):
        return []

    def recent_post_titles(self, *args, **kwargs):
        return []


class SlotStarvationTest(unittest.TestCase):
    def test_skips_short_cluster_and_posts_from_next(self):
        settings = Settings.load(load_env=False)
        settings.raw["pipeline"]["post_mode"] = ""  # тест обычного (не digest) режима
        channel = ChannelConfig(
            id="tech-news",
            title="Technology News",
            topics=["technology"],
            language="en",
            formats=["story"],
            schedule=["00:00"],
            telegram_chat_id="@TechnologiesNews01",
            hashtags=["#Tech"],
        )
        short = _cluster("short", "Too short", "tiny text")
        good = _cluster("good", "OpenAI releases new model", LONG_TEXT)
        posts, errors = pipeline_module.generate_posts(
            channel, [short, good], settings, FakeStorage(), llm=None, max_posts=1
        )
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].cluster_id, "good")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
