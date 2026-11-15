"""Аудит подключений каналов: включено ≠ настроено."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from content_factory.connections import (
    audit_channel,
    check_connection,
    summarize,
)
from content_factory.models import ChannelConfig
from content_factory.publishers import resolve_publisher_name


class ChannelConnectionsTest(unittest.TestCase):
    def _settings(self):
        return SimpleNamespace(publishers={})

    def test_aliases_are_normalized(self) -> None:
        self.assertEqual(resolve_publisher_name("tg"), "telegram")
        self.assertEqual(resolve_publisher_name("twitter"), "x")
        self.assertEqual(resolve_publisher_name("bsky"), "bluesky")

    def test_only_configured_publishers_are_checked(self) -> None:
        channel = ChannelConfig(
            id="crypto-news",
            title="Crypto",
            telegram_chat_id="-1001",
            publisher_ids=["telegram", "discord", "akkoma"],
        )
        env = {
            "TELEGRAM_BOT_TOKEN": "123:token",
            "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/1/abc",
            "AKKOMA_BASE_URL": "https://akkoma.example",
            "AKKOMA_TOKEN": "secret",
        }
        with patch.dict(os.environ, env, clear=True):
            rows = audit_channel(channel, self._settings())
        self.assertEqual([row.publisher for row in rows], ["telegram", "discord", "akkoma"])
        self.assertTrue(all(row.ready for row in rows))

    def test_missing_credentials_are_reported(self) -> None:
        channel = ChannelConfig(
            id="crypto-news",
            title="Crypto",
            telegram_chat_id="",
            publisher_ids=["telegram", "discord", "akkoma"],
        )
        with patch.dict(os.environ, {}, clear=True):
            rows = audit_channel(channel, self._settings())
        self.assertFalse(any(row.ready for row in rows))
        self.assertEqual(summarize(rows), {"connections": 3, "ready": 0, "missing": 3})

    def test_unknown_publisher_is_not_silently_accepted(self) -> None:
        channel = ChannelConfig(
            id="ai-news",
            title="AI",
            telegram_chat_id="-1002",
            publisher_ids=["unknown-network"],
        )
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "x"}, clear=True):
            row = check_connection(channel, "unknown-network", self._settings())
        self.assertFalse(row.ready)
        self.assertIn("неизвестный публикатор", row.detail)

    def test_discord_requires_real_webhook(self) -> None:
        channel = ChannelConfig(
            id="sport-news", title="Sports", publisher_ids=["discord"]
        )
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://example.com/hook"}, clear=True):
            row = check_connection(channel, "discord", self._settings())
        self.assertFalse(row.ready)


if __name__ == "__main__":
    unittest.main()
