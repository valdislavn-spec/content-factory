"""Mastodon publisher: NO_LINKS сохраняет упоминание канала, ссылки не ломают пост."""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from content_factory.config import Settings
from content_factory.models import ChannelConfig, GeneratedPost
from content_factory.publishers.mastodon import MastodonPublisher


class MastodonPublisherTest(unittest.TestCase):
    def setUp(self):
        self.settings = Settings.load(load_env=False)
        self.channel = ChannelConfig(
            id="ai-news",
            title="AI News",
            topics=["ai"],
            schedule=["09:00"],
            telegram_chat_id="@AINEWS0007",
        )
        self.post = GeneratedPost(
            id="p1",
            channel_id="ai-news",
            cluster_id="c1",
            format="digest",
            text="<b>AI digest</b>\n\nOpenAI released a model.\n\n#AI",
        )

    def _publish(self, extra_env, payload_capture):
        env = {
            "MASTODON_BASE_URL": "https://mastodon.example",
            "MASTODON_TOKEN": "tok",
        }
        env.update(extra_env)

        def fake_http(url, method="POST", payload=None, headers=None, form=False, timeout=25.0):
            payload_capture.append(payload)
            return {"id": "s1", "url": "https://mastodon.example/@bot/1"}

        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch("content_factory.publishers.mastodon.http_json", side_effect=fake_http):
                return MastodonPublisher(self.settings).publish(self.post, self.channel, self.settings)

    def test_no_links_keeps_channel_mention(self):
        payloads = []
        result = self._publish({"MASTODON_NO_LINKS": "1"}, payloads)
        self.assertTrue(result.ok, result.error)
        status = payloads[0]["status"]
        self.assertIn("Telegram: @AINEWS0007", status)
        self.assertNotIn("https://t.me/", status)
        self.assertLessEqual(len(status), 500)

    def test_links_kept_when_allowed(self):
        payloads = []
        result = self._publish({"MASTODON_NO_LINKS": "0"}, payloads)
        self.assertTrue(result.ok, result.error)
        status = payloads[0]["status"]
        self.assertIn("https://t.me/AINEWS0007", status)


if __name__ == "__main__":
    unittest.main()
