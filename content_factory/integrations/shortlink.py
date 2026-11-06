"""Сокращение ссылок на источники через бесплатный TinyURL (без API-ключа).

Нужно для профессиональных постов: длинные URL статей портят вид и занимают
место в Telegram. Сокращаем только http(s)-ссылки; при любой сетевой ошибке
возвращаем исходный URL — публикация не должна падать из-за сокращателя.
"""
from __future__ import annotations

import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict

logger = logging.getLogger(__name__)

TINYURL_ENDPOINT = "https://tinyurl.com/api-create.php"
_CACHE: Dict[str, str] = {}


def shorten_url(url: str, timeout: float = 10.0) -> str:
    """Возвращает короткую ссылку (TinyURL) или исходный URL при ошибке."""
    original = str(url or "").strip()
    if not original.startswith(("http://", "https://")):
        return original
    if original in _CACHE:
        return _CACHE[original]
    endpoint = "{}?url={}".format(TINYURL_ENDPOINT, urllib.parse.quote(original, safe=""))
    try:
        request = urllib.request.Request(
            endpoint, headers={"User-Agent": "ContentFactory/1.0"}
        )
        with urllib.request.urlopen(request, timeout=max(3.0, float(timeout))) as response:
            short = response.read().decode("utf-8", errors="replace").strip()
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        logger.debug("TinyURL недоступен: %s", exc)
        _CACHE[original] = original
        return original
    if short.startswith(("http://", "https://")) and len(short) < len(original):
        _CACHE[original] = short
        return short
    _CACHE[original] = original
    return original


def reset_cache() -> None:
    """Очистить кэш (для тестов)."""
    _CACHE.clear()
