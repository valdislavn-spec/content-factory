"""Тесты конфигурации: валидация, EN/ES каналы, переопределение chat_id из env."""
from __future__ import annotations

import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from content_factory.config import ConfigError, Settings, load_channels
from content_factory.utils import ConfigError as UtilsConfigError


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
    schedule: ["09:00", "18:00"]
    formats: [story, digest]
    hashtags: [тест]
    sources:
      - id: test-feed
        type: rss
        url: https://example.com/rss
        name: Пример
"""


class ConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / "config").mkdir()
        (self.root / "config" / "settings.yaml").write_text(MINIMAL_SETTINGS, encoding="utf-8")
        (self.root / "config" / "channels.yaml").write_text(MINIMAL_CHANNELS, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()
        for key in list(os.environ):
            if key.startswith("TELEGRAM_CHAT_ID_TEST"):
                os.environ.pop(key, None)

    def test_load_settings(self) -> None:
        settings = Settings.load(root=self.root)
        self.assertEqual(settings.app.get("dry_run"), True)
        self.assertEqual(settings.db_path, self.root / "data" / "factory.sqlite3")
        self.assertEqual(settings.llm.get("provider"), "extractive")

    def test_load_channel(self) -> None:
        channels = load_channels(Settings.load(root=self.root))
        self.assertEqual(len(channels), 1)
        channel = channels[0]
        self.assertEqual(channel.id, "test-channel")
        self.assertEqual(channel.schedule, ["09:00", "18:00"])
        self.assertEqual(channel.telegram_chat_id, "@test")
        self.assertEqual(channel.sources[0].type, "rss")
        self.assertEqual(channel.formats, ["story", "digest"])

    def test_env_overrides_chat_id(self) -> None:
        os.environ["TELEGRAM_CHAT_ID_TEST_CHANNEL"] = "-1001234567890"
        channels = load_channels(Settings.load(root=self.root))
        self.assertEqual(channels[0].telegram_chat_id, "-1001234567890")

    def test_invalid_schedule_raises(self) -> None:
        path = self.root / "config" / "channels.yaml"
        path.write_text(
            textwrap.dedent(
                MINIMAL_CHANNELS.replace('"09:00", "18:00"', '"09:00", "25:00"')
            ),
            encoding="utf-8",
        )
        with self.assertRaises(ConfigError):
            load_channels(Settings.load(root=self.root))

    def test_invalid_source_type_raises(self) -> None:
        path = self.root / "config" / "channels.yaml"
        path.write_text(
            MINIMAL_CHANNELS.replace("type: rss", "type: неизвестный"),
            encoding="utf-8",
        )
        with self.assertRaises(ConfigError):
            load_channels(Settings.load(root=self.root))

    def test_bad_provider_raises(self) -> None:
        (self.root / "config" / "settings.yaml").write_text(
            MINIMAL_SETTINGS.replace("provider: extractive", "provider: no-such-provider"),
            encoding="utf-8",
        )
        with self.assertRaises(ConfigError):
            Settings.load(root=self.root)

    def test_missing_channels_file(self) -> None:
        (self.root / "config" / "channels.yaml").unlink()
        with self.assertRaises(ConfigError):
            load_channels(Settings.load(root=self.root))

    def test_real_en_and_es_channels(self) -> None:
        """EN и ES конфиги: по 3 валидных канала с числовыми ID и источниками."""
        project_root = Path(__file__).resolve().parents[1]
        en_channels = load_channels(Settings.load(root=project_root))
        self.assertEqual(
            {c.id for c in en_channels},
            {"sport-news", "ai-news", "crypto-news"},
        )
        from unittest import mock

        with mock.patch.dict(os.environ, {"CONTENT_FACTORY_CHANNELS": "config/channels.es.yaml"}):
            es_channels = load_channels(Settings.load(root=project_root))
        self.assertEqual(
            {c.id for c in es_channels},
            {"tech-ai-es", "crypto-es", "futbol-es"},
        )
        for channels in (en_channels, es_channels):
            for channel in channels:
                self.assertTrue(channel.topics, channel.id)
                self.assertTrue(channel.sources, channel.id)
                self.assertTrue(channel.schedule, channel.id)
                for slot in channel.schedule:
                    from content_factory.utils import parse_hhmm

                    parse_hhmm(slot)
                # Каналы работают по числовым ID, а не по @username.
                # ES-каналы получают id из GitHub Secrets на раннере, поэтому
                # локально/в CI без секретов поле может быть пустым.
                self.assertTrue(
                    channel.telegram_chat_id.startswith("-100") or not channel.telegram_chat_id,
                    channel.id,
                )
        for channel in es_channels:
            self.assertEqual(channel.language, "es", channel.id)
        for channel in en_channels:
            self.assertEqual(channel.language, "en", channel.id)


class ConfigErrorCompatibilityTest(unittest.TestCase):
    def test_config_error_is_same(self) -> None:
        # ConfigError переиспользуется из utils, чтобы CLI ловил один тип.
        self.assertIs(ConfigError, UtilsConfigError)


if __name__ == "__main__":
    unittest.main()
