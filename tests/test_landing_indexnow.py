"""Тесты лендинга каналов и IndexNow-пинга (без сети)."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from content_factory.config import Settings, load_network_channels
from content_factory.integrations.indexnow import (
    IndexNowError,
    build_payload,
    ensure_key_file,
    ping,
    sitemap_urls,
    validate_key,
)
from content_factory.integrations.landing import build_landing, build_sitemap, public_url


class LandingBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        base = Settings.load(load_env=False)
        raw = copy.deepcopy(base.raw)
        raw["app"]["data_dir"] = str(self.root / "data")
        self.settings = Settings(
            root=base.root,
            raw=raw,
            settings_path=base.settings_path,
            channels_path=base.channels_path,
        )
        self.channels = load_network_channels(self.settings)  # EN + ES, без RU
        self.out = self.root / "landing"


class LandingTests(LandingBase):
    def test_only_network_channels_have_public_urls(self):
        urls = {channel.id: public_url(channel) for channel in self.channels}
        self.assertEqual(urls["ai-news"], "https://t.me/AINEWS0007")
        self.assertEqual(urls["crypto-news"], "https://t.me/HOOPY0007")
        self.assertEqual(urls["tech-ai-es"], "https://t.me/WORLDNews0007")
        # RU-каналов в сети нет
        self.assertNotIn("tech-ai", urls)

    def test_build_landing_pages_index_and_sitemap(self):
        result = build_landing(self.channels, self.out, base_url="https://example.github.io/cf")
        self.assertEqual(len(result["pages"]), 6)
        html = (self.out / "ai-news.html").read_text(encoding="utf-8")
        self.assertIn("https://t.me/AINEWS0007", html)
        self.assertIn("Открыть в Telegram", html)
        index = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn("US Sports News", index)
        sitemap = (self.out / "sitemap.xml").read_text(encoding="utf-8")
        for channel in self.channels:
            self.assertIn(f"https://example.github.io/cf/{channel.id}.html", sitemap)

    def test_sitemap_helper(self):
        sitemap = build_sitemap(self.channels, "https://example.github.io/cf/")
        self.assertNotIn("//cf//", sitemap)
        self.assertEqual(sitemap.count("<loc>"), 7)  # 6 каналов + index


class IndexNowTests(LandingBase):
    KEY = "abc123def4567890"

    def test_validate_key(self):
        self.assertEqual(validate_key(self.KEY), self.KEY)
        for bad in ("", "short", "ключ-с-кириллицей", "x" * 200):
            with self.assertRaises(IndexNowError):
                validate_key(bad)

    def test_payload_requires_host_and_urls(self):
        payload = build_payload("example.github.io", self.KEY, ["https://example.github.io/a.html"])
        self.assertEqual(payload["host"], "example.github.io")
        self.assertEqual(payload["key"], self.KEY)
        self.assertEqual(payload["urlList"], ["https://example.github.io/a.html"])
        with self.assertRaises(IndexNowError):
            build_payload("", self.KEY, ["https://x"])
        with self.assertRaises(IndexNowError):
            build_payload("host", self.KEY, [])

    def test_key_file_and_sitemap_urls(self):
        ensure_key_file(self.out, self.KEY)
        key_file = self.out / f"{self.KEY}.txt"
        self.assertTrue(key_file.is_file())
        self.assertEqual(key_file.read_text(encoding="utf-8"), self.KEY)
        build_landing(self.channels, self.out, base_url="https://example.github.io/cf")
        urls = sitemap_urls(self.out)
        self.assertEqual(len(urls), 7)

    def test_dry_run_returns_payload_without_network(self):
        result = ping("example.github.io", self.KEY, ["https://example.github.io/a.html"], dry_run=True)
        self.assertFalse(result["sent"])
        self.assertEqual(result["payload"]["urlList"], ["https://example.github.io/a.html"])

    def test_ping_sends_json(self):
        class FakeResponse:
            status = 200

            def read(self):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with mock.patch(
            "content_factory.integrations.indexnow.urllib.request.urlopen",
            return_value=FakeResponse(),
        ) as mocked:
            result = ping("example.github.io", self.KEY, ["https://example.github.io/a.html"])
        self.assertTrue(result["sent"])
        self.assertEqual(result["status"], 200)
        request = mocked.call_args.args[0]
        self.assertEqual(request.method, "POST")
        self.assertIn(b"urlList", request.data)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
