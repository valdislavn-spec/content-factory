"""Тесты адаптера анонсов BingX (без сети)."""

from __future__ import annotations

from unittest import mock

from content_factory.config import Settings
from content_factory.models import SourceConfig
from content_factory.sources.bingx import BingXAnnouncementsAdapter

SECTION_HTML = """
<ul class="article-list">
  <li class="article-item"><a href="/en/support/articles/18299493475983/" data-v="1">
    <div class="article-title">BingX Delists DOPEUSDT for Perpetual Futures</div>
    <div class="article-publish-time">2026-11-08</div></a></li>
  <li class="article-item"><a href="/en/support/articles/18283614499087/">
    <div class="article-title">BingX Adds GM, CHOO for Perpetual Futures</div>
    <div class="article-publish-time">2026-11-06</div></a></li>
  <li class="article-item"><a href="/en/support/articles/18299493475983/">
    <div class="article-title">Duplicate link should be skipped</div>
    <div class="article-publish-time">2026-11-08</div></a></li>
</ul>
"""

ARTICLE_HTML = """
<div class="article-body-part"><h1>BingX Delists DOPEUSDT</h1>
<p>BingX periodically reviews assets. Affected pairs: DOPEUSDT.</p></div>
"""


def _source(**options):
    return SourceConfig(
        id="bingx-announcements",
        type="bingx",
        url="https://bingx.com/en/support/notice-center",
        name="BingX",
        options={"sections": ["latest"], "max_items": 5, "full_text": True, **options},
    )


def test_fetch_parses_titles_dates_and_dedupes() -> None:
    settings = Settings.load()
    calls = []

    def fake_get(url, timeout=20.0, user_agent=""):
        calls.append(url)
        return ARTICLE_HTML if "support/articles" in url else SECTION_HTML

    adapter = BingXAnnouncementsAdapter()
    with mock.patch("content_factory.sources.bingx.http_get_text", side_effect=fake_get):
        articles = adapter.fetch(_source(), settings)
    assert [a.title for a in articles] == [
        "BingX Delists DOPEUSDT for Perpetual Futures",
        "BingX Adds GM, CHOO for Perpetual Futures",
    ]
    assert articles[0].url.endswith("/support/articles/18299493475983")
    assert "BingX periodically reviews" in articles[0].text
    assert articles[0].published_at.year == 2026
    # один запрос секции + по запросу на каждую уникальную статью
    assert sum("notice-center" in u for u in calls) == 1
    assert sum("support/articles" in u for u in calls) == 2


def test_fetch_without_full_text_uses_title() -> None:
    settings = Settings.load()

    with mock.patch(
        "content_factory.sources.bingx.http_get_text", return_value=SECTION_HTML
    ):
        articles = BingXAnnouncementsAdapter().fetch(_source(full_text=False), settings)
    assert len(articles) == 2
    assert articles[0].text == articles[0].title


def test_max_items_limit() -> None:
    settings = Settings.load()
    with mock.patch(
        "content_factory.sources.bingx.http_get_text", return_value=SECTION_HTML
    ):
        articles = BingXAnnouncementsAdapter().fetch(
            _source(full_text=False, max_items=1), settings
        )
    assert len(articles) == 1
