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


BOT_API = "https://discord.com/api/v10"
# Discord edge блокирует bot-запросы с браузерным User-Agent (40333).
BOT_USER_AGENT = "DiscordBot (https://github.com/valdislavn-spec/content-factory, 1.0)"


def _bot_token() -> str:
    from ..utils import env

    return env("DISCORD_BOT_TOKEN", "").strip()


def _channel_id(channel: ChannelConfig) -> str:
    value = str(_channel_meta(channel).get("discord_channel_id") or "").strip()
    return value if value.isdigit() else ""


def _channel_meta(channel: ChannelConfig) -> Dict[str, Any]:
    """Достаёт публичные meta-настройки канала из разных форм ChannelConfig."""
    meta = getattr(channel, "meta", None)
    if not isinstance(meta, dict):
        return {}
    merged: Dict[str, Any] = {}
    raw = meta.get("raw")
    if isinstance(raw, dict):
        # Loader хранит исходный YAML в meta["raw"], а вложенный meta — в raw["meta"].
        nested = raw.get("meta")
        if isinstance(nested, dict):
            merged.update(nested)
    merged.update({key: value for key, value in meta.items() if key != "raw"})
    return merged


def discord_identity(channel: ChannelConfig) -> Tuple[str, str]:
    """Имя и аватар, которые webhook показывает в общей ленте Discord."""
    meta = _channel_meta(channel)
    username = str(meta.get("discord_username") or getattr(channel, "title", "") or "").strip()
    avatar = str(meta.get("discord_avatar_url") or "").strip()
    if avatar and not avatar.startswith(("http://", "https://")):
        avatar = ""
    return username[:80], avatar


def discord_cta(channel: ChannelConfig) -> str:
    """Короткий призыв к действию из конфига канала.

    ``meta.discord_cta`` позволяет задать отдельный текст для Discord, не
    меняя Telegram-CTA. Если он не задан, используется обычный ``cta``.
    """
    custom = str(_channel_meta(channel).get("discord_cta") or "").strip()
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

    if channel is not None:
        link = str(_channel_meta(channel).get("discord_cta_url") or channel_link(channel)).strip()
    else:
        link = ""
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


_EMBED_COLORS = {
    "sport-news": 0x2ECC71,
    "ai-news": 0x9B59B6,
    "crypto-news": 0xF39C12,
}


def discord_embed(post: Any, channel: Optional[ChannelConfig] = None) -> Optional[Dict[str, Any]]:
    """Embed с картинкой и визуальной меткой канала."""
    meta = getattr(post, "meta", None)
    if not isinstance(meta, dict):
        meta = {}
    image = str(meta.get("image_url") or meta.get("image") or "").strip()
    channel_id = str(getattr(channel, "id", "") or "")
    color = _EMBED_COLORS.get(channel_id, 0x5865F2)
    author: Dict[str, Any] = {}
    if channel is not None:
        name = str(getattr(channel, "title", "") or "").strip()
        _, icon = discord_identity(channel)
        if name:
            author["name"] = name[:256]
        if icon:
            author["icon_url"] = icon
    embed: Dict[str, Any] = {"color": color}
    if author:
        embed["author"] = author
    if image.startswith(("http://", "https://")):
        embed["image"] = {"url": image}
    return embed if (author or image) else None


def discord_payload(post: Any, channel: ChannelConfig) -> Dict[str, Any]:
    """Тело webhook-запроса: текст, безопасные mention-настройки и embed."""
    payload: Dict[str, Any] = {
        "content": discord_text(post, channel, MAX_TEXT),
        # Автопосты не должны случайно пинговать @everyone/@here.
        "allowed_mentions": {"parse": []},
    }
    embed = discord_embed(post, channel)
    if embed:
        payload["embeds"] = [embed]
    username, avatar = discord_identity(channel)
    if username:
        payload["username"] = username
    if avatar:
        payload["avatar_url"] = avatar
    return payload


class DiscordPublisher(SocialPublisher):
    """Публикатор сообщения в Discord-канал своего сервера."""

    name = "discord"

    def check(self, channel: ChannelConfig = None) -> Tuple[bool, str]:
        if channel is not None and _bot_token() and _channel_id(channel):
            return True, "Discord: bot-канал настроен"
        if channel is None:
            from ..utils import env

            url = env("DISCORD_WEBHOOK_URL", "") or ""
        else:
            url = _webhook_url(channel)
        if not _is_webhook_url(url):
            return False, "DISCORD_BOT_TOKEN/канал или DISCORD_WEBHOOK_URL не заданы"
        return True, "Discord: webhook настроен"

    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        if not self.check(channel)[0]:
            return self._result(post, channel, ok=False, error="Discord не настроен")
        payload = discord_payload(post, channel)
        webhook_payload = dict(payload)
        channel_id = _channel_id(channel)
        token = _bot_token()
        data: Dict[str, Any] = {}
        if token and channel_id:
            # Bot API не принимает webhook-only поля username/avatar_url.
            payload.pop("username", None)
            payload.pop("avatar_url", None)
            try:
                data = http_json(
                    f"{BOT_API}/channels/{channel_id}/messages",
                    payload=payload,
                    headers={
                        "Authorization": f"Bot {token}",
                        "User-Agent": BOT_USER_AGENT,
                    },
                )
            except SocialAPIError as exc:
                logger.warning("Discord bot API: %s; пробую webhook", exc)
        if not data:
            url = _webhook_url(channel)
            if not _is_webhook_url(url):
                return self._result(post, channel, ok=False, error="Discord: нет рабочего способа публикации")
            try:
                # wait=true возвращает объект сообщения (id/channel_id) вместо 204.
                data = http_json(_with_query(url, wait="true"), payload=webhook_payload)
            except SocialAPIError as exc:
                logger.warning("Discord: публикация не удалась: %s", exc)
                return self._result(post, channel, ok=False, error=str(exc))
        message_id = str(data.get("id") or "")
        channel_id = str(data.get("channel_id") or "")
        guild_id = str(data.get("guild_id") or "")
        message_url = ""
        if message_id and channel_id and guild_id:
            # Валидная ссылка требует guild_id; без него @me — неверный URL.
            message_url = f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
        return self._result(post, channel, ok=True, external_id=message_id, url=message_url)
