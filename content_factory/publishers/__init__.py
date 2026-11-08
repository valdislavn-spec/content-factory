"""Публикация постов: Telegram Bot API, ВКонтакте и dry-run.

Реестр публикаторов:
    get_publisher("telegram", settings) -> TelegramPublisher
    get_publisher("vk", settings)       -> VKPublisher
    get_publisher("tumblr", settings)   -> TumblrPublisher   (опциональный)
    get_publisher("dryrun", settings)   -> DryRunPublisher

Ключевое правило безопасности: если settings.dry_run истинно, get_publisher
всегда возвращает DryRunPublisher, независимо от запрошенного имени —
реальная отправка в соцсети невозможна по ошибке конфигурации.
"""
from __future__ import annotations

from typing import Dict, List, Type

from ..config import Settings
from .base import (
    TELEGRAM_MESSAGE_LIMIT,
    VK_MESSAGE_LIMIT,
    Publisher,
    split_html_message,
)
from .dryrun import DryRunPublisher
from .facebook import FacebookPublisher
from .linkedin import LinkedInPublisher
from .instagram import InstagramPublisher
from .medium import MediumPublisher
from .pinterest import PinterestPublisher
from .reddit import RedditPublisher
from .threads import ThreadsPublisher
from .bluesky import BlueskyPublisher
from .discord import DiscordPublisher
from .fediverse import (
    AkkomaPublisher,
    FriendicaPublisher,
    GoToSocialPublisher,
    MisskeyPublisher,
    PleromaPublisher,
)
from .mastodon import MastodonPublisher
from .telegram import TelegramPublisher
from .tumblr import TumblrPublisher
from .vk import VKPublisher
from .x import XPublisher

__all__ = [
    "Publisher",
    "DryRunPublisher",
    "TelegramPublisher",
    "BlueskyPublisher",
    "MastodonPublisher",
    "DiscordPublisher",
    "PleromaPublisher",
    "AkkomaPublisher",
    "GoToSocialPublisher",
    "FriendicaPublisher",
    "MisskeyPublisher",
    "VKPublisher",
    "XPublisher",
    "FacebookPublisher",
    "LinkedInPublisher",
    "MediumPublisher",
    "RedditPublisher",
    "TumblrPublisher",
    "ThreadsPublisher",
    "InstagramPublisher",
    "PinterestPublisher",
    "TELEGRAM_MESSAGE_LIMIT",
    "VK_MESSAGE_LIMIT",
    "split_html_message",
    "get_publisher",
    "available_publishers",
    "publisher_classes",
]

_REGISTRY: Dict[str, Type[Publisher]] = {
    "telegram": TelegramPublisher,
    "vk": VKPublisher,
    "bluesky": BlueskyPublisher,
    "mastodon": MastodonPublisher,
    "discord": DiscordPublisher,
    "pleroma": PleromaPublisher,
    "akkoma": AkkomaPublisher,
    "gotosocial": GoToSocialPublisher,
    "friendica": FriendicaPublisher,
    "misskey": MisskeyPublisher,
    "x": XPublisher,
    "facebook": FacebookPublisher,
    "linkedin": LinkedInPublisher,
    "medium": MediumPublisher,
    "reddit": RedditPublisher,
    "tumblr": TumblrPublisher,
    "threads": ThreadsPublisher,
    "instagram": InstagramPublisher,
    "pinterest": PinterestPublisher,
    "dryrun": DryRunPublisher,
}

# Дружелюбные написания, которые встречаются в конфигурации/CLI.
_ALIASES = {
    "dry-run": "dryrun",
    "dry_run": "dryrun",
    "preview": "dryrun",
    "tg": "telegram",
    "bsky": "bluesky",
    "toot": "mastodon",
    "pl": "pleroma",
    "akk": "akkoma",
    "gts": "gotosocial",
    "friend": "friendica",
    "mk": "misskey",
    "firefish": "misskey",
    "vkontakte": "vk",
    "twitter": "x",
    "x.com": "x",
    "fb": "facebook",
    "li": "linkedin",
    "tumblr.com": "tumblr",
    "r": "reddit",
    "reddit.com": "reddit",
    "threads.net": "threads",
    "ig": "instagram",
    "instagram.com": "instagram",
    "pin": "pinterest",
    "pinterest.com": "pinterest",
}


def available_publishers() -> List[str]:
    """Имена поддерживаемых публикаторов (без учёта dry-run-подмены)."""
    return sorted(_REGISTRY)


def publisher_classes() -> Dict[str, Type[Publisher]]:
    """Копия реестра классов — для тестов/расширения без прямого доступа к _REGISTRY."""
    return dict(_REGISTRY)


def get_publisher(name: str, settings: Settings) -> Publisher:
    """Возвращает публикатор по имени с учётом режима dry_run.

    Исключение ValueError — только для неизвестного имени при выключенном
    dry-run; в dry-run неизвестное имя безопасно деградирует до DryRunPublisher.
    """
    key = str(name or "dryrun").strip().lower()
    key = _ALIASES.get(key, key)
    if settings.dry_run:
        return DryRunPublisher(settings)
    publisher_class = _REGISTRY.get(key)
    if publisher_class is None:
        raise ValueError(
            "Неизвестный публикатор {!r}. Доступны: {}".format(
                name, ", ".join(available_publishers())
            )
        )
    return publisher_class(settings)
