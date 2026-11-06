"""Адаптер новостного API ESPN (site.api.espn.com).

Публичный endpoint ESPN отдаёт JSON без ключа: заголовок, описание, дату,
ссылку, картинку и автора — до 50 материалов на лигу. Обычные RSS-ленты ESPN
с 2025–2026 закрыты антибот-защитой (HTTP 202), поэтому для US-спорта
используется именно этот API.

Пример источника в config/channels.en.yaml:

    - id: espn-nfl
      type: espn
      url: https://site.api.espn.com/apis/site/v2/sports/football/nfl/news
      name: ESPN / NFL
      weight: 1.3
      options:
        sport: football/nfl
        max_items: 10
        trust: true

Поддерживаемые ``options``:
  * ``sport`` — путь лиги (``football/nfl``, ``basketball/nba``,
    ``baseball/mlb``, ``hockey/nhl``, ``football/college-football``,
    ``soccer/esp.1``, ``soccer/mex.1``);
    если не задан, берётся из URL источника;
  * ``lang`` — язык API (``en`` по умолчанию, ``es`` — испанские заголовки
    и описания, работает для футбольных лиг: ``soccer/esp.1``, ``mex.1`` и т.п.);
  * ``max_items`` — сколько материалов забрать (1–50, по умолчанию 10).
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
from typing import Any, Dict, List, Optional

from ..config import Settings
from ..models import Article, SourceConfig
from ..utils import FetchError, http_get_text, normalize_url, parse_datetime, strip_html
from .base import SourceAdapter, build_article, max_text_chars, request_params

logger = logging.getLogger(__name__)

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports"
DEFAULT_SPORT = "football/nfl"
DEFAULT_MAX_ITEMS = 10
MAX_ITEMS_CAP = 50
# ESPN чувствителен к User-Agent: UA с пометкой бота получает HTTP 403,
# поэтому для этого API всегда представляемся обычным браузером.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
REQUEST_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.espn.com/",
}


def _sport_of(source: SourceConfig) -> str:
    """Лига из options.sport или из URL вида .../sports/<sport>/news."""
    sport = str((source.options or {}).get("sport") or "").strip().strip("/")
    if sport:
        return sport
    raw = str(source.url or "").strip()
    if "/sports/" in raw:
        tail = raw.split("/sports/", 1)[1]
        if tail.endswith("/news"):
            tail = tail[: -len("/news")]
        tail = tail.split("?", 1)[0].strip("/")
        if tail:
            return tail
    return DEFAULT_SPORT


def _max_items(source: SourceConfig) -> int:
    raw = (source.options or {}).get("max_items", DEFAULT_MAX_ITEMS)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_ITEMS
    return max(1, min(MAX_ITEMS_CAP, value))


def _web_url(item: Dict[str, Any]) -> str:
    """Ссылка на материал: links.web.href (или поле link)."""
    links = item.get("links")
    if isinstance(links, dict):
        web = links.get("web")
        if isinstance(web, dict):
            href = str(web.get("href") or "").strip()
            if href:
                return href
    return str(item.get("link") or "").strip()


def _image_url(item: Dict[str, Any]) -> str:
    """Картинка: предпочитаем header, иначе первую с URL."""
    images = item.get("images")
    if not isinstance(images, list):
        return ""
    fallback = ""
    for image in images:
        if not isinstance(image, dict):
            continue
        url = str(image.get("url") or "").strip()
        if not url:
            continue
        if str(image.get("type") or "").lower() == "header":
            return url
        if not fallback:
            fallback = url
    return fallback


def _tags_of(item: Dict[str, Any]) -> List[str]:
    tags: List[str] = []
    for category in item.get("categories") or []:
        if not isinstance(category, dict):
            continue
        value = str(category.get("description") or category.get("type") or "").strip()
        if value and value not in tags:
            tags.append(value)
    return tags[:10]


def _published_at(value: Any) -> Any:
    raw = str(value or "").strip()
    return parse_datetime(raw) if raw else None


class ESPNAdapter(SourceAdapter):
    """Новости ESPN по лиге (NFL/NBA/MLB/NHL/college football)."""

    type = "espn"

    def build_url(self, source: SourceConfig, settings: Settings) -> str:
        sport = _sport_of(source)
        base = str(source.url or "").strip() or "{}/{}/news".format(BASE_URL, sport)
        parts = urllib.parse.urlsplit(base)
        query = dict(urllib.parse.parse_qsl(parts.query))
        query["limit"] = str(_max_items(source))
        options = source.options or {}
        lang = str(options.get("lang") or options.get("language") or "").strip().lower()
        if lang in ("en", "es"):
            query["lang"] = lang
        return urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment)
        )

    def _request(self, url: str, source: SourceConfig, settings: Settings) -> Dict[str, Any]:
        params = request_params(settings)
        try:
            raw = http_get_text(
                url,
                timeout=params["timeout"],
                user_agent=BROWSER_USER_AGENT,
                headers=REQUEST_HEADERS,
                retries=params["retries"],
            )
        except FetchError:
            raise
        except urllib.error.HTTPError as exc:  # pragma: no cover - http_get_text уже оборачивает
            raise FetchError("espn: HTTP {} ({})".format(exc.code, source.id)) from exc
        except Exception as exc:  # pragma: no cover - защита от неожиданных ошибок
            raise FetchError("espn: сеть недоступна: {}".format(exc)) from exc
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise FetchError("espn: ответ не JSON ({})".format(source.id)) from exc
        if not isinstance(data, dict):
            raise FetchError("espn: неожиданный формат ответа")
        return data

    def _article(
        self, item: Dict[str, Any], source: SourceConfig, settings: Settings
    ) -> Optional[Article]:
        if not isinstance(item, dict):
            return None
        url = _web_url(item)
        if not url:
            return None
        headline = strip_html(str(item.get("headline") or item.get("title") or ""))
        if not headline:
            return None
        description = strip_html(str(item.get("description") or ""))
        # Описания ESPN короткие (1–2 предложения): добавляем заголовок,
        # чтобы сюжет проходил порог min_cluster_chars и был осмысленным.
        text = description
        if len(text) < 400:
            text = (headline + ". " + text).strip() if text else headline
        limit = max_text_chars(settings)
        if len(text) > limit:
            text = text[:limit].rsplit(" ", 1)[0]
        summary = description or headline
        tags = _tags_of(item)
        meta: Dict[str, Any] = {
            "espn_id": item.get("id"),
            "sport": _sport_of(source),
            "byline": str(item.get("byline") or "").strip(),
            "image": _image_url(item),
        }
        meta = {key: value for key, value in meta.items() if value not in ("", None)}
        return build_article(
            source,
            settings,
            url=url,
            title=headline,
            published_at=_published_at(item.get("published")),
            text=text,
            summary=summary,
            tags=tags,
            meta=meta,
        )

    def fetch(self, source: SourceConfig, settings: Settings) -> List[Article]:
        url = self.build_url(source, settings)
        data = self._request(url, source, settings)
        items = data.get("articles")
        if not isinstance(items, list):
            return []
        articles: List[Article] = []
        seen: set = set()
        for item in items:
            article = self._article(item, source, settings)
            if article is None:
                continue
            key = normalize_url(article.url)
            if key in seen:
                continue
            seen.add(key)
            articles.append(article)
        logger.info("ESPN[%s]: новостей %d", source.id, len(articles))
        return articles


__all__ = ["ESPNAdapter", "BASE_URL", "DEFAULT_SPORT"]
