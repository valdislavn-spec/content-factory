"""Тесты кураторских источников: config/sources.curated.yaml подмешивается в каналы."""
from __future__ import annotations

import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from content_factory.config import Settings, load_channels
from content_factory.utils import ConfigError

MINIMAL_SETTINGS = """
app:
  data_dir: data
  db_path: data/factory.sqlite3
  dry_run: true
pipeline:
  lookback_hours: 30
llm:
  provider: extractive
"""

MINIMAL_CHANNELS = """
channels:
  - id: test-channel
    title: "Тестовый канал"
    telegram_chat_id: "@test"
    topics: [технологи]
    schedule: ["09:00"]
    formats: [story]
    sources:
      - id: inline-feed
        type: rss
        url: https://example.com/rss
        name: Прямой источник
"""

CURATED = """
channels:
  test-channel:
    - id: curated-feed
      type: rss
      url: https://curated.example.com/feed
      name: Кураторский источник
      weight: 1.2
      options:
        max_items: 5
  "*":
    - id: common-feed
      type: rss
      url: https://common.example.com/feed
      name: Общий источник
"""


class CuratedSourcesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / "config").mkdir()
        (self.root / "config" / "settings.yaml").write_text(MINIMAL_SETTINGS, encoding="utf-8")
        (self.root / "config" / "channels.yaml").write_text(MINIMAL_CHANNELS, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()
        os.environ.pop("CONTENT_FACTORY_CURATED_SOURCES", None)

    def _write_curated(self, content: str = CURATED) -> Path:
        path = self.root / "config" / "sources.curated.yaml"
        path.write_text(textwrap.dedent(content), encoding="utf-8")
        return path

    def test_curated_sources_are_merged(self) -> None:
        self._write_curated()
        channels = load_channels(Settings.load(root=self.root))
        self.assertEqual(len(channels), 1)
        ids = [src.id for src in channels[0].sources]
        self.assertEqual(ids, ["inline-feed", "curated-feed", "common-feed"])
        curated = channels[0].sources[1]
        self.assertEqual(curated.weight, 1.2)
        self.assertEqual(curated.options, {"max_items": 5})

    def test_curated_without_file_is_noop(self) -> None:
        channels = load_channels(Settings.load(root=self.root))
        self.assertEqual([src.id for src in channels[0].sources], ["inline-feed"])

    def test_curated_deduplicates_by_url(self) -> None:
        self._write_curated(
            """
            channels:
              test-channel:
                - id: duplicate-url
                  type: rss
                  url: https://example.com/rss
                - id: duplicate-id
                  type: rss
                  url: https://other.example.com/feed
            """
        )
        # второй источник с тем же id, что уже есть в канале
        path = self.root / "config" / "sources.curated.yaml"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "url: https://other.example.com/feed",
                "url: https://other.example.com/feed\n      name: Другой",
            ),
            encoding="utf-8",
        )
        channels = load_channels(Settings.load(root=self.root))
        urls = [src.url for src in channels[0].sources]
        self.assertEqual(urls.count("https://example.com/rss"), 1)
        self.assertIn("https://other.example.com/feed", urls)

    def test_env_override_path(self) -> None:
        custom = self.root / "config" / "custom-curated.yaml"
        custom.write_text(
            "channels:\n  test-channel:\n    - id: env-feed\n      type: rss\n      url: https://env.example.com/feed\n",
            encoding="utf-8",
        )
        os.environ["CONTENT_FACTORY_CURATED_SOURCES"] = str(custom)
        channels = load_channels(Settings.load(root=self.root))
        self.assertIn("env-feed", [src.id for src in channels[0].sources])

    def test_invalid_curated_structure_raises(self) -> None:
        self._write_curated("channels:\n  test-channel: not-a-list\n")
        with self.assertRaises(ConfigError):
            load_channels(Settings.load(root=self.root))

    def test_wildcard_applies_to_every_channel(self) -> None:
        self._write_curated('channels:\n  "*":\n    - id: common\n      type: rss\n      url: https://common.example.com/feed\n')
        channels = load_channels(Settings.load(root=self.root))
        self.assertIn("common", [src.id for src in channels[0].sources])


if __name__ == "__main__":
    unittest.main()
