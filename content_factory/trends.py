"""Тренды для постов: внешние фиды + частота по своим статьям.

Провайдеры (все бесплатные, без API-ключей и тяжёлых зависимостей):
- Google Trends RSS — топ поисковых запросов по региону (US / MX);
- CoinGecko Trending — монеты, которые сейчас ищут (крипто-каналы);
- GitHub Trending — растущие репозитории (AI/tech-каналы);
- Hacker News top stories — повестка tech-сообщества;
- частота терминов в свежих статьях канала — всегда доступный fallback.

Результат кэшируется на полчаса в ``data/trends_cache.json``, ошибки сети
не ломают публикацию: тренды просто остаются пустыми.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .utils import env, tokenize, normalize_space

logger = logging.getLogger(__name__)

GOOGLE_TRENDS_URL = "https://trends.google.com/trending/rss?geo={geo}"
COINGECKO_TRENDING_URL = "https://api.coingecko.com/api/v3/search/trending"
HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"
GITHUB_TRENDING_URL = "https://github.com/trending?since=daily"

CACHE_TTL_SECONDS = 1800
CACHE_VERSION = "v2"  # менять при изменении формата/парсеров трендов
REQUEST_TIMEOUT = 12
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")

# какие провайдеры включать по тематике канала
_CRYPTO_WORDS = {"bitcoin", "ethereum", "crypto", "cripto", "blockchain", "defi", "token"}
_SPORT_WORDS = {"nfl", "nba", "mlb", "nhl", "sport", "futbol", "fútbol", "deporte", "soccer", "goal", "gol"}
_AI_WORDS = {"ai", "ia", "llm", "openai", "anthropic", "machine", "artificial", "modelo", "tecnología"}


# ---------------------------------------------------------------------------
# кэш
# ---------------------------------------------------------------------------
def _cache_path(settings: Any) -> Path:
    data_dir = Path(getattr(settings, "data_dir", "data"))
    return data_dir / "trends_cache.json"


def _cache_get(settings: Any, key: str) -> Optional[List[str]]:
    key = f"{CACHE_VERSION}:{key}"
    try:
        path = _cache_path(settings)
        raw = json.loads(path.read_text(encoding="utf-8"))
        entry = raw.get(key) or {}
        if time.time() - float(entry.get("ts", 0)) <= CACHE_TTL_SECONDS:
            values = entry.get("values")
            if isinstance(values, list):
                return [str(value) for value in values]
    except Exception:  # noqa: BLE001 - кэш не критичен
        return None
    return None


def _cache_set(settings: Any, key: str, values: Sequence[str]) -> None:
    key = f"{CACHE_VERSION}:{key}"
    try:
        path = _cache_path(settings)
        data: Dict[str, Any] = {}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                data = {}
        data[key] = {"ts": time.time(), "values": list(values)}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _fetch(url: str, *, headers: Optional[Dict[str, str]] = None) -> Optional[bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return response.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
        logger.debug("Тренды: %s недоступен (%s)", url, exc)
        return None


# ---------------------------------------------------------------------------
# провайдеры
# ---------------------------------------------------------------------------
def parse_google_trends_rss(raw: bytes) -> List[str]:
    """Заголовки трендов из Google Trends RSS (без сети — для тестов).

    Берём только ``<item><title>`` (сами поисковые тренды), без вложенных
    новостных заголовков — они слишком длинные и шумные.
    """
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    values: List[str] = []
    for item in root.iter("item"):
        title = normalize_space(item.findtext("title") or "")
        if title:
            values.append(title)
        if len(values) >= 20:
            break
    return _dedupe(values)


def google_trends(geo: str = "US", settings: Any = None) -> List[str]:
    key = f"google:{geo}"
    cached = _cache_get(settings, key) if settings is not None else None
    if cached is not None:
        return cached
    raw = _fetch(GOOGLE_TRENDS_URL.format(geo=geo))
    values = parse_google_trends_rss(raw) if raw else []
    if settings is not None and values:
        _cache_set(settings, key, values)
    return values


def coingecko_trending(settings: Any = None) -> List[str]:
    cached = _cache_get(settings, "coingecko") if settings is not None else None
    if cached is not None:
        return cached
    raw = _fetch(COINGECKO_TRENDING_URL)
    values: List[str] = []
    if raw:
        try:
            data = json.loads(raw.decode("utf-8", errors="replace"))
            for item in (data.get("coins") or [])[:10]:
                coin = item.get("item") or {}
                name = normalize_space(str(coin.get("name") or ""))
                symbol = normalize_space(str(coin.get("symbol") or ""))
                if name:
                    values.append(name)
                if symbol and symbol.upper() not in {v.upper() for v in values}:
                    values.append(symbol.upper())
        except (ValueError, AttributeError):
            values = []
    if settings is not None and values:
        _cache_set(settings, "coingecko", values)
    return values


def github_trending(settings: Any = None) -> List[str]:
    cached = _cache_get(settings, "github") if settings is not None else None
    if cached is not None:
        return cached
    raw = _fetch(GITHUB_TRENDING_URL)
    values: List[str] = []
    if raw:
        html = raw.decode("utf-8", errors="replace")
        skip_owners = {
            "sponsors", "trending", "topics", "collections", "marketplace", "login",
            "signup", "settings", "features", "enterprise", "team", "pricing", "explore",
            "about", "site", "security", "contact", "orgs", "users", "new", "codespaces",
        }
        skip_names = {"stargazers", "forks", "issues", "pulls", "network", "graphs", "blob", "tree"}
        # любая ссылка вида /owner/repo (хвосты /stargazers и т.п. отбрасываем)
        for match in re.finditer(r'href="([^"]+)"', html):
            path = str(match.group(1)).split("?")[0].strip()
            if not path.startswith("/"):
                continue
            segments = [segment for segment in path.strip("/").split("/") if segment]
            if len(segments) < 2:
                continue
            owner, name = segments[0], segments[1]
            if owner.lower() in skip_owners or name.lower() in skip_names:
                continue
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
                continue
            repo = f"{owner}/{name}"
            if repo not in values:
                values.append(repo)
            if len(values) >= 12:
                break
    if settings is not None and values:
        _cache_set(settings, "github", values)
    return values[:10]


def hackernews_trends(settings: Any = None, limit: int = 8) -> List[str]:
    cached = _cache_get(settings, "hn") if settings is not None else None
    if cached is not None:
        return cached
    raw = _fetch(HN_TOP_URL)
    ids: List[int] = []
    if raw:
        try:
            ids = [int(value) for value in json.loads(raw.decode("utf-8", errors="replace"))[:limit]]
        except (ValueError, TypeError):
            ids = []
    values: List[str] = []
    for item_id in ids:
        item_raw = _fetch(HN_ITEM_URL.format(id=item_id))
        if not item_raw:
            continue
        try:
            item = json.loads(item_raw.decode("utf-8", errors="replace"))
        except ValueError:
            continue
        title = normalize_space(str(item.get("title") or ""))
        if title:
            values.append(title)
    if settings is not None and values:
        _cache_set(settings, "hn", values)
    return values[:limit]


# ---------------------------------------------------------------------------
# локальная частота + сборка
# ---------------------------------------------------------------------------
def _dedupe(values: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        normalized = normalize_space(str(value))
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _channel_words(channel: Any) -> set:
    words = set()
    for topic in (getattr(channel, "topics", None) or []):
        for token in tokenize(str(topic), language=str(getattr(channel, "language", "ru"))):
            if len(str(token)) >= 3:
                words.add(str(token).lower())
    return words


def _provider_kinds(channel: Any) -> List[str]:
    topics = {str(topic).lower() for topic in (getattr(channel, "topics", None) or [])}
    words = _channel_words(channel) | topics
    kinds: List[str] = []
    if words & _CRYPTO_WORDS:
        kinds.append("crypto")
    if words & _AI_WORDS:
        kinds.extend(["github", "hn"])
    if words & _SPORT_WORDS:
        kinds.append("sport")
    return kinds or ["google"]


def _local_frequency(clusters: Sequence[Any], channel: Any, limit: int = 5) -> List[str]:
    counts: Dict[str, int] = {}
    for cluster in clusters or []:
        texts: List[str] = [str(getattr(cluster, "title", "") or "")]
        for article in getattr(cluster, "articles", None) or []:
            texts.append(str(getattr(article, "title", "") or ""))
        for text in texts:
            if not text:
                continue
            for token in tokenize(text.lower(), language=str(getattr(channel, "language", "ru"))):
                token = str(token).strip()
                if len(token) < 4 or token.isdigit():
                    continue
                counts[token] = counts.get(token, 0) + 1
    ranked = [term for term, count in sorted(counts.items(), key=lambda item: -item[1]) if count >= 2]
    return ranked[:limit]


def _relevance(value: str, channel: Any) -> int:
    """Сколько ключевых слов канала встречается в тренде (0 — нерелевантен)."""
    lowered = str(value or "").lower()
    words = _channel_words(channel)
    score = 0
    for topic in (getattr(channel, "topics", None) or []):
        topic = str(topic).lower().strip()
        if not topic:
            continue
        if len(topic) <= 3 and topic.isascii():
            if re.search(r"(?<![a-z0-9])" + re.escape(topic) + r"(?![a-z0-9])", lowered):
                score += 1
        elif topic in lowered or lowered in topic:
            score += 1
    for token in tokenize(lowered, language=str(getattr(channel, "language", "ru"))):
        if str(token).lower() in words:
            score += 1
    return score


def _rank(values: Sequence[str], channel: Any, limit: int) -> List[str]:
    return [
        value
        for value in sorted(_dedupe(values), key=lambda value: (_relevance(value, channel), -len(value)), reverse=True)
    ][:limit]


def collect_trends(
    channel: Any,
    settings: Any = None,
    clusters: Optional[Sequence[Any]] = None,
    limit: int = 3,
) -> List[str]:
    """Собирает актуальные тренды под тематику канала.

    Порядок: внешние провайдеры по типу канала + Google Trends по региону +
    всегда доступная локальная частота. Никогда не бросает исключение.
    """
    try:
        geo = "MX" if str(getattr(channel, "language", "en")) == "es" else "US"
        kinds = _provider_kinds(channel)
        ranked: List[str] = []

        def add(values: Sequence[str], *, relevant_only: bool) -> None:
            candidates = _rank(values, channel, limit * 3)
            if relevant_only:
                candidates = [value for value in candidates if _relevance(value, channel) > 0]
            for value in candidates:
                if value not in ranked:
                    ranked.append(value)

        if "crypto" in kinds:
            # монеты из трендов рынка — сигнал сам по себе
            add(coingecko_trending(settings), relevant_only=False)
        if "github" in kinds:
            add(github_trending(settings), relevant_only=True)
        if "hn" in kinds:
            add(hackernews_trends(settings), relevant_only=True)
        add(google_trends(geo, settings), relevant_only=True)
        add(_local_frequency(list(clusters or []), channel), relevant_only=True)
        return ranked[:limit]
    except Exception as exc:  # noqa: BLE001 - тренды не должны ломать пайплайн
        logger.debug("Тренды недоступны: %s", exc)
        return []
