"""Адаптеры JSON-новостных API: newsdata.io и Currents API.

Оба сервиса отдают новости по ключевому слову/языку, включая картинку статьи
(``image_url`` / ``image``), дату публикации и краткое описание. Ключи берутся
из ``NEWSDATA_API_KEY`` / ``CURRENTS_API_KEY``; в конфиге канала не хранятся.

Пример источника:

    - id: newsdata
      type: newsdata
      url: https://newsdata.io/api/1/latest
      name: newsdata.io
      weight: 1.0
      options:
        query: artificial intelligence technology
        language: en
        max_items: 10
        trust: true
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..config import Settings
from ..models import Article, SourceConfig
from ..utils import FetchError, env, http_get_text, strip_html
from .base import SourceAdapter, build_article, max_text_chars, request_params, source_budget

logger = logging.getLogger(__name__)

NEWSDATA_URL = "https://newsdata.io/api/1/latest"
CURRENTS_URL = "https://api.currentsapi.services/v1/latest-news"
DEFAULT_MAX_ITEMS = 10


def _parse_date(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _get_json(url: str, settings: Settings) -> Dict[str, Any]:
    params = request_params(settings)
    try:
        raw = http_get_text(
            url,
            timeout=params["timeout"],
            user_agent=params["user_agent"],
            retries=params["retries"],
        )
    except FetchError:
        raise
    except urllib.error.HTTPError as exc:  # pragma: no cover - http_get_text уже оборачивает
        raise FetchError("HTTP {}: {}".format(exc.code, url)) from exc
    except Exception as exc:
        raise FetchError("сеть недоступна: {}".format(exc)) from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise FetchError("ответ не JSON: {}".format(raw[:120])) from exc
    if not isinstance(data, dict):
        raise FetchError("неожиданный формат ответа")
    return data


def _text_of(item: Dict[str, Any]) -> tuple:
    text = strip_html(str(item.get("content") or item.get("text") or ""))
    summary = strip_html(str(item.get("description") or item.get("summary") or ""))
    return text, summary


def _tags_of(item: Dict[str, Any]) -> List[str]:
    category = item.get("category")
    if isinstance(category, list):
        return [str(value) for value in category if value][:5]
    if category:
        return [str(category)]
    return []


class _JsonNewsAdapter(SourceAdapter):
    """Базовая логика JSON-новостного адаптера."""

    key_env = ""
    default_url = ""
    query_param = "q"

    def _key(self, source: SourceConfig) -> str:
        name = str((source.options or {}).get("api_key_env") or self.key_env)
        return env(name, "") or ""

    def _request_url(self, source: SourceConfig, settings: Settings) -> str:
        raise NotImplementedError

    def _items(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def _map_item(
        self, item: Dict[str, Any], source: SourceConfig, settings: Settings
    ) -> Optional[Article]:
        url = str(item.get("link") or item.get("url") or "").strip()
        if not url:
            return None
        text, summary = _text_of(item)
        limit = max_text_chars(settings)
        if len(text) > limit:
            text = text[:limit].rsplit(" ", 1)[0]
        image = str(
            item.get("image_url")
            or item.get("image")
            or (item.get("source") or {}).get("image")
            or ""
        ).strip()
        source_name = str(
            item.get("source_name")
            or item.get("source_id")
            or (item.get("source") or {}).get("name")
            or item.get("author")
            or ""
        ).strip()
        meta = {"image": image, "provider": self.type, "feed_url": source.url}
        if source_name:
            meta["source_name"] = source_name
        meta = {key: value for key, value in meta.items() if value not in ("", None)}
        return build_article(
            source,
            settings,
            url=url,
            title=str(item.get("title") or ""),
            published_at=_parse_date(item.get("pubDate") or item.get("published") or item.get("publishedAt")),
            text=text,
            summary=summary,
            tags=_tags_of(item),
            meta=meta,
        )

    def fetch(self, source: SourceConfig, settings: Settings) -> List[Article]:
        if not self._key(source):
            raise FetchError(
                "{}: не задан {} (см. scripts/set_extra_keys.py)".format(
                    self.type, self.key_env
                )
            )
        budget = source_budget(source, settings)
        if budget is not None and not budget.try_consume(1):
            logger.info("%s[%s]: %s — источник пропущен", self.type, source.id, budget.describe())
            return []
        data = _get_json(self._request_url(source, settings), settings)
        items = self._items(data)
        articles: List[Article] = []
        seen = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            article = self._map_item(item, source, settings)
            if article is None or article.id in seen:
                continue
            seen.add(article.id)
            articles.append(article)
        logger.info("%s[%s]: новостей %d", self.type, source.id, len(articles))
        return articles


class NewsDataAdapter(_JsonNewsAdapter):
    """newsdata.io API (``/api/1/latest``)."""

    type = "newsdata"
    key_env = "NEWSDATA_API_KEY"
    default_url = NEWSDATA_URL
    query_param = "q"

    def _request_url(self, source: SourceConfig, settings: Settings) -> str:
        options = source.options or {}
        try:
            size = max(1, min(10, int(options.get("max_items") or DEFAULT_MAX_ITEMS)))
        except (TypeError, ValueError):
            size = DEFAULT_MAX_ITEMS
        params: Dict[str, Any] = {
            "apikey": self._key(source),
            "language": str(options.get("language") or "en"),
            "size": size,
        }
        query = str(options.get("query") or "").strip()
        if query:
            params["q"] = query
        category = str(options.get("category") or "").strip()
        if category:
            params["category"] = category
        base = str(source.url or self.default_url)
        return base + "?" + urllib.parse.urlencode(params)

    def _items(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        results = data.get("results")
        return results if isinstance(results, list) else []


class CurrentsAdapter(_JsonNewsAdapter):
    """Currents API (``/v1/latest-news``)."""

    type = "currents"
    key_env = "CURRENTS_API_KEY"
    default_url = CURRENTS_URL
    query_param = "keywords"

    def _request_url(self, source: SourceConfig, settings: Settings) -> str:
        options = source.options or {}
        try:
            limit = max(1, min(10, int(options.get("max_items") or DEFAULT_MAX_ITEMS)))
        except (TypeError, ValueError):
            limit = DEFAULT_MAX_ITEMS
        params: Dict[str, Any] = {
            "apiKey": self._key(source),
            "language": str(options.get("language") or "en"),
            "page_size": limit,
        }
        query = str(options.get("query") or "").strip()
        if query:
            params["keywords"] = query
        base = str(source.url or self.default_url)
        return base + "?" + urllib.parse.urlencode(params)

    def _items(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        news = data.get("news")
        return news if isinstance(news, list) else []


__all__ = ["NewsDataAdapter", "CurrentsAdapter"]
