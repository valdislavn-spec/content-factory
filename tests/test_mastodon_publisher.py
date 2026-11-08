"""Тесты Mastodon-публикатора: антиспам-режим без ссылок и проверка кредов."""
import os
import unittest
from unittest import mock

from content_factory.models import ChannelConfig, GeneratedPost
from content_factory.publishers.mastodon import MastodonPublisher


def make_channel() -> ChannelConfig:
    return ChannelConfig(
        id="ai-news",
        title="AI News",
        language="en",
        topics=["ai"],
        hashtags=["#AI"],
        telegram_chat_id="@AINEWS0007",
    )


def make_post(text: str) -> GeneratedPost:
    return GeneratedPost(
        id="p1",
        channel_id="ai-news",
        cluster_id="c1",
        format="story",
        text=text,
        hashtags=["#AI"],
    )


class MastodonPublisherTests(unittest.TestCase):
    def setUp(self):
        self._env = {
            "MASTODON_BASE_URL": "https://mastodon.social",
            "MASTODON_TOKEN": "token",
        }
        os.environ.update(self._env)
        os.environ.pop("MASTODON_NO_LINKS", None)

    def tearDown(self):
        for key in ("MASTODON_BASE_URL", "MASTODON_TOKEN", "MASTODON_NO_LINKS"):
            os.environ.pop(key, None)

    def _publish(self, text: str):
        publisher = MastodonPublisher()
        with mock.patch(
            "content_factory.publishers.mastodon.http_json",
            return_value={"id": "42", "url": "https://mastodon.social/@cf/42"},
        ) as mocked:
            result = publisher.publish(make_post(text), make_channel(), mock.Mock())
        return result, mocked

    def test_requires_credentials(self):
        for key in ("MASTODON_BASE_URL", "MASTODON_TOKEN"):
            os.environ.pop(key)
        self.assertFalse(MastodonPublisher().check(make_channel())[0])

    def test_publishes_and_returns_url(self):
        result, mocked = self._publish("<b>Hello</b> world")
        self.assertTrue(result.ok)
        self.assertEqual(result.url, "https://mastodon.social/@cf/42")
        self.assertTrue(mocked.call_args.kwargs.get("form"))

    def test_no_links_mode_strips_urls(self):
        os.environ["MASTODON_NO_LINKS"] = "1"
        _, mocked = self._publish(
            "<b>Hello</b> https://t.me/AINEWS0007 and @AINEWS0007"
        )
        status = mocked.call_args.kwargs["payload"]["status"]
        self.assertNotIn("https://", status)
        self.assertIn("@AINEWS0007", status)

    def test_links_stay_when_mode_off(self):
        _, mocked = self._publish("Read more: https://t.me/AINEWS0007")
        status = mocked.call_args.kwargs["payload"]["status"]
        self.assertIn("https://t.me/AINEWS0007", status)


if __name__ == "__main__":
    unittest.main()
