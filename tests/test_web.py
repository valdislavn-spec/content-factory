"""Тесты веб-адаптера: сбор ссылок, домены, фильтры, лимиты, full_text."""
import unittest
from pathlib import Path
from unittest import mock

from content_factory.config import Settings
from content_factory.models import SourceConfig
from content_factory.sources.web import WebAdapter
from content_factory.utils import FetchError, url_hash

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SETTINGS = Settings.load()


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _source(**overrides) -> SourceConfig:
    data = {
        "id": "test-web",
        "type": "web",
        "url": "https://example.com/news",
        "name": "Веб-источник",
        "weight": 0.8,
        "options": {},
    }
    data.update(overrides)
    return SourceConfig(**data)


class WebAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = WebAdapter()
        self.listing = _fixture("sources_web_listing.html")

    def _fetch(self, page=None, source=None):
        source = source or _source(options={"link_contains": "/news/"})
        with mock.patch(
            "content_factory.sources.web.http_get_text", return_value=self.listing if page is None else page
        ):
            return self.adapter.fetch(source, SETTINGS)

    def test_collects_matching_links(self) -> None:
        articles = self._fetch()
        urls = [article.url for article in articles]
        self.assertEqual(len(articles), 3)
        self.assertIn("https://example.com/news/2026/10/one", urls)
        self.assertIn("https://example.com/news/2026/10/two?utm_source=page", urls)
        self.assertIn("https://example.com/news/2026/10/three", urls)
        self.assertNotIn("https://external.example.net/news/3", urls, "внешние домены запрещены")
        self.assertNotIn("https://example.com/news/2026/10/script", urls, "script не парсим")
        self.assertTrue(all(article.id == url_hash(article.url) for article in articles))

    def test_title_from_attribute_when_no_text(self) -> None:
        articles = self._fetch()
        titles = {article.url: article.title for article in articles}
        self.assertEqual(titles["https://example.com/news/2026/10/three"], "Третья новость из title")

    def test_relative_links_and_deduplication(self) -> None:
        articles = self._fetch()
        one = [article for article in articles if article.url.endswith("/one")]
        self.assertEqual(len(one), 1, "дубль ссылки должен быть отброшен")

    def test_max_items_option(self) -> None:
        articles = self._fetch(source=_source(options={"link_contains": "/news/", "max_items": 2}))
        self.assertEqual(len(articles), 2)

    def test_link_regex_option(self) -> None:
        source = _source(options={"link_regex": r"/news/2026/10/(one|two)"})
        articles = self._fetch(source=source)
        self.assertEqual(len(articles), 2)
        self.assertEqual(
            sorted(article.url for article in articles),
            [
                "https://example.com/news/2026/10/one",
                "https://example.com/news/2026/10/two?utm_source=page",
            ],
        )

    def test_no_filter_collects_all_internal_links(self) -> None:
        articles = self._fetch(source=_source(options={}))
        urls = {article.url for article in articles}
        self.assertEqual(len(articles), 4, "без фильтра берём все внутренние ссылки с текстом")
        self.assertIn("https://example.com/about", urls)
        self.assertNotIn("https://external.example.net/news/3", urls)

    def test_broken_html_does_not_crash(self) -> None:
        page = _fixture("sources_web_broken.html")
        articles = self._fetch(page=page, source=_source(options={"link_contains": "/news/"}))
        self.assertIsInstance(articles, list)

    def test_invalid_regex_falls_back_to_substring(self) -> None:
        articles = self._fetch(source=_source(options={"link_regex": "("}))
        self.assertEqual(articles, [])

    def test_full_text_downloads_article_page(self) -> None:
        page = _fixture("sources_article_page.html")
        source = _source(options={"link_contains": "/news/", "max_items": 1, "full_text": True})
        with mock.patch(
            "content_factory.sources.web.http_get_text", side_effect=[self.listing, page]
        ) as mocked:
            articles = self.adapter.fetch(source, SETTINGS)
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(len(articles), 1)
        self.assertIn("Первый полноценный абзац", articles[0].text)
        self.assertNotIn("alert", articles[0].text)
        self.assertTrue(articles[0].summary)

    def test_missing_url_raises(self) -> None:
        with self.assertRaises(FetchError):
            self.adapter.fetch(_source(url=""), SETTINGS)

    def test_network_error_raises(self) -> None:
        source = _source(options={"link_contains": "/news/"})
        with mock.patch(
            "content_factory.sources.web.http_get_text", side_effect=FetchError("нет соединения")
        ):
            with self.assertRaises(FetchError):
                self.adapter.fetch(source, SETTINGS)

    def test_check_ok(self) -> None:
        source = _source(options={"link_contains": "/news/"})
        with mock.patch("content_factory.sources.web.http_get_text", return_value=self.listing):
            ok, message = self.adapter.check(source, SETTINGS)
        self.assertTrue(ok)
        self.assertIn("доступен", message.lower())

    def test_check_error_is_reported(self) -> None:
        source = _source(options={"link_contains": "/news/"})
        with mock.patch(
            "content_factory.sources.web.http_get_text", side_effect=FetchError("ошибка сети")
        ):
            ok, message = self.adapter.check(source, SETTINGS)
        self.assertFalse(ok)
        self.assertIn("ошибка сети", message)


if __name__ == "__main__":
    unittest.main()
