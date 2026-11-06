"""Адаптер веб-страниц: собирает ссылки на материалы со страницы-анонса.

Используется для сайтов без RSS. Адаптер не ходит по внешним доменам,
отбрасывает пустые/битые ссылки и умеет фильтровать ссылки регулярным
выражением (``options.link_regex``) или подстрокой/шаблоном
(``options.link_contains``). Дополнительно можно включить ``full_text``,
чтобы скачать каждую статью и извлечь текст абзацев.
"""
from __future__ import annotations

import re
import urllib.parse
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

from ..config import Settings
from ..models import Article, SourceConfig, utcnow
from ..utils import FetchError, http_get_text, normalize_url, strip_html
from .base import (
    SourceAdapter,
    absolute_url,
    build_article,
    clean_title,
    extract_paragraphs,
    make_summary,
    max_text_chars,
    request_params,
    same_domain,
)

DEFAULT_MAX_ITEMS = 30
_SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}


def _positive_int(value: Any, default: int, minimum: int = 1, maximum: int = 200) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


class _AnchorParser(HTMLParser):
    """Собирает ссылки и их подписи со страницы, игнорируя script/style."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: List[Tuple[str, str]] = []
        self.base_href = ""
        self._href: Optional[str] = None
        self._text: List[str] = []
        self._title_attr = ""
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "base":
            for name, value in attrs:
                if name == "href" and value:
                    self.base_href = value.strip()
            return
        if tag == "a":
            # Битый HTML с вложенными <a> — фиксируем предыдущую ссылку.
            if self._href is not None:
                self._flush()
            attributes = {name: (value or "") for name, value in attrs}
            self._href = attributes.get("href", "").strip()
            self._title_attr = (attributes.get("title") or attributes.get("aria-label") or "").strip()
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag == "a" and self._href is not None:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._href is not None and not self._skip_depth:
            self._text.append(data)

    def _flush(self) -> None:
        href = self._href or ""
        text = strip_html("".join(self._text)) or strip_html(self._title_attr)
        self._href = None
        self._text = []
        self._title_attr = ""
        if href and text:
            self.links.append((href, text))

    def result(self) -> List[Tuple[str, str]]:
        if self._href is not None:
            self._flush()
        return self.links


def _link_matcher(options: Dict[str, Any]):
    """Строит предикат фильтрации ссылок по link_regex/link_contains."""
    patterns: List[Tuple[str, Any]] = []
    for option_name in ("link_regex", "link_contains"):
        raw = options.get(option_name)
        if raw is None or raw == "":
            continue
        if isinstance(raw, (list, tuple)):
            values = [str(item) for item in raw if str(item)]
        else:
            values = [str(raw)]
        for value in values:
            try:
                patterns.append(("regex", re.compile(value, re.IGNORECASE)))
            except re.error:
                patterns.append(("substring", value.lower()))

    def matches(href: str) -> bool:
        for kind, pattern in patterns:
            if kind == "regex":
                if not pattern.search(href):
                    return False
            elif pattern not in href.lower():
                return False
        return True

    return matches


class WebAdapter(SourceAdapter):
    """Адаптер страницы со списком материалов.

    Поддерживаемые options:
      * ``link_contains`` — подстрока или регулярное выражение в href;
      * ``link_regex`` — регулярное выражение для href (приоритет по смыслу
        тот же: оба фильтра применяются одновременно);
      * ``max_items`` — сколько ссылок забрать (по умолчанию 30);
      * ``full_text`` — true, чтобы скачать каждую статью (по умолчанию false);
      * ``same_domain`` — false, чтобы разрешить внешние домены (по умолчанию
        запрещены).
    """

    type = "web"

    def fetch(self, source: SourceConfig, settings: Settings) -> List[Article]:
        if not source.url:
            raise FetchError(f"Источник {source.id}: не задан URL страницы")
        options = source.options or {}
        max_items = _positive_int(options.get("max_items"), DEFAULT_MAX_ITEMS)
        full_text = bool(options.get("full_text", False))
        restrict_domain = bool(options.get("same_domain", True))
        matches = _link_matcher(options)

        params = request_params(settings)
        try:
            page = http_get_text(
                source.url,
                timeout=params["timeout"],
                user_agent=params["user_agent"],
                retries=params["retries"],
            )
        except FetchError:
            raise
        except Exception as exc:  # pragma: no cover - http_get_text сам бросает FetchError
            raise FetchError(f"Ошибка загрузки страницы {source.url}: {exc}") from exc
        if not page:
            raise FetchError(f"Источник {source.id}: пустой ответ страницы")

        parser = _AnchorParser()
        try:
            parser.feed(page)
            parser.close()
            anchors = parser.result()
        except Exception:  # pragma: no cover - HTMLParser устойчив, но бережёмся
            anchors = []
        base_url = absolute_url(source.url, parser.base_href) or source.url
        page_key = normalize_url(source.url)

        articles: List[Article] = []
        seen_urls: set = set()
        for href, link_text in anchors:
            if len(articles) >= max_items:
                break
            url = absolute_url(base_url, href)
            if not url:
                continue
            url_key = normalize_url(url)
            if not url_key or url_key == page_key or url_key in seen_urls:
                continue
            if restrict_domain and not same_domain(source.url, url):
                continue
            if not matches(href):
                continue
            title = clean_title(link_text)
            if not title:
                continue
            seen_urls.add(url_key)

            article_text = ""
            if full_text:
                article_text = self._fetch_article_text(url, settings)
            article = build_article(
                source=source,
                settings=settings,
                url=url,
                title=title,
                published_at=utcnow(),
                text=article_text,
                summary=make_summary(article_text),
                meta={"listing_url": source.url},
            )
            if article is not None:
                articles.append(article)
        return articles

    def _fetch_article_text(self, url: str, settings: Settings) -> str:
        """Догружает страницу статьи и извлекает абзацы (для options.full_text)."""
        params = request_params(settings)
        try:
            page = http_get_text(
                url,
                timeout=params["timeout"],
                user_agent=params["user_agent"],
                retries=params["retries"],
            )
        except Exception:
            # Текст статьи необязателен: ссылка остаётся валидной и без него.
            return ""
        return extract_paragraphs(page, limit=max_text_chars(settings))


__all__ = ["WebAdapter", "DEFAULT_MAX_ITEMS"]
