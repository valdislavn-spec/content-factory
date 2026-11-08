"""Reddit publisher: токен, submit, заголовок и проверка кредов."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from content_factory.config import Settings
from content_factory.models import ChannelConfig, GeneratedPost
from content_factory.publishers import get_publisher
from content_factory.publishers.reddit import RedditPublisher

ENV = {
    "REDDIT_CLIENT_ID": "cid",
    "REDDIT_CLIENT_SECRET": "secret",
    "REDDIT_USERNAME": "user",
    "REDDIT_PASSWORD": "pass",
    "REDDIT_SUBREDDIT": "USNewsWire",
}


class RedditPublisherTest(unittest.TestCase):
    def setUp(self):
        self.settings = Settings.load(load_env=False)
        self.settings.raw.setdefault("app", {})["dry_run"] = False
        self.channel = ChannelConfig(
            id="crypto-news",
            title="Crypto & Blockchain",
            topics=["bitcoin"],
            schedule=["09:00"],
            telegram_chat_id="@HOOPY0007",
        )
        self.post = GeneratedPost(
            id="p1",
            channel_id="crypto-news",
            cluster_id="c1",
            format="digest",
            text="Bitcoin ETF inflows hit record\n\nBody line one with details.\n\n#Crypto",
            sources=[{"title": "The Block", "url": "https://example.com"}],
        )

    def test_missing_creds_reports_error(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in ENV:
                os.environ.pop(key, None)
            publisher = RedditPublisher(self.settings)
            result = publisher.publish(self.post, self.channel, self.settings)
            self.assertFalse(result.ok)
            self.assertIn("REDDIT", result.error or "")

    def test_submit_self_post(self):
        calls = []

        def fake_http(url, method="POST", payload=None, headers=None, form=False, timeout=25.0):
            calls.append((url, payload, headers))
            if url.endswith("/access_token"):
                return {"access_token": "tok"}
            return {"json": {"errors": [], "data": {"id": "abc123", "url": "https://reddit.com/r/USNewsWire/comments/abc123"}}}

        with mock.patch.dict(os.environ, ENV, clear=False):
            with mock.patch("content_factory.publishers.reddit.http_json", side_effect=fake_http):
                publisher = RedditPublisher(self.settings)
                result = publisher.publish(self.post, self.channel, self.settings)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.external_id, "abc123")
        self.assertIn("comments/abc123", result.url or "")
        submit = [call for call in calls if call[0].endswith("/api/submit")][0]
        payload = submit[1]
        self.assertEqual(payload["sr"], "USNewsWire")
        self.assertEqual(payload["kind"], "self")
        self.assertEqual(payload["title"], "Bitcoin ETF inflows hit record")
        self.assertIn("Body line one", payload["text"])
        self.assertTrue(submit[2]["Authorization"].startswith("bearer "))

    def test_registry_has_reddit(self):
        publisher = get_publisher("reddit", self.settings)
        self.assertIsInstance(publisher, RedditPublisher)


if __name__ == "__main__":
    unittest.main()
