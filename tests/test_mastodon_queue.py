"""Тесты очереди постов Mastodon (config/mastodon_queue.yaml)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scripts.mastodon_publish as pb


class QueueValidationTests(unittest.TestCase):
    def test_default_queue_is_valid(self):
        queue = pb.load_queue()
        self.assertGreaterEqual(len(queue), 10)
        for item in queue:
            self.assertLessEqual(len(item["text"]), pb.MAX_TEXT)
            self.assertTrue(item["channel"])
            self.assertIn(item["language"], {"en", "es"})
            self.assertIn(item["visibility"], {"public", "unlisted", "private", "direct"})

    def test_too_long_post_rejected(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as handle:
            handle.write("posts:\n  - channel: ai-news\n    text: '" + "x" * 501 + "'\n")
            path = Path(handle.name)
        try:
            with self.assertRaises(ValueError):
                pb.load_queue(path)
        finally:
            path.unlink(missing_ok=True)


class PublishFlowTests(unittest.TestCase):
    def _fake_channels(self):
        return {
            "ai-news": mock.Mock(id="ai-news"),
            "crypto-news": mock.Mock(id="crypto-news"),
            "tech-ai-es": mock.Mock(id="tech-ai-es"),
        }

    def test_dry_run_does_not_post(self):
        with mock.patch.object(pb.Settings, "load", return_value=object()), \
             mock.patch.object(pb, "channels_map", return_value=self._fake_channels()), \
             mock.patch.object(pb, "post_status") as posted:
            code = pb.run(apply=False)
        self.assertEqual(code, 0)
        posted.assert_not_called()

    def test_apply_posts_with_credentials(self):
        calls = []

        def fake_post(base, token, text, visibility, language, timeout=30):
            calls.append({"base": base, "token": token, "text": text, "language": language})
            return {"id": "1", "url": "https://mastodon.social/@cf/1"}

        def fake_env(channel, base, default=""):
            return "https://mastodon.social" if "BASE_URL" in base else "token-123"

        with mock.patch.object(pb.Settings, "load", return_value=object()), \
             mock.patch.object(pb, "channels_map", return_value=self._fake_channels()), \
             mock.patch.object(pb, "env_for_channel", side_effect=fake_env), \
             mock.patch.object(pb, "post_status", side_effect=fake_post), \
             mock.patch.object(pb, "load_queue", return_value=[
                 {"channel": "ai-news", "language": "en", "visibility": "public", "text": "hello"}
             ]):
            code = pb.run(apply=True)
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["token"], "token-123")
        self.assertEqual(calls[0]["language"], "en")

    def test_apply_without_credentials_skips(self):
        with mock.patch.object(pb.Settings, "load", return_value=object()), \
             mock.patch.object(pb, "channels_map", return_value=self._fake_channels()), \
             mock.patch.object(pb, "env_for_channel", return_value=""), \
             mock.patch.object(pb, "post_status") as posted, \
             mock.patch.object(pb, "load_queue", return_value=[
                 {"channel": "ai-news", "language": "en", "visibility": "public", "text": "hello"}
             ]):
            code = pb.run(apply=True)
        self.assertEqual(code, 0)
        posted.assert_not_called()

    def test_channel_filter(self):
        queue = pb.load_queue()
        channels = {"futbol-es": mock.Mock(id="futbol-es")}
        posted_channels = []

        def fake_post(base, token, text, visibility, language, timeout=30):
            posted_channels.append(language)
            return {"id": "1", "url": "u"}

        with mock.patch.object(pb.Settings, "load", return_value=object()), \
             mock.patch.object(pb, "channels_map", return_value=channels), \
             mock.patch.object(pb, "env_for_channel", return_value="x"), \
             mock.patch.object(pb, "post_status", side_effect=fake_post):
            code = pb.run(apply=True, only_channel="futbol-es")
        self.assertEqual(code, 0)
        self.assertEqual(len(posted_channels), 1)
        self.assertEqual(posted_channels[0], "es")


if __name__ == "__main__":
    unittest.main()
