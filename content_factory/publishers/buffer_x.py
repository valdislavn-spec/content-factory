"""X (Twitter) через Buffer API — fallback, пока прямой OAuth1 app read-only.

Buffer уже содержит подключённый X-канал @NValdislav. Публикатор берёт
`BUFFER_API_KEY` и либо `BUFFER_X_CHANNEL_ID`, либо находит twitter-канал в
первой организации аккаунта Buffer.
"""
from __future__ import annotations

import logging
from typing import Tuple

from ..config import Settings
from ..integrations.buffer import BufferClient, BufferError
from ..models import ChannelConfig, GeneratedPost, PublishResult
from ..utils import env
from .social import SocialPublisher, post_text

logger = logging.getLogger(__name__)

MAX_TEXT = 280


class BufferXPublisher(SocialPublisher):
    """Публикация в X через Buffer GraphQL API."""

    name = "buffer-x"

    def check(self, channel: ChannelConfig = None) -> Tuple[bool, str]:
        if not env("BUFFER_API_KEY", ""):
            return False, "BUFFER_API_KEY не задан"
        return True, "X через Buffer"

    def _channel_id(self, client: BufferClient) -> str:
        explicit = env("BUFFER_X_CHANNEL_ID", "")
        if explicit:
            return explicit
        organizations = client.organizations()
        if not organizations:
            raise BufferError("Buffer: нет организаций")
        channels = client.channels(str(organizations[0].get("id") or ""))
        for channel in channels:
            if str(channel.get("service") or "").lower() in {"twitter", "x"}:
                return str(channel.get("id") or "")
        raise BufferError("Buffer: X-канал не найден")

    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        ok, detail = self.check(channel)
        if not ok:
            return self._result(post, channel, ok=False, error="Buffer X не настроен: {}".format(detail))
        text = post_text(post, MAX_TEXT, channel)
        try:
            client = BufferClient.from_env()
            channel_id = self._channel_id(client)
            payload = client.create_post(channel_id, text, mode="shareNow")
        except Exception as exc:  # noqa: BLE001 - публикатор не бросает наружу
            logger.warning("Buffer X: публикация не удалась: %s", exc)
            return self._result(post, channel, ok=False, error="Buffer X: {}".format(exc))
        return self._result(
            post,
            channel,
            ok=True,
            external_id=str(payload.get("id") or ""),
            url=str(payload.get("externalLink") or ""),
        )
