"""ES-канал про спорт: аналитика и ставки добавлены в существующий futbol-es."""

from __future__ import annotations

import unittest

from content_factory.config import Settings, load_channels


class EsBettingConfigTest(unittest.TestCase):
    def setUp(self):
        channels = {
            channel.id: channel
            for channel in load_channels(Settings.load(load_env=False), path="config/channels.es.yaml")
        }
        self.channel = channels["futbol-es"]

    def test_title_reflects_analytics(self):
        self.assertIn("Analytics", self.channel.title)

    def test_language_and_strict_topics(self):
        self.assertEqual(self.channel.language, "es")
        self.assertTrue(self.channel.strict_topics)

    def test_betting_topics_added(self):
        topics = " ".join(self.channel.topics).lower()
        for word in ("apuestas", "cuotas", "probabilidad"):
            self.assertIn(word, topics)

    def test_betting_not_excluded(self):
        self.assertNotIn("apuestas", self.channel.exclude_keywords)

    def test_cta_requires_18_plus(self):
        self.assertIn("18+", self.channel.cta)

    def test_newsdata_betting_source(self):
        sources = [source for source in self.channel.sources if source.type == "newsdata"]
        self.assertTrue(sources, "нужен newsdata-источник про ставки")
        queries = " ".join(str(source.options.get("query", "")).lower() for source in sources)
        self.assertIn("apuestas", queries)


if __name__ == "__main__":
    unittest.main()
