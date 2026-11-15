"""X через Buffer: fallback-публикатор."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from content_factory.config import Settings
from content_factory.models import ChannelConfig, GeneratedPost
from content_factory.publishers.buffer_x import BufferXPublisher


class FakeBufferClient:
    calls = []

    @classmethod
    def from_env(cls):
        return cls()

    def organizations(self):
        return [{"id": "org-1", "name": "My Organization"}]

    def channels(self, organization_id):
        assert organization_id == "org-1"
        return [{"id": "x-channel", "name": "NValdislav", "service": "twitter"}]

    def create_post(self, channel_id, text, mode="addToQueue"):
        self.calls.append({"channel_id": channel_id, "text": text, "mode": mode})
        return {"id": "buffer-post-1", "externalLink": "https://x.com/NValdislav/status/1"}


class BufferXPublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings.load(load_env=False)
        self.channel = ChannelConfig(id="crypto-news", title="Crypto", publisher_ids=["buffer-x"])
        self.post = GeneratedPost(
            id="p1",
            channel_id="crypto-news",
            cluster_id="c1",
            format="story",
            text="<b>Bitcoin</b> update &amp; more",
        )
        FakeBufferClient.calls = []

    def test_publish_uses_share_now(self) -> None:
        with mock.patch.dict(os.environ, {"BUFFER_API_KEY": "key"}, clear=True), mock.patch(
            "content_factory.publishers.buffer_x.BufferClient", FakeBufferClient
        ):
            result = BufferXPublisher(self.settings).publish(self.post, self.channel, self.settings)

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.publisher, "buffer-x")
        self.assertEqual(result.external_id, "buffer-post-1")
        self.assertEqual(FakeBufferClient.calls[0]["channel_id"], "x-channel")
        self.assertEqual(FakeBufferClient.calls[0]["mode"], "shareNow")
        self.assertNotIn("<b>", FakeBufferClient.calls[0]["text"])

    def test_missing_key_is_reported(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            ok, detail = BufferXPublisher(self.settings).check(self.channel)
        self.assertFalse(ok)
        self.assertIn("BUFFER_API_KEY", detail)


if __name__ == "__main__":
    unittest.main()
