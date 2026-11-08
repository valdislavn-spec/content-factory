"""Reddit publisher: refresh-token режим и выбор способа авторизации."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from content_factory.config import Settings
from content_factory.models import ChannelConfig, GeneratedPost
from content_factory.publishers.reddit import RedditPublisher


class RedditRefreshTest(unittest.TestCase):
    def setUp(self):
        self.settings = Settings.load(load_env=False)
        self.channel = ChannelConfig(
            id="crypto-news", title="Crypto", topics=["bitcoin"],
            schedule=["09:00"], telegram_chat_id="@HOOPY0007",
        )
        self.post = GeneratedPost(
            id="p1", channel_id="crypto-news", cluster_id="c1", format="digest",
            text="Bitcoin hits new high\n\nBody",
        )

    def test_refresh_token_used(self):
        calls = []

        def fake_http(url, method="POST", payload=None, headers=None, form=False, timeout=25.0):
            calls.append(payload)
            if url.endswith("/access_token"):
                return {"access_token": "tok"}
            return {"json": {"errors": [], "data": {"id": "x1"}}}

        env = {
            "REDDIT_CLIENT_ID": "cid", "REDDIT_CLIENT_SECRET": "sec",
            "REDDIT_REFRESH_TOKEN": "refresh-123", "REDDIT_SUBREDDIT": "USNewsWire",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch("content_factory.publishers.reddit.http_json", side_effect=fake_http):
                publisher = RedditPublisher(self.settings)
                ok, detail = publisher.check(self.channel)
                self.assertTrue(ok, detail)
                self.assertIn("refresh-token", detail)
                result = publisher.publish(self.post, self.channel, self.settings)
        self.assertTrue(result.ok, result.error)
        token_payload = calls[0]
        self.assertEqual(token_payload["grant_type"], "refresh_token")
        self.assertEqual(token_payload["refresh_token"], "refresh-123")

    def test_nothing_configured(self):
        publisher = RedditPublisher(self.settings)
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME",
                        "REDDIT_PASSWORD", "REDDIT_REFRESH_TOKEN", "REDDIT_SUBREDDIT"):
                os.environ.pop(key, None)
            ok, detail = publisher.check(self.channel)
        self.assertFalse(ok)
        self.assertIn("REFRESH_TOKEN_OR_USERNAME_PASSWORD", detail)


if __name__ == "__main__":
    unittest.main()
