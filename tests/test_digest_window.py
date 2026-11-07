"""Сводка за период: окно от прошлого поста и лимит новостей."""

from __future__ import annotations

import unittest
from datetime import timedelta

from content_factory.config import Settings
from content_factory.models import Analysis, Article, ChannelConfig, StoryCluster, utcnow
from content_factory.nlp.generator import generate_digest
from content_factory.pipeline import digest_window_clusters


def _cluster(cluster_id: str, title: str, published_at) -> StoryCluster:
    article = Article(
        id="a-" + cluster_id,
        title=title,
        url="https://example.com/" + cluster_id,
        source_id="test",
        source_name="Test",
        published_at=published_at,
        text=title + " Details of the story with enough text for a digest item." * 3,
        language="en",
    )
    return StoryCluster(id=cluster_id, title=title, articles=[article])


class DigestWindowTest(unittest.TestCase):
    def test_only_clusters_newer_than_last_post(self):
        now = utcnow()
        old = _cluster("old", "Old story", now - timedelta(hours=3))
        new = _cluster("new", "Fresh story", now - timedelta(minutes=10))
        selected = digest_window_clusters([old, new], now - timedelta(hours=1))
        self.assertEqual([cluster.id for cluster in selected], ["new"])

    def test_overlap_keeps_borderline_story(self):
        now = utcnow()
        borderline = _cluster("edge", "Edge story", now - timedelta(minutes=65))
        selected = digest_window_clusters([borderline], now - timedelta(hours=1), overlap_minutes=15)
        self.assertEqual([cluster.id for cluster in selected], ["edge"])

    def test_first_run_returns_all(self):
        now = utcnow()
        clusters = [_cluster("a", "A", now), _cluster("b", "B", now)]
        self.assertEqual(len(digest_window_clusters(clusters, None)), 2)


class DigestCapTest(unittest.TestCase):
    def test_digest_respects_digest_max_items(self):
        settings = Settings.load(load_env=False)
        settings.raw["pipeline"]["digest_max_items"] = 2
        now = utcnow()
        items = [
            (_cluster(f"c{i}", f"Story {i}", now - timedelta(minutes=i)), Analysis())
            for i in range(4)
        ]
        channel = ChannelConfig(
            id="crypto-news",
            title="Crypto & Blockchain",
            topics=["bitcoin"],
            schedule=["09:00", "10:00"],
            language="en",
            hashtags=["Crypto"],
        )
        post = generate_digest(items, channel, settings)
        self.assertEqual(post.meta["items_count"], 2)


if __name__ == "__main__":
    unittest.main()
