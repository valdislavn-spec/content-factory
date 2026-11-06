"""Тесты адаптеров newsdata.io и Currents API (без сети)."""

from __future__ import annotations

import json
import os
import unittest
import urllib.parse
from datetime import timezone
from unittest import mock

from content_factory.config import Settings
from content_factory.models import SourceConfig
from content_factory.sources import available_types, get_adapter
from content_factory.sources.jsonnews import CurrentsAdapter, NewsDataAdapter
from content_factory.utils import FetchError

NEWSDATA_RESPONSE = {
    "status": "success",
    "results": [
        {
            "article_id": "a1",
            "title": "AI startup raises new round",
            "link": "https://example.com/newsdata-ai",
            "description": "Short description",
            "content": "Full article text about the funding round.",
            "image_url": "https://cdn.example.com/newsdata.jpg",
            "pubDate": "2026-11-06 09:00:00",
            "source_name": "Example News",
            "category": ["technology"],
            "language": "en",
        }
    ],
}

CURRENTS_RESPONSE = {
    "status": "ok",
    "news": [
        {
            "id": "c1",
            "title": "Electric vehicles sales grow",
            "url": "https://example.com/currents-ev",
            "description": "EV sales description",
            "image": "https://cdn.example.com/currents.jpg",
            "published": "2026-11-06 09:00:00 +0000",
            "category": ["automotive"],
            "author": "Jane Doe",
        }
    ],
}


class JsonNewsAdaptersTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = mock.patch.dict(
            os.environ,
            {"NEWSDATA_API_KEY": "nd-key", "CURRENTS_API_KEY": "cur-key"},
            clear=False,
        )
        self._env.start()
        self.addCleanup(self._env.stop)
        self.settings = Settings.load(load_env=False)

    def test_registered(self) -> None:
        self.assertIn("newsdata", available_types())
        self.assertIn("currents", available_types())
        self.assertIsInstance(get_adapter("newsdata"), NewsDataAdapter)
        self.assertIsInstance(get_adapter("currents"), CurrentsAdapter)

    def _source(self, source_type: str) -> SourceConfig:
        return SourceConfig(
            id=source_type,
            type=source_type,
            url="https://api.example.com/latest"
            if source_type == "newsdata"
            else "https://api.example.com/latest-news",
            name=source_type,
            options={"query": "artificial intelligence", "language": "en", "max_items": 5},
        )

    def test_newsdata_parses_article(self) -> None:
        with mock.patch(
            "content_factory.sources.jsonnews.http_get_text",
            return_value=json.dumps(NEWSDATA_RESPONSE),
        ) as get:
            articles = NewsDataAdapter().fetch(self._source("newsdata"), self.settings)
        self.assertEqual(len(articles), 1)
        article = articles[0]
        self.assertEqual(article.title, "AI startup raises new round")
        self.assertEqual(article.meta["image"], "https://cdn.example.com/newsdata.jpg")
        self.assertEqual(article.tags, ["technology"])
        self.assertEqual(article.published_at.tzinfo, timezone.utc)
        url = get.call_args[0][0]
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(query["apikey"], ["nd-key"])
        self.assertEqual(query["q"], ["artificial intelligence"])
        self.assertEqual(query["size"], ["5"])

    def test_currents_parses_article(self) -> None:
        with mock.patch(
            "content_factory.sources.jsonnews.http_get_text",
            return_value=json.dumps(CURRENTS_RESPONSE),
        ) as get:
            articles = CurrentsAdapter().fetch(self._source("currents"), self.settings)
        self.assertEqual(len(articles), 1)
        article = articles[0]
        self.assertEqual(article.title, "Electric vehicles sales grow")
        self.assertEqual(article.meta["image"], "https://cdn.example.com/currents.jpg")
        url = get.call_args[0][0]
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(query["apiKey"], ["cur-key"])
        self.assertEqual(query["keywords"], ["artificial intelligence"])

    def test_missing_key_raises(self) -> None:
        with mock.patch.dict(os.environ, {"NEWSDATA_API_KEY": ""}, clear=False):
            with self.assertRaises(FetchError) as ctx:
                NewsDataAdapter().fetch(self._source("newsdata"), self.settings)
        self.assertIn("NEWSDATA_API_KEY", str(ctx.exception))

    def test_broken_json_raises(self) -> None:
        with mock.patch(
            "content_factory.sources.jsonnews.http_get_text", return_value="not json"
        ):
            with self.assertRaises(FetchError):
                CurrentsAdapter().fetch(self._source("currents"), self.settings)


if __name__ == "__main__":
    unittest.main()
