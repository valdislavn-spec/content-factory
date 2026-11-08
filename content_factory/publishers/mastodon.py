"""Публикация в Mastodon (любой инстанс) — бесплатно, без ревью.

Endpoint: POST https://<instance>/api/v1/statuses (Bearer-токен приложения).
Креды в .env:
    MASTODON_BASE_URL / MASTODON_TOKEN
    MASTODON_BASE_URL_<CHANNEL_ID> / MASTODON_TOKEN_<CHANNEL_ID>
Токен выдаётся приложению инстанса (Preferences → Development → New application,
scope write:statuses). Бот-аккаунт рекомендуется помечать как бота.
"""
from __future__ import annotations

import logging
import re
from typing import Tuple

from ..config import Settings
from ..models import ChannelConfig, GeneratedPost, PublishResult
from .social import SocialAPIError, SocialPublisher, channel_link, http_json, post_text

logger = logging.getLogger(__name__)

MAX_TEXT = 500  # лимит Mastodon по умолчанию (инстанс может менять)


class MastodonPublisher(SocialPublisher):
    """Публикатор статуса в Mastodon."""

    name = "mastodon"

    def check(self, channel: ChannelConfig = None) -> Tuple[bool, str]:
        if channel is None:
            from ..utils import env

            base = env("MASTODON_BASE_URL", "") or ""
            token = env("MASTODON_TOKEN", "") or ""
        else:
            base = self._env(channel, "MASTODON_BASE_URL")
            token = self._env(channel, "MASTODON_TOKEN")
        if not base or not token:
            return False, "MASTODON_BASE_URL/MASTODON_TOKEN не заданы"
        return True, f"Mastodon: {base}"

    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        if not self.check(channel)[0]:
            return self._result(post, channel, ok=False, error="Mastodon не настроен: нет кредов")
        base = self._env(channel, "MASTODON_BASE_URL").rstrip("/")
        token = self._env(channel, "MASTODON_TOKEN")
        text = post_text(post, MAX_TEXT, channel)
        from ..utils import env as _env

        if str(_env("MASTODON_NO_LINKS", "") or "").strip().lower() in {"1", "true", "yes", "on"}:
            # Новый аккаунт: mastodon.social удаляет посты с внешними ссылками.
            # Полосуем URL, но свой канал оставляем текстовым упоминанием,
            # иначе зеркало не приводит подписчиков.
            own = channel_link(channel) if channel is not None else ""
            if own:
                handle = own.rstrip("/").rsplit("/", 1)[-1]
                text = text.replace(own, "Telegram: @" + handle)
            text = re.sub(r"https?://\S+", "", text)
            text = re.sub(r"[ \t]{2,}", " ", text).strip()
            text = re.sub(r"\n{3,}", "\n\n", text)
        try:
            data = http_json(
                f"{base}/api/v1/statuses",
                payload={"status": text},
                headers={"Authorization": f"Bearer {token}"},
                form=True,
            )
        except SocialAPIError as exc:
            logger.warning("Mastodon: публикация не удалась: %s", exc)
            return self._result(post, channel, ok=False, error=str(exc))
        status_id = str(data.get("id") or "")
        url = str(data.get("url") or data.get("uri") or "")
        return self._result(post, channel, ok=True, external_id=status_id, url=url)
