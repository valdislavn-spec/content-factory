"""Тесты защиты от повторов: опубликованные источники и кулдаун рекапа."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from content_factory.models import Article, GeneratedPost, StoryCluster
from content_factory.pipeline import _cluster_published, _recap_from_posts
from content_factory.storage import Storage


class DedupGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.tmp.name) / "factory.sqlite3")

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def _channel(self):
        return SimpleNamespace(
            id="test-ai",
            title="AI News",
            topics=["ai"],
            hashtags=["#AI"],
            language="en",
        )

    def _settings(self):
        return SimpleNamespace(
            pipeline={
                "fallback_from_posts_hours": 72,
                "fallback_recap_cooldown_hours": 10,
            },
            publishers={},
            data_dir=Path(self.tmp.name) / "data",
        )

    def _save_post(self, post_id: str, url: str, meta=None) -> None:
        self.storage.save_post(
            GeneratedPost(
                id=post_id,
                channel_id="test-ai",
                cluster_id="c1",
                format="story",
                text="<b>OpenAI ships GPT-5</b>\n\nOpenAI ships GPT-5 with a larger context window. The model is available through the API.",
                sources=[{"title": "Example", "url": url, "source": "Example"}],
                hashtags=["#AI"],
                meta=meta or {},
            )
        )

    def test_recent_post_sources_returns_published_urls(self):
        self._save_post("post-1", "https://example.com/a")
        urls = self.storage.recent_post_sources("test-ai", hours=72)
        self.assertEqual(urls, ["https://example.com/a"])

    def test_cluster_published_by_article_url(self):
        self._save_post("post-1", "https://example.com/a")
        from content_factory.utils import url_hash

        published = {url_hash("https://example.com/a")}
        article = Article(
            id="art-1",
            title="OpenAI ships GPT-5",
            url="https://example.com/a",
            source_id="example",
            source_name="Example",
            published_at=None,
        )
        cluster = StoryCluster(id="c1", title="OpenAI ships GPT-5", articles=[article])
        self.assertTrue(_cluster_published(cluster, published))
        self.assertFalse(_cluster_published(cluster, {url_hash("https://example.com/other")}))

    def test_recap_is_skipped_during_cooldown(self):
        self._save_post("recap-1", "https://example.com/a", meta={"fallback": True})
        recap = _recap_from_posts(self._channel(), self.storage, self._settings(), slot="09:00")
        self.assertIsNone(recap)


if __name__ == "__main__":
    unittest.main()
