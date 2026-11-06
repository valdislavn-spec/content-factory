"""Тесты RSS/Atom-адаптера: поля, кодировки, битые ленты, full_text, check."""
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from content_factory.config import Settings
from content_factory.models import SourceConfig
from content_factory.sources.rss import RSSAdapter
from content_factory.utils import FetchError, normalize_url, url_hash

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SETTINGS = Settings.load()


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _source(**overrides) -> SourceConfig:
    data = {
        "id": "test-rss",
        "type": "rss",
        "url": "https://example.com/feed",
        "name": "Тестовая лента",
        "weight": 1.3,
        "options": {},
    }
    data.update(overrides)
    return SourceConfig(**data)


class RSSAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = RSSAdapter()

    def _fetch(self, text, source=None):
        source = source or _source()
        with mock.patch("content_factory.sources.rss.http_get_text", return_value=text):
            return self.adapter.fetch(source, SETTINGS)

    # ------------------------------------------------------------------
    # RSS 2.0
    # ------------------------------------------------------------------
    def test_rss2_fields(self) -> None:
        articles = self._fetch(_fixture("sources_rss2.xml"))
        self.assertEqual(len(articles), 3, "дубль по URL должен быть отброшен")
        first = articles[0]
        self.assertEqual(first.title, "Первая новость об ИИ")
        self.assertEqual(first.url, "https://example.com/news/1?utm_source=rss")
        self.assertEqual(first.source_id, "test-rss")
        self.assertEqual(first.source_name, "Тестовая лента")
        self.assertEqual(first.weighted_source_score, 1.3)
        self.assertAlmostEqual(first.summary, "Описание первой новости.")
        self.assertEqual(first.tags, ["ИИ"])
        self.assertEqual(first.meta["author"], "Иван Петров")
        self.assertEqual(first.meta["url_hash"], url_hash(first.url))
        self.assertEqual(first.id, url_hash(first.url))
        self.assertIsNotNone(first.published_at.tzinfo)
        self.assertEqual(first.published_at.astimezone(timezone.utc).year, 2026)

    def test_rss2_relative_link_and_date_fallback(self) -> None:
        articles = self._fetch(_fixture("sources_rss2.xml"))
        second = articles[1]
        self.assertEqual(second.url, "https://example.com/news/2", "относительная ссылка должна стать абсолютной")
        self.assertEqual(second.published_at.astimezone(timezone.utc).hour, 6)  # 09:30+03:00 = 06:30 UTC
        third = articles[2]
        self.assertLess(abs((datetime.now(timezone.utc) - third.published_at).total_seconds()), 120)
        self.assertTrue(third.published_at.tzinfo, "дата без времени должна быть timezone-aware")

    def test_duplicate_urls_are_dropped(self) -> None:
        articles = self._fetch(_fixture("sources_rss2.xml"))
        hashes = [article.id for article in articles]
        self.assertEqual(len(hashes), len(set(hashes)))
        urls = {normalize_url(article.url) for article in articles}
        self.assertIn(normalize_url("https://example.com/news/1"), urls)
        self.assertNotIn("https://example.com/news/1?utm_medium=rss", urls)

    # ------------------------------------------------------------------
    # Atom
    # ------------------------------------------------------------------
    def test_atom_namespaces_and_alternate_link(self) -> None:
        articles = self._fetch(
            _fixture("sources_atom.xml"), _source(url="https://example.org/feed")
        )
        self.assertEqual(len(articles), 2)
        first = articles[0]
        self.assertEqual(first.title, "Заголовок Atom")
        self.assertEqual(first.url, "https://example.org/posts/10", "нужен rel=alternate, а не rel=self")
        self.assertAlmostEqual(first.summary, "Краткое описание записи.")
        self.assertEqual(first.tags, ["наука"])
        self.assertEqual(first.meta["author"], "Мария")
        self.assertEqual(first.published_at.astimezone(timezone.utc).day, 13)
        second = articles[1]
        self.assertEqual(second.url, "https://example.org/posts/11")
        self.assertEqual(second.published_at.astimezone(timezone.utc).hour, 5)  # 08:00+03:00

    # ------------------------------------------------------------------
    # Кодировки и «лечение» XML
    # ------------------------------------------------------------------
    def test_cp1251_feed(self) -> None:
        raw = (FIXTURES / "sources_cp1251.xml").read_bytes()
        text = raw.decode("cp1251")
        articles = self._fetch(text)
        self.assertEqual(len(articles), 1)
        self.assertIn("windows-1251", articles[0].title)
        self.assertEqual(articles[0].summary, "Описание на русском языке.")

    def test_bom_and_leading_spaces(self) -> None:
        articles = self._fetch("\ufeff \n" + _fixture("sources_rss2.xml"))
        self.assertEqual(len(articles), 3)

    def test_broken_entities_are_recovered(self) -> None:
        articles = self._fetch(_fixture("sources_entities.xml"))
        self.assertEqual(len(articles), 1)
        self.assertIn("Новость с сущностью", articles[0].title)
        self.assertIn("—", articles[0].summary)

    def test_broken_xml_raises_fetch_error(self) -> None:
        with self.assertRaises(FetchError):
            self._fetch(_fixture("sources_broken.xml"))

    def test_empty_feed_returns_empty_list(self) -> None:
        self.assertEqual(self._fetch(_fixture("sources_empty.xml")), [])

    # ------------------------------------------------------------------
    # Лимиты, full_text, check
    # ------------------------------------------------------------------
    def test_max_items_option(self) -> None:
        articles = self._fetch(_fixture("sources_rss2.xml"), _source(options={"max_items": 2}))
        self.assertEqual(len(articles), 2)

    def test_full_text_downloads_article_page(self) -> None:
        feed = _fixture("sources_rss2.xml")
        page = _fixture("sources_article_page.html")
        source = _source(options={"max_items": 1, "full_text": True})
        with mock.patch("content_factory.sources.rss.http_get_text", side_effect=[feed, page]) as mocked:
            articles = self.adapter.fetch(source, SETTINGS)
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(len(articles), 1)
        article = articles[0]
        self.assertIn("Первый полноценный абзац", article.text)
        self.assertIn("Второй абзац", article.text)
        self.assertNotIn("alert", article.text)
        # summary остаётся из description ленты
        self.assertAlmostEqual(article.summary, "Описание первой новости.")

    def test_title_falls_back_to_description(self) -> None:
        feed = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0"><channel><item>
          <link>https://example.com/news/9</link>
          <description>Описание без заголовка в самой ленте.</description>
        </item></channel></rss>"""
        articles = self._fetch(feed)
        self.assertEqual(len(articles), 1)
        self.assertTrue(articles[0].title)
        self.assertIn("Описание", articles[0].title)

    def test_check_ok(self) -> None:
        with mock.patch(
            "content_factory.sources.rss.http_get_text", return_value=_fixture("sources_rss2.xml")
        ) as mocked:
            ok, message = self.adapter.check(_source(), SETTINGS)
        self.assertTrue(ok)
        self.assertIn("доступен", message.lower())
        self.assertEqual(mocked.call_count, 1, "check должен делать один запрос")

    def test_check_empty_feed(self) -> None:
        with mock.patch(
            "content_factory.sources.rss.http_get_text", return_value=_fixture("sources_empty.xml")
        ):
            ok, message = self.adapter.check(_source(), SETTINGS)
        self.assertTrue(ok)
        self.assertIn("не найдено", message)

    def test_check_network_error(self) -> None:
        with mock.patch(
            "content_factory.sources.rss.http_get_text",
            side_effect=FetchError("сеть недоступна"),
        ):
            ok, message = self.adapter.check(_source(), SETTINGS)
        self.assertFalse(ok)
        self.assertIn("сеть недоступна", message)


if __name__ == "__main__":
    unittest.main()
