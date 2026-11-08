"""Реестр адаптеров источников.

Единая точка входа для конвейера: по строке ``type`` из конфигурации
возвращается нужный адаптер. Новые типы источников достаточно добавить в
``_ADAPTERS`` — остальной код менять не нужно.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from ..config import Settings
from ..models import Article, SourceConfig
from ..utils import FetchError
from .base import SourceAdapter
from .docs import DocsAdapter
from .bingx import BingXAnnouncementsAdapter
from .espn import ESPNAdapter
from .rss import RSSAdapter
from .telegram import TelegramAdapter
from .web import WebAdapter
from .worldnews import WorldNewsAdapter
from .jsonnews import CurrentsAdapter, NewsDataAdapter

# Экземпляры адаптеров не хранят состояния, поэтому их можно переиспользовать.
_ADAPTERS: Dict[str, SourceAdapter] = {
    RSSAdapter.type: RSSAdapter(),
    WebAdapter.type: WebAdapter(),
    TelegramAdapter.type: TelegramAdapter(),
    WorldNewsAdapter.type: WorldNewsAdapter(),
    NewsDataAdapter.type: NewsDataAdapter(),
    CurrentsAdapter.type: CurrentsAdapter(),
    ESPNAdapter.type: ESPNAdapter(),
    DocsAdapter.type: DocsAdapter(),
    BingXAnnouncementsAdapter.type: BingXAnnouncementsAdapter(),
}


def get_adapter(source_type: str) -> SourceAdapter:
    """Возвращает адаптер по типу источника (rss/web/telegram/worldnews/espn/docs)."""
    key = str(source_type or "").strip().lower()
    adapter = _ADAPTERS.get(key)
    if adapter is None:
        raise FetchError(
            f"Неизвестный тип источника {source_type!r}. "
            f"Доступны: {', '.join(available_types())}"
        )
    return adapter


def available_types() -> List[str]:
    """Список поддерживаемых типов источников."""
    return sorted(_ADAPTERS)


def check_source(source: SourceConfig, settings: Settings) -> Tuple[bool, str]:
    """Проверяет доступность источника; никогда не бросает исключений."""
    try:
        adapter = get_adapter(source.type)
    except FetchError as exc:
        return False, str(exc)
    return adapter.check(source, settings)


def fetch_source(source: SourceConfig, settings: Settings) -> List[Article]:
    """Загружает статьи источника, не глотая ошибки (для конвейера)."""
    return get_adapter(source.type).fetch(source, settings)


__all__ = ["get_adapter", "available_types", "check_source", "fetch_source", "SourceAdapter"]
