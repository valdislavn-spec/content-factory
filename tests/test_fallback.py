"""Тесты fallback-публикаций: канал не должен пропускать слот."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from content_factory.models import Article, ChannelConfig, GeneratedPost
from content_factory.pipeline import _recap_emoji, _recap_from_posts
from content_factory.storage import Storage


class FallbackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.tmp.name) / "factory.sqlite3")

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def _channel(self, channel_id="test-ai", title="AI News", topics=None):
        return ChannelConfig(
            id=channel_id,
            title=title,
            topics=topics or ["ai", "openai"],
            hashtags=["#AI"],
            language="en",
        )

    def _settings(self):
        return SimpleNamespace(
            pipeline={"fallback_from_posts_hours": 72},
            publishers={},
            data_dir=Path(self.tmp.name) / "data",
        )

    def test_recent_articles_returns_history(self):
        self.storage.save_articles(
            "test-ai",
            [
                Article(
                    id="a1",
                    title="OpenAI ships GPT-5",
                    url="https://example.com/1",
                    source_id="example",
                    source_name="Example",
                    published_at=None,
                    summary="OpenAI ships GPT-5.",
                    text="OpenAI ships GPT-5 with a larger context window.",
                )
            ],
        )
        items = self.storage.recent_articles("test-ai", hours=48)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "OpenAI ships GPT-5")

    def test_recap_from_recent_posts(self):
        self.storage.save_post(
            GeneratedPost(
                id="post-1",
                channel_id="test-ai",
                cluster_id="c1",
                format="story",
                text=(
                    "<b>OpenAI ships GPT-5</b>\n\n"
                    "OpenAI ships GPT-5 with a larger context window. "
                    "The model is available through the API."
                ),
                hashtags=["#AI"],
            )
        )
        recap = _recap_from_posts(
            self._channel(), self.storage, self._settings(), slot="09:00"
        )
        self.assertIsNotNone(recap)
        self.assertTrue(recap.meta.get("fallback"))
        self.assertIn("<b>", recap.text)
        self.assertIn("AI News", recap.text)
        self.assertNotIn("1️⃣", recap.text)

    def test_recap_without_materials_is_none(self):
        recap = _recap_from_posts(
            self._channel(), self.storage, self._settings(), slot="09:00"
        )
        self.assertIsNone(recap)

    def test_recap_emoji_by_theme(self):
        self.assertEqual(_recap_emoji(self._channel()), "🤖")
        self.assertEqual(_recap_emoji(self._channel("crypto-news", "Crypto & Blockchain")), "🪙")
        self.assertEqual(_recap_emoji(self._channel("futbol-es", "Fútbol en Español")), "⚽")


if __name__ == "__main__":
    unittest.main()
