"""Тесты автоподстановки брендовых карточек в партнёрские посты."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import content_factory.brand.templates  # noqa: F401 - нужен для patch
from content_factory.brand import runtime


class ExtractTests(unittest.TestCase):
    def test_topic_for_channel(self):
        self.assertEqual(runtime.topic_for("ai-news"), "ai")
        self.assertEqual(runtime.topic_for("crypto-news"), "crypto")
        self.assertEqual(runtime.topic_for("sport-news"), "sports")
        self.assertEqual(runtime.topic_for("futbol-es"), "sports")
        self.assertEqual(runtime.topic_for("unknown-channel"), "crypto")

    def test_headline_and_subtitle(self):
        text = "<b>OpenAI ships GPT-5</b>\n\nBigger context window and lower price. More on the channel."
        self.assertEqual(runtime.headline_from_post(text), "OpenAI ships GPT-5")
        self.assertIn("Bigger context window", runtime.subtitle_from_post(text))
        self.assertEqual(runtime.headline_from_post(text, cluster_title="Custom"), "Custom")

    def test_partner_from_url(self):
        bingx = runtime.partner_from_url("https://bingxdao.com/invite/WYYEGK/")
        self.assertEqual(bingx["title"], "BingX")
        bitget = runtime.partner_from_url("https://partner.bitget.com/bg/abc")
        self.assertEqual(bitget["title"], "Bitget")
        unknown = runtime.partner_from_url("https://example.org/ref/1")
        self.assertEqual(unknown["title"], "Example")
        self.assertTrue(unknown["url"].startswith("https://"))

    def test_affiliate_link_from_meta_or_config(self):
        post = SimpleNamespace(meta={"affiliate": "🤝 Trade on BingX (ad): https://bingxdao.com/invite/X/"})
        channel = SimpleNamespace(affiliate={})
        self.assertIn("bingxdao.com", runtime.affiliate_link(post, channel))
        post2 = SimpleNamespace(meta={})
        channel2 = SimpleNamespace(affiliate={"tracked_url": "https://links.example/r/x"})
        self.assertEqual(runtime.affiliate_link(post2, channel2), "https://links.example/r/x")


class AttachTests(unittest.TestCase):
    def _post(self):
        return SimpleNamespace(
            id="p1",
            text="<b>OpenAI ships GPT-5</b>\n\nBigger context window.",
            meta={"affiliate": "ad · https://bingxdao.com/invite/X/"},
        )

    def _channel(self):
        return SimpleNamespace(id="crypto-news", affiliate={"link": "https://bingxdao.com/invite/X/"})

    def test_disabled_by_env(self):
        with mock.patch.dict(os.environ, {"BRAND_CARDS": "0"}):
            self.assertIsNone(runtime.maybe_attach_affiliate_card(
                self._post(), self._channel(), mock.Mock()))

    def test_attaches_brand_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "card.png"
            spec_calls = {}

            def fake_plan(config, network, topic, partner="", **kwargs):
                spec_calls.update(network=network, topic=topic, **kwargs)
                return {"network": network, "topic_key": topic, "partner": None}

            def fake_render(spec, out_dir):
                target.write_bytes(b"png")
                return target

            settings = mock.Mock()
            settings.publishers = {}
            with mock.patch.dict(os.environ, {"BRAND_CARDS": "1"}), \
                 mock.patch.object(runtime, "_cache_path", return_value=target), \
                 mock.patch("content_factory.brand.templates.load_config", return_value={"networks": []}), \
                 mock.patch("content_factory.brand.templates.plan", side_effect=fake_plan), \
                 mock.patch("content_factory.brand.templates.render", side_effect=fake_render):
                path = runtime.maybe_attach_affiliate_card(self._post(), self._channel(), settings)
            post = self._post()
        self.assertEqual(spec_calls["network"], "telegram_post")
        self.assertEqual(spec_calls["topic"], "crypto")
        self.assertTrue(path)

    def test_render_failure_is_harmless(self):
        settings = mock.Mock()
        settings.publishers = {}
        post = self._post()
        with mock.patch.dict(os.environ, {"BRAND_CARDS": "1"}), \
             mock.patch("content_factory.brand.templates.load_config", return_value={}), \
             mock.patch("content_factory.brand.templates.plan", side_effect=RuntimeError("boom")):
            self.assertIsNone(runtime.maybe_attach_affiliate_card(post, self._channel(), settings))
        self.assertNotIn("card_path", post.meta or {})


if __name__ == "__main__":
    unittest.main()
