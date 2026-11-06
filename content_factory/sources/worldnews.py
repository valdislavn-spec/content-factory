"""Адаптер World News API (https://worldnewsapi.com).

Бесплатный тариф: 50 points/день (1 запрос + 0.01 за каждый результат).
Поиск новостей по тексту с фильтрами, ответ содержит полный текст, картинку,
дату публикации, категорию, язык и тональность статьи.

Ключ берётся из переменной окружения ``WORLD_NEWS_API_KEY`` (можно переопределить
через ``options.api_key_env``); в конфиге канала ключ не хранится.

Пример источника в config/channels.yaml:

    - id: worldnews-tech
      type: worldnews
      name: World News API
      weight: 1.1
      options:
        query: artificial intelligence technology
        language: en
        max_items: 10
        sort: publish-time
        trust: true
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ..config import Settings
from ..models import Article, SourceConfig
from ..utils import FetchError, env, normalize_url, parse_datetime, strip_html
from .base import SourceAdapter, build_article, max_text_chars, request_params, source_budget

logger = logging.getLogger(__name__)

BASE_URL = "https://api.worldnewsapi.com"
SEARCH_ENDPOINT = BASE_URL + "/search-news"
DEFAULT_KEY_ENV = "WORLD_NEWS_API_KEY"
DEFAULT_MAX_ITEMS = 10
DEFAULT_SORT = "publish-time"
# Бесплатный тариф: 50 points/день; после лимита API отвечает 402.
QUOTA_HINT = "Бесплатный лимит World News API (50 points/сутки) исчерпан"


def _published_at(value: Any) -> Optional[datetime]:
    """Разбирает дату World News API (``YYYY-MM-DD HH:MM:SS``, UTC)."""
    raw = str(value or "").strip()
    if not raw:
        return None
    parsed = parse_datetime(raw)
    if parsed is not None:
        return parsed
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


class WorldNewsAdapter(SourceAdapter):
    """Новости через World News API (search-news)."""

    type = "worldnews"

    # -- конфигурация ---------------------------------------------------
    @staticmethod
    def _options(source: SourceConfig) -> Dict[str, Any]:
        return dict(source.options or {})

    def _api_key(self, source: SourceConfig) -> str:
        opts = self._options(source)
        name = str(opts.get("api_key_env") or DEFAULT_KEY_ENV)
        return env(name, "") or ""

    def build_url(self, source: SourceConfig, settings: Settings) -> str:
        opts = self._options(source)
        query = str(opts.get("query") or "").strip()
        if not query:
            raise FetchError(
                "worldnews: задайте options.query (например, 'artificial intelligence')"
            )
        try:
            number = max(1, min(100, int(opts.get("max_items") or DEFAULT_MAX_ITEMS)))
        except (TypeError, ValueError):
            number = DEFAULT_MAX_ITEMS
        params: Dict[str, Any] = {
            "text": query,
            "language": str(opts.get("language") or "en"),
            "number": number,
            "sort": str(opts.get("sort") or DEFAULT_SORT),
        }
        categories = str(opts.get("categories") or "").strip()
        if categories:
            params["categories"] = categories
        countries = str(opts.get("source_countries") or "").strip()
        if countries:
            params["source-countries"] = countries
        # Свежие новости: ограничиваем окно lookback из настроек завода.
        try:
            lookback = float(settings.pipeline.get("lookback_hours", 30) or 30)
        except (TypeError, ValueError, AttributeError):
            lookback = 30.0
        earliest = datetime.now(timezone.utc) - timedelta(hours=max(1.0, lookback))
        params["earliest-publish-date"] = earliest.strftime("%Y-%m-%d")
        return SEARCH_ENDPOINT + "?" + urllib.parse.urlencode(params)

    # -- HTTP ------------------------------------------------------------
    def _request(self, url: str, source: SourceConfig, settings: Settings) -> Dict[str, Any]:
        api_key = self._api_key(source)
        if not api_key:
            raise FetchError(
                "worldnews: не задан WORLD_NEWS_API_KEY (см. scripts/set_worldnews_key.py)"
            )
        params = request_params(settings)
        request = urllib.request.Request(
            url,
            headers={
                "x-api-key": api_key,
                "Accept": "application/json",
                "User-Agent": params["user_agent"],
            },
        )
        try:
            with urllib.request.urlopen(
                request, timeout=params["timeout"]
            ) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise FetchError("worldnews: неверный WORLD_NEWS_API_KEY (HTTP 401)") from exc
            if exc.code == 402:
                raise FetchError(QUOTA_HINT + " (HTTP 402)") from exc
            if exc.code == 429:
                raise FetchError("worldnews: слишком много запросов (HTTP 429)") from exc
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:200]
            except Exception:  # pragma: no cover - тело ошибки может быть недоступно
                detail = ""
            raise FetchError(
                "worldnews: HTTP {} {}".format(exc.code, detail.strip())
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise FetchError("worldnews: сеть недоступна: {}".format(exc)) from exc
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise FetchError("worldnews: ответ не JSON") from exc
        if not isinstance(data, dict):
            raise FetchError("worldnews: неожиданный формат ответа")
        return data

    # -- маппинг ---------------------------------------------------------
    def _article(
        self, item: Dict[str, Any], source: SourceConfig, settings: Settings
    ) -> Optional[Article]:
        if not isinstance(item, dict):
            return None
        url = str(item.get("url") or "").strip()
        if not url:
            return None
        text = strip_html(str(item.get("text") or item.get("summary") or ""))
        summary = strip_html(str(item.get("summary") or ""))
        limit = max_text_chars(settings)
        if len(text) > limit:
            text = text[:limit].rsplit(" ", 1)[0]
        tags: List[str] = []
        category = str(item.get("category") or "").strip()
        if category:
            tags.append(category)
        meta = {
            "image": str(item.get("image") or "").strip(),
            "video": str(item.get("video") or "").strip(),
            "category": category,
            "source_country": str(item.get("source_country") or "").strip(),
            "sentiment": item.get("sentiment"),
            "authors": item.get("authors") or [],
            "worldnews_id": item.get("id"),
        }
        meta = {key: value for key, value in meta.items() if value not in ("", None, [])}
        article = build_article(
            source,
            settings,
            url=url,
            title=str(item.get("title") or ""),
            published_at=_published_at(item.get("publish_date")),
            text=text,
            summary=summary,
            tags=tags,
            meta=meta,
        )
        return article

    def fetch(self, source: SourceConfig, settings: Settings) -> List[Article]:
        if not self._api_key(source):
            raise FetchError(
                "worldnews: не задан WORLD_NEWS_API_KEY (см. scripts/set_worldnews_key.py)"
            )
        budget = source_budget(source, settings)
        if budget is not None and not budget.try_consume(1):
            logger.info("WorldNews[%s]: %s — источник пропущен", source.id, budget.describe())
            return []
        url = self.build_url(source, settings)
        data = self._request(url, source, settings)
        items = data.get("news")
        if not isinstance(items, list):
            return []
        articles: List[Article] = []
        seen: set = set()
        for item in items:
            article = self._article(item, source, settings)
            if article is None:
                continue
            if article.id in seen:
                continue
            seen.add(article.id)
            articles.append(article)
        logger.info("WorldNews[%s]: новостей %d", source.id, len(articles))
        return articles


__all__ = ["WorldNewsAdapter", "SEARCH_ENDPOINT", "QUOTA_HINT"]
