"""Тесты брендовых пинов/OG для GitHub Pages (без рендера)."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import scripts.build_brand_pages as pages


class HelperTests(unittest.TestCase):
    def test_channel_partner_from_affiliate_config(self):
        channel = SimpleNamespace(id="crypto-news", affiliate={
            "enabled": True, "tracked_url": "https://links.example/r/bingx",
            "link": "https://bingxdao.com/invite/X/"})
        with mock.patch.object(pages, "_ready_partners", return_value=[]):
            partner = pages.channel_partner(channel)
        self.assertIsNotNone(partner)
        self.assertEqual(partner["url"], "https://links.example/r/bingx")

    def test_channel_partner_rotation(self):
        channel = SimpleNamespace(id="sport-news", affiliate={})
        ready = [{"key": "mylead", "title": "MyLead", "url": "https://mylead.global/r/x",
                  "age_restricted": False},
                 {"key": "collaborator", "title": "Collaborator.pro",
                  "url": "https://collaborator.pro/x", "age_restricted": False}]
        with mock.patch.object(pages, "_ready_partners", return_value=ready):
            self.assertEqual(pages.channel_partner(channel, 0)["key"], "mylead")
            self.assertEqual(pages.channel_partner(channel, 1)["key"], "collaborator")

    def test_page_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            en = Path(tmp) / "en.html"; en.write_text('<html lang="en"><head></head></html>')
            es = Path(tmp) / "es.html"; es.write_text('<html lang="es"><head></head></html>')
            self.assertEqual(pages._page_language(en), "en")
            self.assertEqual(pages._page_language(es), "es")

    def test_patch_og_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "p.html"
            page.write_text('<html><head><title>T</title>'
                            '<meta name="twitter:card" content="summary"></head><body></body></html>')
            self.assertTrue(pages._patch_og_meta(page, "https://x/og.png"))
            text = page.read_text()
            self.assertIn('property="og:image" content="https://x/og.png"', text)
            self.assertIn("summary_large_image", text)
            self.assertIn('name="twitter:image"', text)
            # повторный вызов не дублирует
            self.assertFalse(pages._patch_og_meta(page, "https://x/og.png"))

    def test_patch_og_meta_no_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "bad.html"; page.write_text("no head")
            self.assertFalse(pages._patch_og_meta(page, "https://x/og.png"))

    def test_manifest_format(self):
        # структура манифеста, которую читает PinterestPublisher._manifest_url
        self.assertIn("channels", "channels:\n  ai-news: 'https://x'\n")


if __name__ == "__main__":
    unittest.main()
