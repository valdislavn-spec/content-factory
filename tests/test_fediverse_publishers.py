"""Тесты fediverse-публикаторов: Pleroma/Akkoma/GoToSocial/Friendica/Misskey."""
import os
import unittest
from unittest import mock

from content_factory.models import ChannelConfig, GeneratedPost
from content_factory.publishers import get_publisher, publisher_classes
from content_factory.publishers.fediverse import (
    AkkomaPublisher,
    FriendicaPublisher,
    GoToSocialPublisher,
    MisskeyPublisher,
    PleromaPublisher,
)


def make_channel() -> ChannelConfig:
    return ChannelConfig(
        id="ai-news",
        title="AI News",
        language="en",
        topics=["ai"],
        hashtags=["#AI"],
        telegram_chat_id="@AINEWS0007",
    )


def make_post(text: str = "<b>Hello</b> fediverse") -> GeneratedPost:
    return GeneratedPost(
        id="p1", channel_id="ai-news", cluster_id="c1", format="story",
        text=text, hashtags=["#AI"],
    )


class RegistryTests(unittest.TestCase):
    def test_registry_has_fediverse_networks(self):
        classes = publisher_classes()
        for name, cls in (
            ("pleroma", PleromaPublisher),
            ("akkoma", AkkomaPublisher),
            ("gotosocial", GoToSocialPublisher),
            ("friendica", FriendicaPublisher),
            ("misskey", MisskeyPublisher),
        ):
            self.assertIn(name, classes)
            self.assertIs(classes[name], cls)

    def test_aliases(self):
        from content_factory.config import Settings

        settings = mock.Mock()
        settings.dry_run = False
        settings.publishers = {}
        self.assertIsInstance(get_publisher("mk", settings), MisskeyPublisher)
        self.assertIsInstance(get_publisher("gts", settings), GoToSocialPublisher)


class MastodonCompatibleTests(unittest.TestCase):
    def setUp(self):
        for key in ("PLEROMA_BASE_URL", "PLEROMA_TOKEN", "MASTODON_NO_LINKS"):
            os.environ.pop(key, None)

    def tearDown(self):
        for key in ("PLEROMA_BASE_URL", "PLEROMA_TOKEN", "MASTODON_NO_LINKS"):
            os.environ.pop(key, None)

    def test_requires_credentials(self):
        publisher = PleromaPublisher(mock.Mock())
        self.assertFalse(publisher.check(make_channel())[0])

    def test_publish_success(self):
        os.environ["PLEROMA_BASE_URL"] = "https://pleroma.example"
        os.environ["PLEROMA_TOKEN"] = "token"
        publisher = PleromaPublisher(mock.Mock())
        self.assertTrue(publisher.check(make_channel())[0])
        with mock.patch(
            "content_factory.publishers.fediverse.http_json",
            return_value={"id": "42", "url": "https://pleroma.example/notes/42"},
        ) as mocked:
            result = publisher.publish(make_post(), make_channel(), mock.Mock())
        self.assertTrue(result.ok)
        self.assertEqual(result.url, "https://pleroma.example/notes/42")
        self.assertTrue(mocked.call_args.kwargs.get("form"))
        self.assertEqual(mocked.call_args.args[0], "https://pleroma.example/api/v1/statuses")

    def test_no_links_strip(self):
        os.environ["PLEROMA_BASE_URL"] = "https://pleroma.example"
        os.environ["PLEROMA_TOKEN"] = "token"
        os.environ["MASTODON_NO_LINKS"] = "1"
        publisher = PleromaPublisher(mock.Mock())
        with mock.patch(
            "content_factory.publishers.fediverse.http_json",
            return_value={"id": "1", "url": "u"},
        ) as mocked:
            publisher.publish(make_post("text https://t.me/AINEWS0007 and @AINEWS0007"),
                              make_channel(), mock.Mock())
        status = mocked.call_args.kwargs["payload"]["status"]
        self.assertNotIn("https://", status)
        self.assertIn("@AINEWS0007", status)


class MisskeyTests(unittest.TestCase):
    def setUp(self):
        for key in ("MISSKEY_HOST", "MISSKEY_TOKEN", "MISSKEY_MAX_CHARS"):
            os.environ.pop(key, None)

    def tearDown(self):
        for key in ("MISSKEY_HOST", "MISSKEY_TOKEN", "MISSKEY_MAX_CHARS"):
            os.environ.pop(key, None)

    def test_requires_credentials(self):
        self.assertFalse(MisskeyPublisher(mock.Mock()).check(make_channel())[0])

    def test_publish_payload_and_url(self):
        os.environ["MISSKEY_HOST"] = "https://misskey.example"
        os.environ["MISSKEY_TOKEN"] = "token"
        publisher = MisskeyPublisher(mock.Mock())
        self.assertTrue(publisher.check(make_channel())[0])
        with mock.patch(
            "content_factory.publishers.fediverse.http_json",
            return_value={"createdNote": {"id": "abc"}},
        ) as mocked:
            result = publisher.publish(make_post(), make_channel(), mock.Mock())
        self.assertTrue(result.ok)
        self.assertEqual(result.url, "https://misskey.example/notes/abc")
        payload = mocked.call_args.kwargs["payload"]
        self.assertEqual(payload["i"], "token")
        self.assertEqual(payload["visibility"], "public")
        self.assertIn("Hello", payload["text"])

    def test_missing_credentials_returns_error(self):
        result = MisskeyPublisher(mock.Mock()).publish(make_post(), make_channel(), mock.Mock())
        self.assertFalse(result.ok)
        self.assertIn("не настроен", result.error or "")


if __name__ == "__main__":
    unittest.main()
