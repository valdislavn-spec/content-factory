"""Тесты добровольной поддержки (donate, не paywall)."""

from __future__ import annotations

import html
import os
import re
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml

from content_factory.nlp.generator import _cta_block
from content_factory.support import (
    load_support_config,
    support_link,
    voluntary_support_block,
)


class FakeSettings:
    def __init__(self, root: Path):
        self.root = root
        self._raw = {"pipeline": {"cta": ""}}

    def get(self, dotted, default=None):
        node = self._raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


def make_channel(channel_id="crypto-news", language="en", cta=""):
    return SimpleNamespace(
        id=channel_id, language=language, cta=cta, hashtags=[], emoji=True
    )


def write_config(root: Path, **overrides):
    config = {
        "enabled": True,
        "mode": "voluntary",
        "url": "https://tribute.tg/donate?ref=post",
        "channels": [],
        "frequency": 1,
        "utm": {
            "source": "telegram",
            "medium": "post",
            "campaign": "voluntary_support",
        },
    }
    config.update(overrides)
    path = root / "config"
    path.mkdir(parents=True, exist_ok=True)
    (path / "support.yaml").write_text(
        yaml.safe_dump(config, allow_unicode=True), encoding="utf-8"
    )
    return config


class SupportConfigTests(unittest.TestCase):
    def test_disabled_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root, enabled=False)
            settings = FakeSettings(root)
            self.assertEqual(voluntary_support_block(make_channel(), settings), "")

    def test_empty_url_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root, url="")
            settings = FakeSettings(root)
            with mock.patch.dict(os.environ, {"SUPPORT_URL": ""}, clear=False):
                self.assertEqual(voluntary_support_block(make_channel(), settings), "")

    def test_env_url_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root, url="")
            settings = FakeSettings(root)
            with mock.patch.dict(os.environ, {"SUPPORT_URL": "https://boosty.to/donate"}):
                config = load_support_config(settings)
                block = voluntary_support_block(make_channel(), settings)
        self.assertIn("boosty.to", block)


class SupportBlockTests(unittest.TestCase):
    def test_english_block_and_utm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root)
            settings = FakeSettings(root)
            block = voluntary_support_block(make_channel(language="en"), settings, seed="Title")
        self.assertIn("<i>", block)
        self.assertIn("Support the project voluntarily", block)
        href = html.unescape(re.search(r'href="([^"]+)"', block).group(1))
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query)
        self.assertEqual(query["utm_source"], ["telegram"])
        self.assertEqual(query["utm_medium"], ["post"])
        self.assertEqual(query["utm_campaign"], ["voluntary_support"])
        self.assertEqual(query["utm_content"], ["crypto-news"])
        self.assertEqual(query["utm_term"], ["en"])
        self.assertEqual(query["ref"], ["post"])  # исходные параметры сохранены

    def test_languages(self):
        cases = {
            "en": "Support the project voluntarily",
            "es": "Apoya el proyecto de forma voluntaria",
            "ru": "Поддержать проект добровольно",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root)
            settings = FakeSettings(root)
            for language, expected in cases.items():
                with self.subTest(language=language):
                    block = voluntary_support_block(
                        make_channel(language=language), settings
                    )
                    self.assertIn(expected, block)

    def test_channels_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root, channels=["ai-news"])
            settings = FakeSettings(root)
            self.assertEqual(
                voluntary_support_block(make_channel("crypto-news"), settings), ""
            )
            self.assertIn(
                "Support the project voluntarily",
                voluntary_support_block(make_channel("ai-news"), settings),
            )

    def test_frequency_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root, frequency=2)
            settings = FakeSettings(root)
            results = [
                voluntary_support_block(make_channel(), settings, seed="seed-{}".format(i))
                for i in range(20)
            ]
        self.assertTrue(any(results), "хотя бы один пост должен содержать блок")
        self.assertTrue(any(not item for item in results), "часть постов — без блока")

    def test_custom_template_is_escaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root, text_en="Support <us>: {link}")
            settings = FakeSettings(root)
            block = voluntary_support_block(make_channel(language="en"), settings)
        self.assertIn("&lt;us&gt;", block)
        self.assertIn("<a href=", block)


class GeneratorIntegrationTests(unittest.TestCase):
    def test_generator_cta_includes_voluntary_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root)
            settings = FakeSettings(root)
            block = _cta_block(make_channel(), settings, "en", seed="Title")
        self.assertIn("Support the project voluntarily", block)
        self.assertIn("utm_source=telegram", html.unescape(block))  # UTM добавлен

    def test_generator_cta_without_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_config(root, enabled=False)
            settings = FakeSettings(root)
            self.assertEqual(_cta_block(make_channel(), settings, "en"), "")

    def test_support_link_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = write_config(root)
            link = support_link(make_channel(), FakeSettings(root), config=config)
        self.assertIn("utm_content=crypto-news", link)


if __name__ == "__main__":
    unittest.main()
