"""Публикация в Discord через webhook — бесплатно, без OAuth, только свои серверы.

Webhook URL берётся из .env:
    DISCORD_WEBHOOK_URL
    DISCORD_WEBHOOK_URL_<CHANNEL_ID>

Для каждого тематического канала лучше завести отдельный webhook: один
Discord-канал не должен смешивать спорт, ИИ и крипту. Суффикс канала имеет
приоритет над общим значением. Лимит webhook: 30 сообщений/мин. Постить
только в СВОИ серверы (иначе спам и бан).
"""
from __future__ import annotations

import html as html_lib
import logging
import re
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..config import Settings
from ..models import ChannelConfig, GeneratedPost, PublishResult
from .social import SocialAPIError, SocialPublisher, channel_link, http_json

logger = logging.getLogger(__name__)

MAX_TEXT = 2000  # лимит Discord на content

_HASHTAG_RE = re.compile(r"(?<!\w)#[^\s#<]{1,40}")
_WEBHOOK_PREFIXES = (
    "https://discord.com/api/webhooks/",
    "https://discordapp.com/api/webhooks/",
)


def _with_query(url: str, **params: Any) -> str:
    """Добавляет/заменяет query-параметры, не ломая уже существующие."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({str(key): str(value) for key, value in params.items()})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def discord_webhook_url(channel: ChannelConfig) -> str:
    """Webhook конкретного канала, иначе общий DISCORD_WEBHOOK_URL."""
    return _webhook_url(channel)


def _webhook_url(channel: ChannelConfig) -> str:
    """Внутренний резолвер: суффикс канала → общий webhook."""
    from .social import env_for_channel

    return env_for_channel(channel, "DISCORD_WEBHOOK_URL").strip()


def _is_webhook_url(url: str) -> bool:
    return bool(url) and url.startswith(_WEBHOOK_PREFIXES)


def discord_cta(channel: ChannelConfig) -> str:
    """Короткий призыв к действию из конфига канала.

    ``meta.discord_cta`` позволяет задать отдельный текст для Discord, не
    меняя Telegram-CTA. Если он не задан, используется обычный ``cta``.
    """
    meta = getattr(channel, "meta", None)
    if isinstance(meta, dict):
        custom = str(meta.get("discord_cta") or "").strip()
        if custom:
            return custom
    return str(getattr(channel, "cta", "") or "").strip()


def discord_text(post: Any, channel: Optional[ChannelConfig], limit: int = MAX_TEXT) -> str:
    """Текст под Discord: markdown вместо HTML, без хэштегов, с CTA и ссылкой.

    Discord не понимает Telegram HTML. Заодно убираем хэштеги (в Discord они
    не работают как навигация) и добавляем понятный призыв перейти в Telegram:
    это и есть конверсионный элемент кросспоста.
    """
    source = getattr(post, "html", "") or getattr(post, "text", "") or getattr(post, "plain_text", "") or ""
    text = str(source)

    # HTML → markdown Discord
    text = re.sub(r"<a\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", r"[\2](\1)", text, flags=re.S | re.I)
    text = re.sub(r"<b>(.*?)</b>", r"**\1**", text, flags=re.S | re.I)
    text = re.sub(r"<strong>(.*?)</strong>", r"**\1**", text, flags=re.S | re.I)
    text = re.sub(r"<i>(.*?)</i>", r"*\1*", text, flags=re.S | re.I)
    text = re.sub(r"<em>(.*?)</em>", r"*\1*", text, flags=re.S | re.I)
    text = re.sub(r"<code>(.*?)</code>", r"`\1`", text, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)

    # хэштеги в Discord бесполезны
    text = _HASHTAG_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    link = channel_link(channel) if channel is not None else ""
    cta = discord_cta(channel) if channel is not None else ""

    # Не дублируем CTA/ссылку, если генератор уже добавил их в текст.
    footer_parts = []
    if cta and cta.casefold() not in text.casefold():
        footer_parts.append(cta)
    if link and link not in text:
        footer_parts.append(link)
    footer = "\n\n".join(footer_parts)

    budget = limit - len(footer) - (2 if footer else 0)
    budget = max(40, budget)
    if len(text) > budget:
        cut = text[:budget]
        pos = max(cut.rfind("\n"), cut.rfind(". "))
        cut = cut[: pos + 1] if pos > budget * 0.6 else cut
        text = cut.rstrip() + "…"

    if not footer:
        return text[:limit]
    return f"{text}\n\n{footer}".strip()


def discord_embed(post: Any) -> Optional[Dict[str, Any]]:
    """Необязательный embed с картинкой поста (если она есть в meta)."""
    meta = getattr(post, "meta", None)
    if not isinstance(meta, dict):
        return None
    image = str(meta.get("image_url") or meta.get("image") or "").strip()
    if not image.startswith(("http://", "https://")):
        return None
    return {
        "color": 0x5865F2,
        "image": {"url": image},
    }


def discord_payload(post: Any, channel: ChannelConfig) -> Dict[str, Any]:
    """Тело webhook-запроса: текст, безопасные mention-настройки и embed."""
    payload: Dict[str, Any] = {
        "content": discord_text(post, channel, MAX_TEXT),
        # Автопосты не должны случайно пинговать @everyone/@here.
        "allowed_mentions": {"parse": []},
    }
    embed = discord_embed(post)
    if embed:
        payload["embeds"] = [embed]
    return payload


class DiscordPublisher(SocialPublisher):
    """Публикатор сообщения в Discord-канал своего сервера."""

    name = "discord"

    def check(self, channel: ChannelConfig = None) -> Tuple[bool, str]:
        if channel is None:
            from ..utils import env

            url = env("DISCORD_WEBHOOK_URL", "") or ""
        else:
            url = _webhook_url(channel)
        if not _is_webhook_url(url):
            return False, "DISCORD_WEBHOOK_URL не задан/неверный"
        return True, "Discord: webhook настроен"

    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        if not self.check(channel)[0]:
            return self._result(post, channel, ok=False, error="Discord не настроен: нет webhook")
        url = _webhook_url(channel)
        payload = discord_payload(post, channel)
        try:
            # wait=true возвращает объект сообщения (id/channel_id) вместо 204.
            data = http_json(_with_query(url, wait="true"), payload=payload)
        except SocialAPIError as exc:
            logger.warning("Discord: публикация не удалась: %s", exc)
            return self._result(post, channel, ok=False, error=str(exc))
        message_id = str(data.get("id") or "")
        channel_id = str(data.get("channel_id") or "")
        message_url = ""
        if message_id and channel_id:
            # Ссылка на сообщение работает только для публичных каналов.
            message_url = f"https://discord.com/channels/@me/{channel_id}/{message_id}"
        return self._result(post, channel, ok=True, external_id=message_id, url=message_url)
