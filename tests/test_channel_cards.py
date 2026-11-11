"""Тесты карточек каналов: манифест, подписи, travel-ссылки, рендер."""
import json
import unittest

from content_factory.channel_cards import (
    CARDS,
    TRAVEL_OFFERS,
    build_caption,
    card_manifest,
    get_card,
    travel_offer,
)


class ChannelCardsTest(unittest.TestCase):
    def test_all_six_channels_have_cards(self):
        self.assertEqual(set(CARDS), {
            "crypto-news", "ai-news", "sport-news",
            "crypto-es", "tech-ai-es", "futbol-es",
        })

    def test_manifest_has_public_image_urls_and_captions(self):
        rows = card_manifest(public_base="https://example.test")
        self.assertEqual(len(rows), 6)
        for row in rows:
            self.assertTrue(row["image_url"].startswith("https://raw.githubusercontent.com/"))
            self.assertIn("t.me/", row["telegram_url"])
            self.assertIn("links-tracker.valdislav-n.workers.dev", row["travel"]["url"])
            for platform in ("mastodon", "akkoma", "x", "bluesky", "facebook", "tumblr", "pinterest"):
                self.assertTrue(row["captions"][platform].strip())

    def test_caption_limits_and_links(self):
        card = get_card("crypto-news")
        x_caption = build_caption(card, "x")
        self.assertLessEqual(len(x_caption), 270)
        self.assertIn("t.me/HOOPY0007", x_caption)
        self.assertIn("Flights →", x_caption)

        bluesky = build_caption(card, "bluesky")
        self.assertLessEqual(len(bluesky), 290)

        mastodon = build_caption(card, "mastodon")
        self.assertLessEqual(len(mastodon), 480)
        self.assertIn("Ad", mastodon)

    def test_spanish_caption_is_localized(self):
        card = get_card("tech-ai-es")
        caption = build_caption(card, "mastodon", travel_offer(1))
        self.assertIn("Seguir en Telegram", caption)
        self.assertIn("Anuncio", caption)
        self.assertIn("t.me/WORLDNews0007", caption)

    def test_travel_rotation(self):
        self.assertEqual(travel_offer(0)["name"], "Aviasales")
        self.assertEqual(travel_offer(len(TRAVEL_OFFERS))["name"], TRAVEL_OFFERS[0]["name"])

    def test_render_card_size(self):
        try:
            from PIL import Image  # noqa: F401
        except Exception as exc:  # noqa: BLE001 - локальный Pillow бывает сломан подписью
            self.skipTest("Pillow недоступен: {}".format(exc))
        from content_factory.channel_cards import render_card

        image = render_card(get_card("ai-news"), size=(500, 750))
        self.assertEqual(image.size, (500, 750))
        self.assertEqual(image.mode, "RGB")


if __name__ == "__main__":
    unittest.main()
