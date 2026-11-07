"""Тесты пакета продвижения: карточки каталогов, Markdown/JSON, фолбэки."""
from __future__ import annotations

import json
import unittest

from content_factory.models import ChannelConfig
from content_factory.promo import (
    CATALOGS,
    DESCRIPTIONS,
    build_cards,
    cards_to_json,
    cards_to_markdown,
    channel_url,
)

CHANNELS = [
    ("sport-news", "US Sports News", "en", "NFL, NBA, MLB and more."),
    ("ai-news", "AI News", "en", "AI for a US audience."),
    ("crypto-news", "Crypto & Blockchain", "en", "US crypto news."),
    ("tech-ai-es", "ES AI News", "es", "IA en español."),
    ("crypto-es", "ES Crypto & Blockchain", "es", "Cripto en español."),
    ("futbol-es", "ES Sports News", "es", "Deporte en español."),
]

USERNAMES = {
    "sport-news": "SPORTNews0007",
    "ai-news": "AINEWS0007",
    "crypto-news": "HOOPY0007",
    "tech-ai-es": "WORLDNews0007",
    "crypto-es": "TechnologiesNews01",
    "futbol-es": "SPORTSAnalytics007",
}


def make_channel(channel_id: str, title: str, language: str, description: str) -> ChannelConfig:
    return ChannelConfig(
        id=channel_id,
        title=title,
        language=language,
        description=description,
        telegram_chat_id="-1000000000000",
        topics=["тема"],
        hashtags=["#test"],
    )


class PromoCardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.channels = [
            make_channel(channel_id, title, language, description)
            for channel_id, title, language, description in CHANNELS
        ]

    def test_all_channels_get_cards(self) -> None:
        cards = build_cards(self.channels, USERNAMES, contact="@owner")
        self.assertEqual([card["id"] for card in cards], [item[0] for item in CHANNELS])
        for card in cards:
            self.assertTrue(card["title"])
            self.assertEqual(card["contact"], "@owner")
            self.assertTrue(card["url"].startswith("https://t.me/"))
            self.assertIn(card["language"], ("en", "es"))
            self.assertTrue(card["category"])
            self.assertTrue(card["keywords"])
            self.assertTrue(card["hashtags"])

    def test_curated_descriptions_fit_catalog_limits(self) -> None:
        cards = build_cards(self.channels, USERNAMES)
        for card in cards:
            self.assertGreaterEqual(len(card["description"]), 120, card["id"])
            self.assertLessEqual(len(card["description"]), 200, card["id"])

    def test_curated_description_used_for_known_channels(self) -> None:
        cards = {card["id"]: card for card in build_cards(self.channels, USERNAMES)}
        for channel_id, text in DESCRIPTIONS.items():
            self.assertIn(text[:40], cards[channel_id]["description"])

    def test_unknown_channel_falls_back_to_config_description(self) -> None:
        channel = make_channel("new-channel", "Новый канал", "ru", "Короткое описание канала")
        card = build_cards([channel], {})[0]
        self.assertTrue(card["description"].startswith("Короткое описание канала"))
        self.assertEqual(card["username"], "")
        self.assertEqual(card["url"], "")

    def test_missing_username_is_marked_in_markdown(self) -> None:
        channel = make_channel("ai-news", "AI News", "en", "AI")
        markdown = cards_to_markdown(build_cards([channel], {}))
        self.assertIn("username не найден", markdown)

    def test_markdown_contains_catalogs_and_cards(self) -> None:
        cards = build_cards(self.channels, USERNAMES)
        markdown = cards_to_markdown(cards)
        self.assertIn("Пакет для каталогов", markdown)
        self.assertIn("TGStat", markdown)
        for card in cards:
            self.assertIn(card["title"], markdown)
            self.assertIn("@" + card["username"], markdown)
        self.assertEqual(len(CATALOGS), markdown.count("| ["))

    def test_json_is_serializable_and_complete(self) -> None:
        payload = cards_to_json(build_cards(self.channels, USERNAMES))
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertIn("SPORTNews0007", dumped)
        self.assertEqual(len(payload["channels"]), 6)
        self.assertEqual(len(payload["catalogs"]), len(CATALOGS))

    def test_channel_url(self) -> None:
        self.assertEqual(channel_url("@test"), "https://t.me/test")
        self.assertEqual(channel_url("test"), "https://t.me/test")
        self.assertEqual(channel_url(""), "")


if __name__ == "__main__":
    unittest.main()
