"""Сбор метрик каналов для аналитики.

Подписчики берутся через Telegram Bot API (getChatMemberCount) и только при
реальной публикации — в dry-run сеть не трогаем. Просмотры постов, если
установлен Telethon и заданы TG_API_ID/TG_API_HASH, собираются необязательным
ленивым импортом; без Telethon аналитика продолжает работать.

Все метрики сохраняются в SQLite через storage.save_metrics, поэтому отчёт
может строиться и по истории, и по последнему срезу.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Sequence

from ..config import Settings
from ..models import ChannelConfig, MetricSnapshot, utcnow
from ..storage import Storage
from ..utils import env, strip_html, tokenize

logger = logging.getLogger(__name__)

DEFAULT_DAYS = 7


def _telegram_token(settings: Settings) -> str:
    config = settings.publishers.get("telegram", {})
    if not isinstance(config, dict):
        config = {}
    env_name = str(config.get("bot_token_env") or "TELEGRAM_BOT_TOKEN")
    return env("{}".format(env_name), "") or ""


def fetch_subscribers(chat_id: str, token: str, timeout: float = 20.0) -> Optional[int]:
    """Число подписчиков канала через Bot API getChatMemberCount.

    Любая ошибка (нет прав у бота, сеть, некорректный ответ) — None:
    аналитика не должна ломаться из-за недоступного API.
    """
    if not chat_id or not token:
        return None
    query = urllib.parse.urlencode({"chat_id": chat_id})
    url = "https://api.telegram.org/bot{}/getChatMemberCount?{}".format(token, query)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ContentFactory/1.0", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read()
            data = json.loads(raw.decode("utf-8"))
            description = data.get("description") if isinstance(data, dict) else ""
        except Exception:  # noqa: BLE001 - тело ошибки необязательно
            description = ""
        logger.warning(
            "getChatMemberCount для %s: HTTP %s %s", chat_id, exc.code, description or ""
        )
        return None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("getChatMemberCount для %s недоступен: %s", chat_id, exc)
        return None

    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        logger.warning("getChatMemberCount для %s: некорректный JSON", chat_id)
        return None
    if not isinstance(data, dict) or not data.get("ok"):
        description = data.get("description") if isinstance(data, dict) else ""
        logger.warning("getChatMemberCount для %s: %s", chat_id, description or "ok=false")
        return None
    result = data.get("result")
    if isinstance(result, bool) or not isinstance(result, int):
        logger.warning("getChatMemberCount для %s: неожиданный result=%r", chat_id, result)
        return None
    return int(result)


def top_terms_from_posts(posts: Sequence[Dict[str, Any]], top_n: int = 10) -> List[Dict[str, Any]]:
    """Частотные термины из текстов постов канала (без внешних библиотек)."""
    noise = {
        "ru", "http", "https", "www", "com", "html", "php", "rss",
        "источники", "источник", "новости", "новость", "рассказал", "рассказала",
        "сообщил", "сообщила", "сообщает", "заявил", "заявила", "пишет", "пишут",
        "фото", "видео", "подробности", "читать", "смотрите",
    }
    source_names = set()
    for post in posts:
        for source in post.get("sources") or []:
            if isinstance(source, dict):
                name = str(source.get("source") or "").strip().lower()
                if name:
                    source_names.add(name)
                    source_names.update(tokenize(name))
    counts: Dict[str, int] = {}
    for post in posts:
        text = strip_html(str(post.get("text") or ""))
        for token in tokenize(text):
            if token in noise or token in source_names:
                continue
            if any(ch.isdigit() for ch in token):
                continue
            counts[token] = counts.get(token, 0) + 1
    ordered = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return [{"term": term, "count": count} for term, count in ordered[:top_n]]


def top_sources_from_posts(posts: Sequence[Dict[str, Any]], top_n: int = 10) -> List[Dict[str, Any]]:
    """Источники, которые чаще всего упоминаются в постах канала."""
    counts: Dict[str, int] = {}
    for post in posts:
        sources = post.get("sources") or []
        if not isinstance(sources, list):
            continue
        seen_in_post = set()
        for source in sources:
            if not isinstance(source, dict):
                continue
            name = str(source.get("source") or source.get("title") or "").strip()
            if not name or name in seen_in_post:
                continue
            seen_in_post.add(name)
            counts[name] = counts.get(name, 0) + 1
    ordered = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return [{"source_name": name, "count": count} for name, count in ordered[:top_n]]


def collect_post_views(
    channel: ChannelConfig, settings: Settings, limit: int = 20
) -> Dict[str, int]:
    """Просмотры последних постов через Telethon (опционально, ленивый импорт).

    Возвращает {message_id: views} или {} — если Telethon/ключи не настроены
    или канал недоступен. Никогда не бросает исключений.
    """
    if settings.dry_run:
        return {}
    api_id = env("TG_API_ID", "") or ""
    api_hash = env("TG_API_HASH", "") or ""
    session = env("TG_SESSION", "content_factory") or "content_factory"
    if not api_id or not api_hash:
        return {}
    username = str(channel.telegram_chat_id or "").strip().lstrip("@")
    if not username:
        return {}
    try:  # ленивый импорт: без Telethon система работает на Bot API
        from telethon.sync import TelegramClient
    except ImportError:
        logger.debug("Telethon не установлен — просмотры постов пропущены")
        return {}
    try:
        client = TelegramClient(session, int(api_id), api_hash)
        with client:
            entity = client.get_entity(username)
            views: Dict[str, int] = {}
            for message in client.iter_messages(entity, limit=limit):
                value = getattr(message, "views", None)
                if value is not None:
                    views[str(getattr(message, "id", ""))] = int(value)
            return views
    except Exception as exc:  # noqa: BLE001 - опциональная функция
        logger.debug("Не удалось собрать просмотры постов %s: %s", channel.id, exc)
        return {}


def collect_channel_metrics(
    channel: ChannelConfig,
    settings: Settings,
    storage: Storage,
    days: int = DEFAULT_DAYS,
) -> MetricSnapshot:
    """Собирает и сохраняет срез метрик одного канала."""
    snapshot = MetricSnapshot(channel_id=channel.id, collected_at=utcnow())
    posts: List[Dict[str, Any]] = []
    try:
        stats = storage.channel_stats(channel.id, days=days)
        posts = storage.get_posts(channel.id, days=days)
    except Exception as exc:  # noqa: BLE001 - пустая/битая база не должна ронять сбор
        logger.exception("Не удалось прочитать статистику канала %s: %s", channel.id, exc)
        stats = {}

    publishes = stats.get("publishes") or {}
    snapshot.posts_total = int(stats.get("posts", 0) or 0)
    snapshot.posts_published = int(publishes.get("ok", 0) or 0)
    snapshot.articles_total = int(stats.get("articles", 0) or 0)
    snapshot.avg_post_chars = float(stats.get("avg_post_chars", 0.0) or 0.0)
    formats = stats.get("formats") or {}
    snapshot.formats = {str(key): int(value) for key, value in formats.items()}
    clusters = {str(post.get("cluster_id")) for post in posts if post.get("cluster_id")}
    snapshot.clusters_total = len(clusters)
    snapshot.top_sources = top_sources_from_posts(posts)
    snapshot.top_terms = top_terms_from_posts(posts)

    # Подписчики: только в режиме реальной публикации и при наличии токена/чатa.
    chat_id = str(channel.telegram_chat_id or "").strip() or str(
        settings.channel_env_chat_id(channel.id) or ""
    ).strip()
    token = _telegram_token(settings)
    if settings.analytics.get("collect_subscribers", True) and not settings.dry_run:
        snapshot.subscribers = fetch_subscribers(chat_id, token, settings.request_timeout)
    else:
        logger.debug(
            "Канал %s: подписчики не собираются (dry_run=%s, collect_subscribers=%s)",
            channel.id,
            settings.dry_run,
            settings.analytics.get("collect_subscribers", True),
        )

    post_views = collect_post_views(channel, settings)
    snapshot.payload = {
        "dry_run": settings.dry_run,
        "days": days,
        "channel_title": channel.title,
        "publishes": publishes,
        "last_run": stats.get("last_run"),
        "sources_overall": storage.article_sources(days=days, limit=10),
        "post_views": post_views,
    }
    try:
        storage.save_metrics(snapshot)
    except Exception as exc:  # noqa: BLE001 - отчёт построится и по предыдущим данным
        logger.exception("Не удалось сохранить метрики канала %s: %s", channel.id, exc)
    return snapshot


def collect_all(
    channels: Sequence[ChannelConfig], settings: Settings, storage: Storage
) -> List[MetricSnapshot]:
    """Собирает метрики по всем включённым каналам."""
    if not settings.analytics.get("enabled", True):
        logger.info("Аналитика отключена в настройках — сбор метрик пропущен")
        return []
    snapshots: List[MetricSnapshot] = []
    for channel in channels:
        if not channel.enabled:
            logger.debug("Канал %s выключен — метрики не собираются", channel.id)
            continue
        try:
            snapshots.append(collect_channel_metrics(channel, settings, storage))
        except Exception as exc:  # noqa: BLE001 - один канал не ломает остальные
            logger.exception("Ошибка сбора метрик канала %s: %s", channel.id, exc)
    logger.info("Собраны метрики по %s каналам", len(snapshots))
    return snapshots
