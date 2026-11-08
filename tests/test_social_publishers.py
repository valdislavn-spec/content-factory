"""Тесты бесплатных соцсетей-публикаторов: Bluesky, Mastodon, Discord (без сети)."""

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
from content_factory.publishers.bluesky import BlueskyPublisher
from content_factory.publishers.discord import DiscordPublisher
from content_factory.publishers.mastodon import MastodonPublisher
from content_factory.publishers.social import SocialAPIError
from content_factory.pipeline import publish_post
from content_factory.storage import Storage

_ENV = (
    "CONTENT_FACTORY_DRY_RUN",
    "BLUESKY_HANDLE",
    "BLUESKY_APP_PASSWORD",
    "BLUESKY_HANDLE_AI_NEWS",
    "BLUESKY_APP_PASSWORD_AI_NEWS",
    "MASTODON_BASE_URL",
    "MASTODON_TOKEN",
    "DISCORD_WEBHOOK_URL",
)


class SocialTestCase(unittest.TestCase):
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
            sources=[{"source": "Habr", "url": "https://habr.com/1"}],
        )


class BlueskyTests(SocialTestCase):
    def test_check_without_env(self):
        publisher = BlueskyPublisher(self.make_settings())
        ready, detail = publisher.check(self.make_channel())
        self.assertFalse(ready)
        self.assertIn("BLUESKY", detail)

    def test_publish_success(self):
        os.environ["BLUESKY_HANDLE"] = "cf.bsky.social"
        os.environ["BLUESKY_APP_PASSWORD"] = "app-pass"
        settings = self.make_settings()
        publisher = BlueskyPublisher(settings)
        self.assertTrue(publisher.check(self.make_channel())[0])

        def fake_http(url, method="POST", payload=None, headers=None, form=False, timeout=25.0):
            if "createSession" in url:
                return {"accessJwt": "jwt", "did": "did:plc:test"}
            return {"uri": "at://did:plc:test/app.bsky.feed.post/abc123"}

        with mock.patch("content_factory.publishers.bluesky.http_json", side_effect=fake_http):
            result = publisher.publish(self.make_post(), self.make_channel(), settings)
        self.assertTrue(result.ok)
        self.assertIn("bsky.app/profile/cf.bsky.social/post/abc123", result.url)
        self.assertEqual(result.external_id, "at://did:plc:test/app.bsky.feed.post/abc123")

    def test_per_channel_env_wins(self):
        os.environ["BLUESKY_HANDLE"] = "common"
        os.environ["BLUESKY_APP_PASSWORD"] = "common-pass"
        os.environ["BLUESKY_HANDLE_AI_NEWS"] = "ai-news"
        os.environ["BLUESKY_APP_PASSWORD_AI_NEWS"] = "ai-pass"
        publisher = BlueskyPublisher(self.make_settings())
        ready, detail = publisher.check(self.make_channel())
        self.assertTrue(ready)
        self.assertIn("ai-news", detail)

    def test_api_error_is_graceful(self):
        os.environ["BLUESKY_HANDLE"] = "cf"
        os.environ["BLUESKY_APP_PASSWORD"] = "pass"
        settings = self.make_settings()
        with mock.patch(
            "content_factory.publishers.bluesky.http_json",
            side_effect=SocialAPIError("boom"),
        ):
            result = BlueskyPublisher(settings).publish(
                self.make_post(), self.make_channel(), settings
            )
        self.assertFalse(result.ok)
        self.assertIn("boom", result.error)


class MastodonTests(SocialTestCase):
    def test_publish_success(self):
        os.environ["MASTODON_BASE_URL"] = "https://mastodon.social"
        os.environ["MASTODON_TOKEN"] = "token"
        settings = self.make_settings()
        publisher = MastodonPublisher(settings)
        self.assertTrue(publisher.check(self.make_channel())[0])
        with mock.patch(
            "content_factory.publishers.mastodon.http_json",
            return_value={"id": "42", "url": "https://mastodon.social/@cf/42"},
        ) as mocked:
            result = publisher.publish(self.make_post(), self.make_channel(), settings)
        self.assertTrue(result.ok)
        self.assertEqual(result.url, "https://mastodon.social/@cf/42")
        self.assertEqual(mocked.call_args.kwargs.get("form"), True)

    def test_requires_creds(self):
        publisher = MastodonPublisher(self.make_settings())
        self.assertFalse(publisher.check(self.make_channel())[0])
    def test_no_links_flag_strips_urls(self):
        os.environ["MASTODON_BASE_URL"] = "https://mastodon.social"
        os.environ["MASTODON_TOKEN"] = "token"
        os.environ["MASTODON_NO_LINKS"] = "1"
        settings = self.make_settings()
        publisher = MastodonPublisher(settings)
        post = self.make_post()
        post.text = "<b>Hello</b> link https://t.me/AINEWS0007 and @AINEWS0007"
        with mock.patch(
            "content_factory.publishers.mastodon.http_json",
            return_value={"id": "1", "url": "u"},
        ) as mocked:
            publisher.publish(post, self.make_channel(), settings)
        sent = mocked.call_args.kwargs["payload"]["status"]
        self.assertNotIn("https://", sent)
        self.assertIn("@AINEWS0007", sent)
        os.environ.pop("MASTODON_NO_LINKS", None)


class DiscordTests(SocialTestCase):
    def test_publish_success(self):
        os.environ["DISCORD_WEBHOOK_URL"] = "https://discord.com/api/webhooks/1/abc"
        settings = self.make_settings()
        publisher = DiscordPublisher(settings)
        self.assertTrue(publisher.check(self.make_channel())[0])
        with mock.patch(
            "content_factory.publishers.discord.http_json", return_value={"id": "msg-1"}
        ):
            result = publisher.publish(self.make_post(), self.make_channel(), settings)
        self.assertTrue(result.ok)
        self.assertEqual(result.external_id, "msg-1")

    def test_invalid_webhook(self):
        os.environ["DISCORD_WEBHOOK_URL"] = "https://example.com/not-a-webhook"
        publisher = DiscordPublisher(self.make_settings())
        self.assertFalse(publisher.check(self.make_channel())[0])


class PipelineSkipTests(SocialTestCase):
    def test_unconfigured_optional_publisher_is_skipped(self):
        settings = self.make_settings(dry_run=False)
        settings.ensure_dirs()
        channel = self.make_channel(publisher_ids=["bluesky"])
        with Storage(settings.db_path) as storage:
            results = publish_post(self.make_post(), channel, settings, storage, effective_dry_run=False)
        self.assertEqual(results, [])  # не настроен → тихий пропуск, без ошибки

    def test_alias_resolves(self):
        settings = self.make_settings(dry_run=False)
        self.assertIsInstance(get_publisher("bsky", settings), BlueskyPublisher)
        self.assertIsInstance(get_publisher("mastodon", settings), MastodonPublisher)
        self.assertIsInstance(get_publisher("discord", settings), DiscordPublisher)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
