"""Гейты качества контента: язык поста и строгая тематика для trusted-источников."""

from __future__ import annotations

import unittest

from content_factory.config import Settings
from content_factory.models import Article, ChannelConfig, GeneratedPost, SourceConfig, utcnow
from content_factory.pipeline import filter_articles, post_language_ok, quality_issues

EN_TEXT = (
    "Bitcoin rose 5% after the SEC approved a new exchange-traded fund for "
    "institutional investors in the United States. Analysts expect more flows "
    "into the market and a new wave of product launches next quarter."
)
ES_TEXT = (
    "El bitcoin subió un 5% después de que la SEC aprobara el nuevo fondo "
    "cotizado para inversores institucionales en Estados Unidos. Los analistas "
    "esperan más flujos hacia el mercado y una nueva ola de productos."
)
CRICKET = (
    "Usman Khawaja claims the entire Australia team knew of the 2014 ball "
    "tampering plot before the third Test against South Africa in Cape Town."
)


def _article(title: str, text: str, source_id: str = "guardian") -> Article:
    return Article(
        id="a1",
        title=title,
        url="https://example.com/a1",
        source_id=source_id,
        source_name="The Guardian",
        published_at=utcnow(),
        text=text,
        language="en",
    )


def _channel(strict: bool) -> ChannelConfig:
    source = SourceConfig(
        id="guardian",
        type="rss",
        url="https://example.com/rss",
        name="The Guardian",
        options={"trust": True},
    )
    return ChannelConfig(
        id="sport-news",
        title="US Sports News",
        topics=["nfl", "nba", "mlb", "nhl"],
        sources=[source],
        schedule=["09:00"],
        strict_topics=strict,
        min_relevance=0.18,
        language="en",
    )


class LanguageGateTest(unittest.TestCase):
    def test_english_post_rejected_in_spanish_channel(self):
        self.assertFalse(post_language_ok(EN_TEXT, "es"))

    def test_spanish_post_ok_in_spanish_channel(self):
        self.assertTrue(post_language_ok(ES_TEXT, "es"))

    def test_english_post_ok_in_english_channel(self):
        self.assertTrue(post_language_ok(EN_TEXT, "en"))

    def test_short_text_not_checked(self):
        self.assertTrue(post_language_ok("Hola", "es"))

    def test_quality_issues_flags_wrong_language(self):
        settings = Settings.load(load_env=False)
        channel = _channel(strict=False)
        channel.language = "es"
        post = GeneratedPost(
            id="p1",
            channel_id="sport-news",
            cluster_id="c1",
            format="story",
            text=EN_TEXT + " " + EN_TEXT,
            sources=[{"title": "x", "url": "https://example.com"}],
        )
        issues = quality_issues(post, channel, settings)
        self.assertTrue(any("язык" in issue for issue in issues), issues)


class StrictTopicsTest(unittest.TestCase):
    def setUp(self):
        self.settings = Settings.load(load_env=False)

    def test_trusted_source_offtopic_rejected_with_strict_topics(self):
        channel = _channel(strict=True)
        kept = filter_articles(channel, [_article("Ball tampering plot", CRICKET)], self.settings)
        self.assertEqual(kept, [])

    def test_trusted_source_offtopic_kept_without_strict_topics(self):
        channel = _channel(strict=False)
        kept = filter_articles(channel, [_article("Ball tampering plot", CRICKET)], self.settings)
        self.assertEqual(len(kept), 1)

    def test_relevant_topic_kept_with_strict_topics(self):
        channel = _channel(strict=True)
        article = _article(
            "NFL trade: star quarterback moves to a new team",
            "The NFL quarterback was traded after the season ended.",
        )
        kept = filter_articles(channel, [article], self.settings)
        self.assertEqual(len(kept), 1)


if __name__ == "__main__":
    unittest.main()
