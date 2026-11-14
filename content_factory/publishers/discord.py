"""Публикация в Discord через webhook — бесплатно, без OAuth, только свои серверы.

Webhook URL берётся из .env:
    DISCORD_WEBHOOK_URL
    DISCORD_WEBHOOK_URL_<CHANNEL_ID>
Лимит webhook: 30 сообщений/мин. Постить только в СВОИ серверы (иначе спам и бан).
"""
from __future__ import annotations

import html as html_lib
import logging
import re
from typing import Tuple

from ..config import Settings
from ..models import ChannelConfig, GeneratedPost, PublishResult
from .social import SocialAPIError, SocialPublisher, channel_link, http_json

logger = logging.getLogger(__name__)

MAX_TEXT = 2000  # лимит Discord на content


_HASHTAG_RE = re.compile(r"(?<!\w)#[^\s#<]{1,40}")


def discord_text(post, channel, limit: int = MAX_TEXT) -> str:
    """Текст под Discord: markdown вместо HTML, без хэштегов, со ссылкой на канал."""
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
    if link:
        budget = max(40, limit - len(link) - 4)
        if len(text) > budget:
            cut = text[:budget]
            pos = max(cut.rfind("\n"), cut.rfind(". "))
            cut = cut[: pos + 1] if pos > budget * 0.6 else cut
            text = cut.rstrip() + "…"
        return f"{text}\n\n{link}"
    return text[:limit]


class DiscordPublisher(SocialPublisher):
    """Публикатор сообщения в Discord-канал своего сервера."""

    name = "discord"

    def check(self, channel: ChannelConfig = None) -> Tuple[bool, str]:
        if channel is None:
            from ..utils import env

            url = env("DISCORD_WEBHOOK_URL", "") or ""
        else:
            url = self._env(channel, "DISCORD_WEBHOOK_URL")
        if not url.startswith("https://discord.com/api/webhooks/"):
            return False, "DISCORD_WEBHOOK_URL не задан/неверный"
        return True, "Discord: webhook настроен"

    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        if not self.check(channel)[0]:
            return self._result(post, channel, ok=False, error="Discord не настроен: нет webhook")
        url = self._env(channel, "DISCORD_WEBHOOK_URL")
        text = discord_text(post, channel, MAX_TEXT)
        try:
            data = http_json(url, payload={"content": text})
        except SocialAPIError as exc:
            logger.warning("Discord: публикация не удалась: %s", exc)
            return self._result(post, channel, ok=False, error=str(exc))
        message_id = str(data.get("id") or "")
        return self._result(post, channel, ok=True, external_id=message_id, url="")
