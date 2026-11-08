"""Тесты клиента трекера ссылок (без сети)."""

from __future__ import annotations

import json
import os
import unittest
import urllib.error
from io import BytesIO
from unittest import mock

from content_factory.integrations.affiliate import build_affiliate_line, resolve_link
from content_factory.integrations.link_tracker import LinkTrackerClient, LinkTrackerError


class FakeResponse:
    def __init__(self, payload) -> None:
        self.payload = json.dumps(payload).encode()

    def read(self, *args, **kwargs) -> bytes:  # noqa: D102
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class LinkTrackerClientTests(unittest.TestCase):
    def test_short_url(self) -> None:
        client = LinkTrackerClient(base_url="https://links.example.dev")
        self.assertEqual(client.short_url("bingx-crypto-news"), "https://links.example.dev/r/bingx-crypto-news")

    def test_create_link_request(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["method"] = request.method
            captured["headers"] = dict(request.headers)
            captured["body"] = json.loads(request.data.decode())
            return FakeResponse({"ok": True, "record": {"code": "bingx-crypto-news"}})

        client = LinkTrackerClient(base_url="https://links.example.dev", admin_token="adm")
        with mock.patch(
            "content_factory.integrations.link_tracker.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            record = client.create_link(
                "bingx-crypto-news",
                "https://bingxdao.com/invite/WYYEGK/",
                channel="crypto-news",
                network="bingx",
            )
        self.assertEqual(record["code"], "bingx-crypto-news")
        self.assertTrue(captured["url"].endswith("/admin/links"))
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["body"]["channel"], "crypto-news")
        self.assertIn("x-token", {k.lower(): v for k, v in captured["headers"].items()})

    def test_stats_parsing(self) -> None:
        payload = {
            "ok": True,
            "count": 1,
            "links": [
                {"code": "bingx-default", "total": 3, "channel": "", "days": {"2026-11-08": 3}},
            ],
        }
        client = LinkTrackerClient(base_url="https://links.example.dev", stats_token="st")
        with mock.patch(
            "content_factory.integrations.link_tracker.urllib.request.urlopen",
            return_value=FakeResponse(payload),
        ):
            data = client.stats()
        self.assertEqual(data["links"][0]["total"], 3)

    def test_error_response(self) -> None:
        client = LinkTrackerClient(base_url="https://links.example.dev", admin_token="bad")
        with mock.patch(
            "content_factory.integrations.link_tracker.urllib.request.urlopen",
            return_value=FakeResponse({"ok": False, "error": "forbidden"}),
        ):
            with self.assertRaises(LinkTrackerError):
                client.list_links()

    def test_missing_base(self) -> None:
        client = LinkTrackerClient(base_url="")
        with self.assertRaises(LinkTrackerError):
            client.short_url("x")


class AffiliateTrackedLinkTests(unittest.TestCase):
    def test_tracked_url_wins_over_raw_link(self) -> None:
        cfg = {
            "enabled": True,
            "link": "https://bingxdao.com/invite/WYYEGK/",
            "tracked_url": "https://links.example.dev/r/bingx-crypto-news",
        }
        self.assertEqual(resolve_link(cfg, "crypto-news"), "https://links.example.dev/r/bingx-crypto-news")
        line = build_affiliate_line(cfg, "en")
        self.assertIn("links.example.dev/r/bingx-crypto-news", line)
        self.assertNotIn("bingxdao.com", line)

    def test_code_and_base_build_tracked_url(self) -> None:
        cfg = {"enabled": True, "code": "bingx-crypto-es", "link": "https://bingxdao.com/invite/WYYEGK/"}
        with mock.patch.dict(os.environ, {"LINK_TRACKER_BASE": "https://links.example.dev/"}, clear=False):
            self.assertEqual(
                resolve_link(cfg, "crypto-es"),
                "https://links.example.dev/r/bingx-crypto-es",
            )

    def test_env_override_beats_tracking(self) -> None:
        cfg = {"enabled": True, "tracked_url": "https://links.example.dev/r/x", "link": "https://bingxdao.com/invite/WYYEGK/"}
        with mock.patch.dict(os.environ, {"AFFILIATE_LINK_CRYPTO_NEWS": "https://direct.example.com/offer"}, clear=False):
            self.assertEqual(resolve_link(cfg, "crypto-news"), "https://direct.example.com/offer")

    def test_plain_link_still_works(self) -> None:
        cfg = {"enabled": True, "link": "https://mylead.global/r/dJ67Qo"}
        with mock.patch.dict(os.environ, {}, clear=False):
            self.assertEqual(resolve_link(cfg, "crypto-news"), "https://mylead.global/r/dJ67Qo")
