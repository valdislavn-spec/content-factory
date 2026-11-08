"""Тесты публикатора Tumblr (OAuth 1.0a, без сети)."""

from __future__ import annotations

import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from content_factory.config import DEFAULT_SETTINGS, Settings
from content_factory.models import ChannelConfig, GeneratedPost
from content_factory.publishers import get_publisher
from content_factory.publishers.dryrun import DryRunPublisher
from content_factory.publishers.social import SocialAPIError
from content_factory.publishers.tumblr import TumblrPublisher, _pct, _signature

_ENV = (
    "TUMBLR_CONSUMER_KEY",
    "TUMBLR_CONSUMER_SECRET",
    "TUMBLR_OAUTH_TOKEN",
    "TUMBLR_OAUTH_TOKEN_SECRET",
    "TUMBLR_BLOG",
    "TUMBLR_BLOG_AI_NEWS",
    "CONTENT_FACTORY_DRY_RUN",
)


class TumblrTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self._saved = {key: os.environ.pop(key, None) for key in _ENV}
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        for key, value in self._saved.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value

    def make_settings(self, dry_run: bool = False) -> Settings:
        raw = copy.deepcopy(DEFAULT_SETTINGS)
        raw["app"].update(
            {
                "dry_run": dry_run,
                "data_dir": str(self.root / "data"),
                "db_path": str(self.root / "data" / "factory.sqlite3"),
                "outbox_dir": str(self.root / "data" / "outbox"),
                "reports_dir": str(self.root / "data" / "reports"),
                "logs_dir": str(self.root / "data" / "logs"),
            }
        )
        return Settings(
            root=self.root,
            raw=raw,
            settings_path=self.root / "config" / "settings.yaml",
            channels_path=self.root / "config" / "channels.yaml",
        )

    def make_channel(self, **overrides) -> ChannelConfig:
        values = dict(
            id="ai-news",
            title="AI News",
            topics=["ai"],
            telegram_chat_id="@AINEWS0007",
            language="en",
            description="AI news. @AINEWS0007",
            publisher_ids=["telegram"],
        )
        values.update(overrides)
        return ChannelConfig(**values)

    def make_post(self) -> GeneratedPost:
        return GeneratedPost(
            id="post-1",
            channel_id="ai-news",
            cluster_id="cluster-1",
            format="story",
            text="<b>OpenAI releases GPT-5</b>\n\nНовый релиз и разбор.",
            hashtags=["#ai"],
        )

    def set_creds(self) -> None:
        os.environ["TUMBLR_CONSUMER_KEY"] = "ck"
        os.environ["TUMBLR_CONSUMER_SECRET"] = "cs"
        os.environ["TUMBLR_OAUTH_TOKEN"] = "ot"
        os.environ["TUMBLR_OAUTH_TOKEN_SECRET"] = "os"
        os.environ["TUMBLR_BLOG"] = "vlad-007"


class TumblrPublisherTests(TumblrTestCase):
    def test_requires_creds(self):
        publisher = TumblrPublisher(self.make_settings())
        ready, detail = publisher.check(self.make_channel())
        self.assertFalse(ready)
        self.assertIn("TUMBLR", detail)

    def test_check_with_creds(self):
        self.set_creds()
        publisher = TumblrPublisher(self.make_settings())
        ready, detail = publisher.check(self.make_channel())
        self.assertTrue(ready)
        self.assertIn("vlad-007", detail)

    def test_per_channel_blog_wins(self):
        self.set_creds()
        os.environ["TUMBLR_BLOG_AI_NEWS"] = "ai-blog"
        publisher = TumblrPublisher(self.make_settings())
        _, detail = publisher.check(self.make_channel())
        self.assertIn("ai-blog", detail)

    def test_publish_success(self):
        self.set_creds()
        settings = self.make_settings()
        publisher = TumblrPublisher(settings)
        with mock.patch(
            "content_factory.publishers.tumblr._oauth1_request",
            return_value={"response": {"id": "12345"}},
        ) as mocked:
            result = publisher.publish(self.make_post(), self.make_channel(), settings)
        self.assertTrue(result.ok)
        self.assertEqual(result.external_id, "12345")
        self.assertEqual(result.url, "https://vlad-007.tumblr.com/post/12345")
        args, kwargs = mocked.call_args
        self.assertEqual(args[0], "POST")
        self.assertIn("/v2/blog/vlad-007/post", args[1])
        sent = args[2]
        self.assertEqual(sent["type"], "text")
        self.assertEqual(sent["state"], "published")
        self.assertEqual(sent["tags"], "ai")
        self.assertIn("OpenAI releases GPT-5", sent["body"])
        self.assertIn("<br/>", sent["body"])
        self.assertEqual(kwargs["consumer_key"], "ck")
        self.assertEqual(kwargs["token_secret"], "os")

    def test_publish_resolves_primary_blog(self):
        os.environ["TUMBLR_CONSUMER_KEY"] = "ck"
        os.environ["TUMBLR_CONSUMER_SECRET"] = "cs"
        os.environ["TUMBLR_OAUTH_TOKEN"] = "ot"
        os.environ["TUMBLR_OAUTH_TOKEN_SECRET"] = "os"
        settings = self.make_settings()
        publisher = TumblrPublisher(settings)
        calls = []

        def fake_request(method, url, params=None, **kwargs):
            calls.append(url)
            if "user/info" in url:
                return {"response": {"user": {"blogs": [{"name": "vlad-007", "primary": True}]}}}
            return {"response": {"id": "9"}}

        with mock.patch(
            "content_factory.publishers.tumblr._oauth1_request", side_effect=fake_request
        ):
            result = publisher.publish(self.make_post(), self.make_channel(), settings)
        self.assertTrue(result.ok)
        self.assertTrue(any("user/info" in url for url in calls))
        self.assertTrue(any("/v2/blog/vlad-007/post" in url for url in calls))
        self.assertEqual(result.url, "https://vlad-007.tumblr.com/post/9")

    def test_api_error_is_graceful(self):
        self.set_creds()
        settings = self.make_settings()
        with mock.patch(
            "content_factory.publishers.tumblr._oauth1_request",
            side_effect=SocialAPIError("boom"),
        ):
            result = TumblrPublisher(settings).publish(
                self.make_post(), self.make_channel(), settings
            )
        self.assertFalse(result.ok)
        self.assertIn("boom", result.error)

    def test_registry_and_dry_run(self):
        settings = self.make_settings()
        publisher = get_publisher("tumblr", settings)
        self.assertIsInstance(publisher, TumblrPublisher)
        self.assertIsInstance(get_publisher("tumblr.com", settings), TumblrPublisher)
        dry = get_publisher("tumblr", self.make_settings(dry_run=True))
        self.assertIsInstance(dry, DryRunPublisher)


class TumblrOAuthHelpersTests(unittest.TestCase):
    def test_percent_encoding(self):
        self.assertEqual(_pct("a b+c/d~"), "a%20b%2Bc%2Fd~")

    def test_signature_is_stable_and_depends_on_params(self):
        params = {"oauth_consumer_key": "ck", "oauth_nonce": "n", "a": "b c"}
        first = _signature("POST", "https://api.tumblr.com/v2/x", params, "cs", "ts")
        second = _signature("POST", "https://api.tumblr.com/v2/x", params, "cs", "ts")
        self.assertEqual(first, second)
        changed = _signature(
            "POST", "https://api.tumblr.com/v2/x", {**params, "a": "b d"}, "cs", "ts"
        )
        self.assertNotEqual(first, changed)


if __name__ == "__main__":
    unittest.main()
