"""Строка прогнозного рынка Polymarket в постах каналов (спорт и крипто).

Берёт активные рынки Polymarket (Gamma API, публично, без ключа), находит
рынок, совпадающий с темой поста (команды/бренды/термины из заголовка,
хештегов и ``topics`` канала), и вставляет перед хештегами короткую строку
с вероятностью и живой ссылкой:

    🎯 Polymarket: Ravens vs. Panthers — 58%

Best-effort: любая ошибка сети/API возвращает пустую строку и не мешает
публикации. Ответы кешируются на диск (``data/cache/polymarket.json``).

Настройка канала::

    polymarket:
      enabled: true
      max_markets: 1
      topics: [bitcoin, ethereum, nfl]   # добавляются к словам из поста
      min_volume_24h: 25000
      fallback: false   # true = топ-рынок по topics, если тема поста не совпала
      cache_ttl_sec: 600
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

LOGGER = logging.getLogger(__name__)

CACHE_TTL_SEC = 600
DEFAULT_PAGES = 3
DEFAULT_LIMIT = 100
DEFAULT_MIN_VOLUME = 25000
MAX_QUESTION_CHARS = 90
LABEL = "🎯 Polymarket:"

_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9'’-]{2,}")
_STOPWORDS = frozenset(
    """
    the this that with after before from into over their there these those what
    when where which while would could should about against among because been
    being both each even ever every just like more most much must only other
    same some such than then they very were will your have has had its but and
    not you are was one two new now says said amid also may can done first last
    next back top best big small high low years year today week month day time
    report reports update news story stories market markets price prices company
    companies country city government official officials state states world
    """.split()
)


def _cache_path() -> Path:
    base = os.environ.get("CONTENT_FACTORY_DATA_DIR") or "data"
    return Path(base) / "cache" / "polymarket.json"


def _read_cache(path: Path, ttl: int) -> List[Dict[str, Any]]:
    try:
        if not path.exists():
            return []
        if time.time() - path.stat().st_mtime > ttl:
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        markets = data.get("markets") if isinstance(data, dict) else data
        return [m for m in (markets or []) if isinstance(m, dict)]
    except (OSError, ValueError):
        return []


def _write_cache(path: Path, markets: List[Dict[str, Any]]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ts": time.time(), "markets": markets}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        LOGGER.debug("polymarket: не удалось записать кеш %s", path, exc_info=True)


def _fetch_markets(pages: int, limit: int) -> List[Dict[str, Any]]:
    from ..prediction.market import fetch_polymarket

    return fetch_polymarket(limit=limit, pages=pages)


def _markets(
    config: Dict[str, Any],
    fetcher: Optional[Callable[[], List[Dict[str, Any]]]] = None,
    cache_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    try:
        ttl = int(config.get("cache_ttl_sec") or CACHE_TTL_SEC)
    except (TypeError, ValueError):
        ttl = CACHE_TTL_SEC
    path = cache_path or _cache_path()
    cached = _read_cache(path, ttl)
    if cached:
        return cached
    if fetcher is None:
        def fetcher() -> List[Dict[str, Any]]:  # noqa: F811 - локальный дефолт
            return _fetch_markets(
                int(config.get("pages") or DEFAULT_PAGES),
                int(config.get("limit") or DEFAULT_LIMIT),
            )
    markets = fetcher() or []
    if markets:
        _write_cache(path, markets)
    return markets


def _keywords(text: str, config: Dict[str, Any]) -> Dict[str, float]:
    """Слова-кандидаты из поста: заголовок/тело/хештеги + topics канала."""
    text = str(text or "")
    lines = [line for line in text.splitlines() if line.strip()]
    title = lines[0] if lines else ""
    body = "\n".join(lines[1:])[:800]
    weights: Dict[str, float] = {}

    def add(word: str, weight: float) -> None:
        token = str(word or "").strip().lower().strip("#")
        if len(token) < 3 or token in _STOPWORDS:
            return
        if token.isdigit():
            return
        weights[token] = max(weights.get(token, 0.0), weight)

    # Матчим только имена/бренды (с заглавной буквы) и хештеги: строчные
    # служебные слова дают ложные совпадения («announce», «market»).
    for word in _WORD_RE.findall(title):
        if word[0].isupper():
            add(word, 2.0)
    for word in _WORD_RE.findall(body):
        if word[0].isupper():
            add(word, 1.5)
    for tag in re.findall(r"#([A-Za-zÀ-ÿ0-9_]+)", text):
        add(tag, 1.0)
    return weights


def _matches(question: str, keywords: Dict[str, float]) -> List[str]:
    haystack = str(question or "").lower()
    found: List[str] = []
    for token in keywords:
        if len(token) < 3:
            continue
        pattern = r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])"
        if re.search(pattern, haystack):
            found.append(token)
    return found


def _score(found: Iterable[str], keywords: Dict[str, float]) -> float:
    return sum(keywords.get(token, 1.0) * (1.0 + len(token) / 12.0) for token in found)


def _pick(markets: Iterable[Dict[str, Any]], keywords: Dict[str, float], config: Dict[str, Any]):
    try:
        min_volume = float(config.get("min_volume_24h") or DEFAULT_MIN_VOLUME)
    except (TypeError, ValueError):
        min_volume = DEFAULT_MIN_VOLUME
    ranked = []
    for market in markets:
        if not isinstance(market, dict):
            continue
        try:
            probability = market.get("probability")
            if probability is None:
                continue
            probability = float(probability)
            volume = float(market.get("volume_24h") or 0)
        except (TypeError, ValueError):
            continue
        if volume < min_volume:
            continue
        question = str(market.get("question") or "").strip()
        if not question:
            continue
        found = _matches(question, keywords)
        if not found:
            continue
        probability = float(market.get("probability") or 0.0)
        # При равной релевантности предпочитаем рынок, где мнение разделилось:
        # 0%/100% — уже решённый вопрос, он неинформативен для читателя.
        interesting = 1 if 0.03 <= probability <= 0.97 else 0
        ranked.append((_score(found, keywords), interesting, volume, market))
    if ranked:
        ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return ranked[0][3]
    if config.get("fallback"):
        topic_keywords = {
            str(topic).strip().lower(): 1.0
            for topic in (config.get("topics") or [])
            if len(str(topic).strip()) >= 3
        }
        pool = []
        for market in markets:
            if not isinstance(market, dict) or market.get("probability") is None:
                continue
            try:
                volume = float(market.get("volume_24h") or 0)
            except (TypeError, ValueError):
                continue
            if volume < min_volume:
                continue
            question = str(market.get("question") or "").strip()
            if not question:
                continue
            if topic_keywords and not _matches(question, topic_keywords):
                continue
            pool.append((volume, market))
        if pool:
            # Крайние вероятности (0%/100%) неинформативны — если есть выбор,
            # показываем рынок, где мнение действительно разделилось.
            def _rank(item):
                volume, market = item
                probability = float(market.get("probability") or 0.0)
                interesting = 1 if 0.03 <= probability <= 0.97 else 0
                return (interesting, volume)

            pool.sort(key=_rank, reverse=True)
            return pool[0][1]
    return None


def _shorten(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:—-")
    return (cut or text[:limit]).rstrip() + "…"


def _format_line(market: Dict[str, Any], language: str = "en") -> str:
    question = _shorten(market.get("question", ""), MAX_QUESTION_CHARS)
    if not question:
        return ""
    url = str(market.get("url") or "").strip()
    if not url.startswith("https://polymarket.com/"):
        return ""
    try:
        probability = max(0.0, min(1.0, float(market.get("probability"))))
    except (TypeError, ValueError):
        return ""
    if probability < 0.01:
        percent = "<1%"
    elif probability > 0.99:
        percent = ">99%"
    else:
        percent = f"{int(round(probability * 100))}%"
    safe_url = html.escape(url, quote=True)
    return f'{LABEL} <a href="{safe_url}">{html.escape(question)}</a> — {percent}'


def build_polymarket_line(
    config: Dict[str, Any],
    text: str,
    language: str = "en",
    channel_id: str = "",
    fetcher: Optional[Callable[[], List[Dict[str, Any]]]] = None,
    cache_path: Optional[Path] = None,
) -> str:
    """Одна строка Polymarket по теме поста или ``""``."""
    if not isinstance(config, dict) or not config.get("enabled"):
        return ""
    try:
        markets = _markets(config, fetcher=fetcher, cache_path=cache_path)
        if not markets:
            return ""
        keywords = _keywords(text, config)
        if not keywords:
            return ""
        market = _pick(markets, keywords, config)
        if not market:
            return ""
        return _format_line(market, language)
    except Exception:  # noqa: BLE001 - строка рынка не должна мешать публикации
        LOGGER.warning("polymarket: не удалось собрать строку для %s", channel_id, exc_info=True)
        return ""


def insert_line(text: str, line: str) -> str:
    """Вставляет строку перед хвостовым блоком хештегов."""
    if not line:
        return text
    from .marketline import insert_before_hashtags

    return insert_before_hashtags(text, line)
