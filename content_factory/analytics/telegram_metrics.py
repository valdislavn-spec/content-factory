"""Telegram-метрики: подписчики, просмотры, реакции, репосты, ER.

Что умеет:

* подписчики — через Bot API ``getChatMemberCount`` (бесплатно, нужен бот-админ);
* просмотры/реакции/репосты постов — через Telethon (MTProto, опционально);
* сохраняет посты и срезы в SQLite;
* считает ER = (реакции + репосты) / просмотры × 100.

Без Telethon/ключей модуль не падает: собирает только подписчиков (если есть
бот и chat_id), а посты пропускает. Это важно для работы без сайта и без
GA4/GSC — единственные доступные метрики здесь телеграмные.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..config import Settings
from ..models import ChannelConfig, utcnow
from ..storage import Storage
from ..utils import env, format_iso, strip_html
from .collector import _telegram_token, fetch_subscribers

logger = logging.getLogger(__name__)

DEFAULT_POSTS_LIMIT = 30
MAX_POSTS_LIMIT = 200


def _chat_target(channel: ChannelConfig) -> Optional[Any]:
    """@username -> username; -100... -> int; пусто -> None."""
    raw = str(channel.telegram_chat_id or "").strip()
    if not raw:
        return None
    if raw.startswith("@"):
        return raw[1:]
    try:
        return int(raw)
    except ValueError:
        return raw


def _username(channel: ChannelConfig) -> str:
    raw = str(channel.telegram_chat_id or "").strip()
    return raw.lstrip("@") if raw.startswith("@") else ""


def _reaction_count(message: Any) -> int:
    """Сумма всех реакций поста (Telethon MessageReactions)."""
    reactions = getattr(message, "reactions", None)
    if reactions is None:
        return 0
    total = 0
    results = getattr(reactions, "results", None) or []
    for item in results:
        try:
            total += int(getattr(item, "count", 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def _reply_count(message: Any) -> int:
    replies = getattr(message, "replies", None)
    if replies is None:
        return 0
    try:
        return int(getattr(replies, "replies", 0) or 0)
    except (TypeError, ValueError):
        return 0


def message_to_post(message: Any, channel: ChannelConfig, username: str = "") -> Dict[str, Any]:
    """Преобразовать сообщение Telethon в словарь метрик поста."""
    try:
        message_id = int(getattr(message, "id", 0) or 0)
    except (TypeError, ValueError):
        return {}
    if message_id <= 0:
        return {}
    views = getattr(message, "views", None)
    try:
        views_value = int(views) if views is not None and not isinstance(views, bool) else None
    except (TypeError, ValueError):
        views_value = None
    posted = getattr(message, "date", None)
    text = strip_html(str(getattr(message, "message", "") or ""))[:200]
    link = "https://t.me/{}/{}".format(username, message_id) if username else ""
    return {
        "message_id": message_id,
        "posted_at": format_iso(posted) if isinstance(posted, datetime) else "",
        "views": views_value,
        "forwards": int(getattr(message, "forwards", 0) or 0),
        "reactions": _reaction_count(message),
        "replies": _reply_count(message),
        "text_preview": text,
        "url": link,
    }


def fetch_channel_posts(
    channel: ChannelConfig, settings: Settings, limit: int = DEFAULT_POSTS_LIMIT
) -> List[Dict[str, Any]]:
    """Последние посты канала с метриками через Telethon.

    Возвращает [] без Telethon, без TG_API_ID/TG_API_HASH или при любой
    ошибке — аналитика не должна ломать завод.
    """
    limit = max(1, min(int(limit or DEFAULT_POSTS_LIMIT), MAX_POSTS_LIMIT))
    if not settings.analytics.get("collect_post_metrics", True):
        return []
    api_id = env("TG_API_ID", "") or ""
    api_hash = env("TG_API_HASH", "") or ""
    session = env("TG_SESSION", "content_factory") or "content_factory"
    target = _chat_target(channel)
    if not api_id or not api_hash or target is None:
        logger.debug("Telegram-метрики постов: нет TG_API_ID/TG_API_HASH или chat_id")
        return []
    # В CI/неинтерактивном режиме без готовой сессии Telethon попытался бы
    # спросить телефон/код и завис. Пропускаем, пока сессию не создали локально.
    if not Path(session).exists() and not sys.stdin.isatty():
        logger.info(
            "Telethon-сессия %s не найдена, а запуск неинтерактивный — "
            "просмотры/реакции пропущены",
            session,
        )
        return []
    try:  # ленивый импорт: без Telethon система работает
        from telethon.sync import TelegramClient
    except ImportError:
        logger.info("Telethon не установлен — просмотры/реакции постов пропущены")
        return []

    posts: List[Dict[str, Any]] = []
    try:
        client = TelegramClient(session, int(api_id), api_hash)
        with client:
            entity = client.get_entity(target)
            username = str(getattr(entity, "username", "") or _username(channel))
            for message in client.iter_messages(entity, limit=limit):
                item = message_to_post(message, channel, username=username)
                if item:
                    posts.append(item)
    except Exception as exc:  # noqa: BLE001 - опциональная функция
        logger.warning("Не удалось собрать посты канала %s: %s", channel.id, exc)
        return []
    return posts


def summarize_posts(posts: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Сводка по постам: просмотры, реакции, репосты, ER и топ-посты."""
    views = [
        int(post.get("views"))
        for post in posts
        if isinstance(post.get("views"), int) and not isinstance(post.get("views"), bool)
    ]
    total_views = sum(views)
    total_reactions = sum(int(post.get("reactions") or 0) for post in posts)
    total_forwards = sum(int(post.get("forwards") or 0) for post in posts)
    total_replies = sum(int(post.get("replies") or 0) for post in posts)
    avg_views = round(total_views / len(views), 1) if views else 0.0
    er = (
        round((total_reactions + total_forwards) / total_views * 100.0, 2)
        if total_views
        else 0.0
    )
    top_posts = sorted(
        posts,
        key=lambda post: int(post.get("views") or 0),
        reverse=True,
    )[:5]
    return {
        "posts_analyzed": len(posts),
        "posts_with_views": len(views),
        "total_views": total_views,
        "avg_views": avg_views,
        "total_reactions": total_reactions,
        "total_forwards": total_forwards,
        "total_replies": total_replies,
        "er": er,
        "top_posts": top_posts,
    }


def _previous_subscribers(storage: Storage, channel_id: str) -> Optional[int]:
    try:
        history = storage.telegram_channel_history(channel_id, days=90)
    except Exception:  # noqa: BLE001
        return None
    for row in reversed(history):
        value = row.get("subscribers")
        if isinstance(value, int) and not isinstance(value, bool):
            return int(value)
    return None


def collect_channel_telegram_metrics(
    channel: ChannelConfig,
    settings: Settings,
    storage: Storage,
    limit: int = DEFAULT_POSTS_LIMIT,
) -> Dict[str, Any]:
    """Собрать и сохранить Telegram-метрики одного канала."""
    chat_id = str(channel.telegram_chat_id or "").strip() or str(
        settings.channel_env_chat_id(channel.id) or ""
    ).strip()
    token = _telegram_token(settings)
    subscribers: Optional[int] = None
    if settings.analytics.get("collect_subscribers", True) and chat_id and token:
        subscribers = fetch_subscribers(chat_id, token, settings.request_timeout)

    posts = fetch_channel_posts(channel, settings, limit=limit)
    summary = summarize_posts(posts)
    previous = _previous_subscribers(storage, channel.id)
    growth: Optional[int] = None
    if subscribers is not None and previous is not None:
        growth = subscribers - previous

    summary.update(
        {
            "channel_id": channel.id,
            "channel_title": channel.title,
            "subscribers": subscribers,
            "growth_subscribers": growth,
            "payload": {
                "dry_run": settings.dry_run,
                "chat_id": chat_id,
                "limit": max(1, min(int(limit or DEFAULT_POSTS_LIMIT), MAX_POSTS_LIMIT)),
                "telethon_used": bool(posts),
            },
        }
    )

    try:
        if posts:
            storage.save_telegram_posts(channel.id, posts)
        storage.save_telegram_channel_metrics(channel.id, summary, collected_at=utcnow())
    except Exception as exc:  # noqa: BLE001 - отчёт построится по прошлым данным
        logger.exception("Не удалось сохранить Telegram-метрики канала %s: %s", channel.id, exc)
    return summary


def collect_all_telegram_metrics(
    channels: Sequence[ChannelConfig],
    settings: Settings,
    storage: Storage,
    limit: int = DEFAULT_POSTS_LIMIT,
) -> List[Dict[str, Any]]:
    """Собрать Telegram-метрики по всем включённым каналам."""
    if not settings.analytics.get("enabled", True):
        logger.info("Аналитика отключена — Telegram-метрики не собираются")
        return []
    summaries: List[Dict[str, Any]] = []
    for channel in channels:
        if not channel.enabled:
            continue
        try:
            summaries.append(
                collect_channel_telegram_metrics(channel, settings, storage, limit=limit)
            )
        except Exception as exc:  # noqa: BLE001 - один канал не ломает остальные
            logger.exception("Ошибка Telegram-метрик канала %s: %s", channel.id, exc)
    logger.info("Собраны Telegram-метрики по %s каналам", len(summaries))
    return summaries
