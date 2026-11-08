"""Публикация в Discord через webhook — бесплатно, без OAuth, только свои серверы.

Webhook URL берётся из .env:
    DISCORD_WEBHOOK_URL
    DISCORD_WEBHOOK_URL_<CHANNEL_ID>
Лимит webhook: 30 сообщений/мин. Постить только в СВОИ серверы (иначе спам и бан).
"""
from __future__ import annotations

import logging
from typing import Tuple

from ..config import Settings
from ..models import ChannelConfig, GeneratedPost, PublishResult
from .social import SocialAPIError, SocialPublisher, http_json, post_text

logger = logging.getLogger(__name__)

MAX_TEXT = 2000  # лимит Discord на content


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
        text = post_text(post, MAX_TEXT, channel)
        try:
            data = http_json(url, payload={"content": text})
        except SocialAPIError as exc:
            logger.warning("Discord: публикация не удалась: %s", exc)
            return self._result(post, channel, ok=False, error=str(exc))
        message_id = str(data.get("id") or "")
        return self._result(post, channel, ok=True, external_id=message_id, url="")
