"""Тесты реестра источников, проверки доступности и Telegram-адаптера на моках."""
import os
import unittest
from datetime import datetime, timezone
from unittest import mock

from content_factory.config import Settings
from content_factory.models import SourceConfig
from content_factory.sources import (
    available_types,
    check_source,
    fetch_source,
    get_adapter,
)
from content_factory.sources.base import SourceAdapter
from content_factory.sources.espn import ESPNAdapter
from content_factory.sources.rss import RSSAdapter
from content_factory.sources.telegram import (
    TelegramAdapter,
    channel_username,
    telegram_credentials,
)
from content_factory.sources.web import WebAdapter
from content_factory.utils import FetchError

SETTINGS = Settings.load()


class FakeMessage:
    """Минимальная замена telethon.tl.custom.message.Message."""

    def __init__(self, message_id, text, date=None, action=None):
        self.id = message_id
        self.text = text
        self.message = text
        self.date = date or datetime(2026, 10, 14, 9, 0, tzinfo=timezone.utc)
        self.action = action


class FakeClient:
    """Мок TelegramClient: считает вызовы и отдаёт заданные сообщения."""

    def __init__(self, messages):
        self.messages = messages
        self.calls = []
        self.entered = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *args):
        return False

    def get_messages(self, username, limit):
        self.calls.append((username, limit))
        return self.messages[:limit]


class RegistryTest(unittest.TestCase):
    def test_available_types(self) -> None:
        self.assertEqual(
            available_types(),
            ["currents", "espn", "newsdata", "rss", "telegram", "web", "worldnews"],
        )

    def test_get_adapter_returns_instances(self) -> None:
        self.assertIsInstance(get_adapter("rss"), RSSAdapter)
        self.assertIsInstance(get_adapter("web"), WebAdapter)
        self.assertIsInstance(get_adapter("telegram"), TelegramAdapter)
        self.assertIsInstance(get_adapter("espn"), ESPNAdapter)
        self.assertIsInstance(get_adapter("RSS"), RSSAdapter, "тип не должен зависеть от регистра")

    def test_unknown_type_raises(self) -> None:
        with self.assertRaises(FetchError):
            get_adapter("carrier-pigeon")

    def test_check_source_unknown_type(self) -> None:
        source = SourceConfig(id="bad", type="rss", url="https://example.com/feed")
        source.type = "unknown"
        ok, message = check_source(source, SETTINGS)
        self.assertFalse(ok)
        self.assertIn("Неизвестный тип", message)

    def test_check_source_rss(self) -> None:
        feed = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0"><channel><item>
          <title>Проверочная новость</title>
          <link>https://example.com/news/1</link>
          <description>Описание проверочной новости.</description>
        </item></channel></rss>"""
        source = SourceConfig(id="rss-check", type="rss", url="https://example.com/feed")
        with mock.patch("content_factory.sources.rss.http_get_text", return_value=feed):
            ok, message = check_source(source, SETTINGS)
        self.assertTrue(ok)
        self.assertIn("доступен", message.lower())

    def test_fetch_source_delegates_to_adapter(self) -> None:
        feed = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0"><channel><item>
          <title>Новость для fetch_source</title>
          <link>https://example.com/news/2</link>
        </item></channel></rss>"""
        source = SourceConfig(id="rss-fetch", type="rss", url="https://example.com/feed")
        with mock.patch("content_factory.sources.rss.http_get_text", return_value=feed):
            articles = fetch_source(source, SETTINGS)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].source_id, "rss-fetch")

    def test_base_adapter_contract(self) -> None:
        adapter = SourceAdapter()
        source = SourceConfig(id="base", type="base", url="https://example.com/")
        with self.assertRaises(NotImplementedError):
            adapter.fetch(source, SETTINGS)


class TelegramAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = TelegramAdapter()
        self.source = SourceConfig(
            id="tg-test",
            type="telegram",
            url="https://t.me/test_channel",
            name="Тестовый канал",
            weight=0.9,
            options={"limit": 5},
        )

    def test_channel_username(self) -> None:
        self.assertEqual(channel_username("https://t.me/rian_ru"), "rian_ru")
        self.assertEqual(channel_username("t.me/rian_ru"), "rian_ru")
        self.assertEqual(channel_username("https://telegram.me/rian_ru"), "rian_ru")
        self.assertEqual(channel_username("https://t.me/s/rian_ru"), "rian_ru")
        self.assertEqual(channel_username("https://t.me/@rian_ru"), "rian_ru")

    def test_private_channel_rejected(self) -> None:
        with self.assertRaises(FetchError):
            channel_username("https://t.me/joinchat/AAAAA")
        with self.assertRaises(FetchError):
            channel_username("https://t.me/+AAAAA")

    def test_credentials_from_environment(self) -> None:
        with mock.patch.dict(os.environ, {"TG_API_ID": "12345", "TG_API_HASH": "hash"}):
            self.assertEqual(telegram_credentials(), (12345, "hash"))

    def test_credentials_missing(self) -> None:
        with mock.patch.dict(os.environ, {"TG_API_ID": "", "TG_API_HASH": ""}):
            with self.assertRaises(FetchError) as context:
                telegram_credentials()
        self.assertIn("my.telegram.org", str(context.exception))

    def test_fetch_with_mocked_client(self) -> None:
        messages = [
            FakeMessage(7, "Заголовок сообщения\n\nПодробный текст новости из Telegram."),
            FakeMessage(8, "Ещё одна новость канала без длинного текста."),
            FakeMessage(9, "Служебное сообщение", action=object()),
            FakeMessage(10, "   "),
        ]
        client = FakeClient(messages)
        with mock.patch.dict(
            os.environ, {"TG_API_ID": "12345", "TG_API_HASH": "hash", "TG_SESSION": ""}
        ):
            with mock.patch.object(TelegramAdapter, "_create_client", return_value=client):
                articles = self.adapter.fetch(self.source, SETTINGS)
        self.assertEqual(client.calls, [("test_channel", 5)])
        self.assertTrue(client.entered)
        self.assertEqual(len(articles), 2, "служебные и пустые сообщения пропускаются")
        first = articles[0]
        self.assertEqual(first.title, "Заголовок сообщения")
        self.assertEqual(first.url, "https://t.me/test_channel/7")
        self.assertEqual(first.source_id, "tg-test")
        self.assertIn("Подробный текст", first.text)
        self.assertTrue(first.published_at.tzinfo)
        self.assertEqual(first.meta["message_id"], 7)

    def test_fetch_without_credentials(self) -> None:
        with mock.patch.dict(os.environ, {"TG_API_ID": "", "TG_API_HASH": ""}):
            with self.assertRaises(FetchError):
                self.adapter.fetch(self.source, SETTINGS)

    def test_check_without_credentials(self) -> None:
        with mock.patch.dict(os.environ, {"TG_API_ID": "", "TG_API_HASH": ""}):
            ok, message = check_source(self.source, SETTINGS)
        self.assertFalse(ok)
        self.assertIn("TG_API_ID", message)

    def test_fetch_error_mentions_optional_dependency(self) -> None:
        with mock.patch.dict(
            os.environ, {"TG_API_ID": "12345", "TG_API_HASH": "hash", "TG_SESSION": ""}
        ):
            with mock.patch.object(
                TelegramAdapter,
                "_create_client",
                side_effect=FetchError(
                    "Для Telegram-источников нужен Telethon. Установите: "
                    "python -m pip install -r requirements-optional.txt"
                ),
            ):
                with self.assertRaises(FetchError) as context:
                    self.adapter.fetch(self.source, SETTINGS)
        self.assertIn("requirements-optional.txt", str(context.exception))


if __name__ == "__main__":
    unittest.main()
