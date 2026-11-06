"""Тесты ESPN-адаптера: разбор JSON API, URL, картинки и ошибки."""
import json
import unittest
from datetime import datetime, timezone
from unittest import mock

from content_factory.config import Settings
from content_factory.models import SourceConfig
from content_factory.sources.espn import ESPNAdapter
from content_factory.utils import FetchError

SETTINGS = Settings.load()

PAYLOAD = {
    "articles": [
        {
            "id": 50402162,
            "headline": "Giants' Cam Skattebo doubtful vs. Eagles",
            "description": "Giants running back Cam Skattebo is unlikely to play on Sunday.",
            "published": "2026-11-06T22:38:03Z",
            "byline": "Jordan Raanan",
            "links": {"web": {"href": "https://www.espn.com/nfl/story/_/id/1/test-story"}},
            "images": [
                {"type": "header", "url": "https://a.espncdn.com/photo/2026/1106/header.jpg"},
                {"type": "body", "url": "https://a.espncdn.com/photo/2026/1106/body.jpg"},
            ],
            "categories": [{"type": "team", "description": "New York Giants"}],
        },
        {
            "id": 2,
            "headline": "NBA roundup: Lakers win again",
            "description": "",
            "published": "2026-11-06T20:00:00Z",
            "links": {"web": {"href": "https://www.espn.com/nba/story/_/id/2/roundup"}},
            "images": [],
            "categories": [],
        },
        {
            "id": 3,
            "headline": "No link — should be skipped",
            "links": {},
        },
    ]
}


def _source(**overrides) -> SourceConfig:
    data = {
        "id": "espn-nfl",
        "type": "espn",
        "url": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news",
        "name": "ESPN / NFL",
        "weight": 1.3,
        "options": {"sport": "football/nfl", "max_items": 10, "trust": True},
    }
    data.update(overrides)
    return SourceConfig(**data)


class ESPNAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = ESPNAdapter()

    def _fetch(self, payload, source=None):
        source = source or _source()
        raw = json.dumps(payload)
        with mock.patch("content_factory.sources.espn.http_get_text", return_value=raw) as patched:
            articles = self.adapter.fetch(source, SETTINGS)
        return articles, patched

    def test_fetch_parses_articles(self) -> None:
        articles, _ = self._fetch(PAYLOAD)
        self.assertEqual(len(articles), 2, "третья запись без ссылки должна быть пропущена")
        first = articles[0]
        self.assertEqual(first.title, "Giants' Cam Skattebo doubtful vs. Eagles")
        self.assertEqual(first.url, "https://www.espn.com/nfl/story/_/id/1/test-story")
        self.assertEqual(first.source_id, "espn-nfl")
        self.assertEqual(first.tags, ["New York Giants"])
        self.assertEqual(first.published_at, datetime(2026, 11, 6, 22, 38, 3, tzinfo=timezone.utc))
        self.assertIn("Giants", first.text)
        self.assertIn("unlikely to play", first.summary)
        self.assertEqual(first.meta["image"], "https://a.espncdn.com/photo/2026/1106/header.jpg")
        self.assertEqual(first.meta["byline"], "Jordan Raanan")
        self.assertEqual(first.meta["sport"], "football/nfl")

    def test_fetch_adds_headline_to_short_description(self) -> None:
        articles, _ = self._fetch(PAYLOAD)
        second = articles[1]
        self.assertEqual(second.text, "NBA roundup: Lakers win again")
        self.assertEqual(second.summary, "NBA roundup: Lakers win again")

    def test_build_url_uses_sport_and_limit(self) -> None:
        source = _source(url="", options={"sport": "basketball/nba", "max_items": 7})
        url = self.adapter.build_url(source, SETTINGS)
        self.assertIn("/sports/basketball/nba/news", url)
        self.assertIn("limit=7", url)

    def test_sport_derived_from_url(self) -> None:
        source = _source(url="https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/news", options={})
        self.assertIn("hockey/nhl", self.adapter.build_url(source, SETTINGS))

    def test_invalid_json_raises_fetch_error(self) -> None:
        with mock.patch("content_factory.sources.espn.http_get_text", return_value="<html>blocked</html>"):
            with self.assertRaises(FetchError):
                self.adapter.fetch(_source(), SETTINGS)

    def test_empty_articles_returns_empty_list(self) -> None:
        articles, _ = self._fetch({"articles": []})
        self.assertEqual(articles, [])


if __name__ == "__main__":
    unittest.main()
