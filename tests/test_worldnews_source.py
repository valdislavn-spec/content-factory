"""Тесты адаптера World News API (без сети)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
import urllib.error
import urllib.parse
from datetime import timezone
from unittest import mock

from content_factory.config import Settings
from content_factory.models import SourceConfig
from content_factory.sources import available_types, get_adapter
from content_factory.sources.worldnews import WorldNewsAdapter
from content_factory.utils import FetchError

NEWS_RESPONSE = {
    "offset": 0,
    "number": 2,
    "available": 42,
    "news": [
        {
            "id": 206030983,
            "title": "AI startup raises $100M to build safer models",
            "text": "The company plans to use the funding for safety research.",
            "summary": "AI safety startup raises a new round.",
            "url": "https://example.com/ai-startup",
            "image": "https://example.com/image.jpg",
            "video": None,
            "publish_date": "2026-11-06 09:15:00",
            "authors": ["Jane Doe"],
            "category": "technology",
            "language": "en",
            "source_country": "us",
            "sentiment": 0.2,
        },
        {
            "id": 206030984,
            "title": "Chipmaker unveils new processor",
            "text": "The processor targets data centers.",
            "summary": "New data-center chip announced.",
            "url": "https://example.com/chip",
            "image": "",
            "publish_date": "2026-11-06T08:00:00",
            "category": "technology",
            "language": "en",
        },
    ],
}


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self, *args, **kwargs) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:
        return False


def _http_error(code: int, body: dict | None = None) -> urllib.error.HTTPError:
    payload = json.dumps(body or {"error": "boom"}).encode("utf-8")
    return urllib.error.HTTPError(
        "https://api.worldnewsapi.com/search-news",
        code,
        "Error",
        hdrs=None,
        fp=__import__("io").BytesIO(payload),
    )


class WorldNewsAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = mock.patch.dict(
            os.environ, {"WORLD_NEWS_API_KEY": "test-key"}, clear=False
        )
        self._env.start()
        self.addCleanup(self._env.stop)
        self.settings = Settings.load(load_env=False)
        self.source = SourceConfig(
            id="worldnews",
            type="worldnews",
            url="https://api.worldnewsapi.com/search-news",
            name="World News API",
            weight=1.1,
            options={
                "query": "artificial intelligence technology",
                "language": "en",
                "max_items": 10,
                "sort": "publish-time",
                "trust": True,
            },
        )

    def _fetch(self, payload=None, error=None):
        patcher = mock.patch(
            "content_factory.sources.worldnews.urllib.request.urlopen",
            return_value=FakeResponse(payload or NEWS_RESPONSE),
            side_effect=error,
        )
        with patcher as urlopen:
            articles = WorldNewsAdapter().fetch(self.source, self.settings)
        return articles, urlopen

    def test_registered(self) -> None:
        self.assertIn("worldnews", available_types())
        self.assertIsInstance(get_adapter("worldnews"), WorldNewsAdapter)

    def test_missing_key_raises(self) -> None:
        with mock.patch.dict(os.environ, {"WORLD_NEWS_API_KEY": ""}, clear=False):
            with self.assertRaises(FetchError) as ctx:
                WorldNewsAdapter().fetch(self.source, self.settings)
        self.assertIn("WORLD_NEWS_API_KEY", str(ctx.exception))

    def test_fetch_parses_articles(self) -> None:
        articles, urlopen = self._fetch()
        self.assertEqual(len(articles), 2)
        first = articles[0]
        self.assertEqual(first.title, "AI startup raises $100M to build safer models")
        self.assertEqual(first.url, "https://example.com/ai-startup")
        self.assertTrue(first.text)
        self.assertEqual(first.meta["image"], "https://example.com/image.jpg")
        self.assertEqual(first.meta["category"], "technology")
        self.assertEqual(first.tags, ["technology"])
        self.assertEqual(first.published_at.tzinfo, timezone.utc)
        self.assertEqual(first.language, "en")
        self.assertEqual(articles[1].meta.get("image"), None)
        request = urlopen.call_args[0][0]
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
        self.assertEqual(query["text"], ["artificial intelligence technology"])
        self.assertEqual(query["language"], ["en"])
        self.assertEqual(query["number"], ["10"])
        self.assertEqual(query["sort"], ["publish-time"])
        self.assertIn("earliest-publish-date", query)
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(headers.get("x-api-key"), "test-key")

    def test_empty_news_returns_empty_list(self) -> None:
        articles, _ = self._fetch(payload={"news": []})
        self.assertEqual(articles, [])

    def test_quota_error_is_explained(self) -> None:
        with mock.patch(
            "content_factory.sources.worldnews.urllib.request.urlopen",
            side_effect=_http_error(402, {"message": "quota"}),
        ):
            with self.assertRaises(FetchError) as ctx:
                WorldNewsAdapter().fetch(self.source, self.settings)
        self.assertIn("лимит", str(ctx.exception))

    def test_invalid_key_is_explained(self) -> None:
        with mock.patch(
            "content_factory.sources.worldnews.urllib.request.urlopen",
            side_effect=_http_error(401),
        ):
            with self.assertRaises(FetchError) as ctx:
                WorldNewsAdapter().fetch(self.source, self.settings)
        self.assertIn("WORLD_NEWS_API_KEY", str(ctx.exception))

    def test_missing_query_raises(self) -> None:
        source = SourceConfig(
            id="bad", type="worldnews", url="https://api.worldnewsapi.com/search-news"
        )
        with self.assertRaises(FetchError) as ctx:
            WorldNewsAdapter().fetch(source, self.settings)
        self.assertIn("query", str(ctx.exception))

    def test_daily_limit_skips_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(load_env=False)
            settings.raw.setdefault("app", {})["data_dir"] = tmp
            source = SourceConfig(
                id="worldnews-limited",
                type="worldnews",
                url="https://api.worldnewsapi.com/search-news",
                name="World News API",
                options={"query": "ai news", "daily_limit": 1},
            )
            with mock.patch(
                "content_factory.sources.worldnews.urllib.request.urlopen",
                return_value=FakeResponse(NEWS_RESPONSE),
            ) as urlopen:
                first = WorldNewsAdapter().fetch(source, settings)
                second = WorldNewsAdapter().fetch(source, settings)
        self.assertEqual(len(first), 2)
        self.assertEqual(second, [])
        self.assertEqual(urlopen.call_count, 1)

    def test_check_reports_success(self) -> None:
        with mock.patch(
            "content_factory.sources.worldnews.urllib.request.urlopen",
            return_value=FakeResponse(NEWS_RESPONSE),
        ):
            ok, message = WorldNewsAdapter().check(self.source, self.settings)
        self.assertTrue(ok, message)


if __name__ == "__main__":
    unittest.main()
