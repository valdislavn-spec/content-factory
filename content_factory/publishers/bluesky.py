"""Публикация в Bluesky (AT Protocol) — бесплатно, без ревью, лимиты большие.

Endpoints:
    POST https://bsky.social/xrpc/com.atproto.server.createSession
    POST https://bsky.social/xrpc/com.atproto.repo.createRecord

Креды в .env (для каждого канала — свой аккаунт по желанию):
    BLUESKY_HANDLE / BLUESKY_APP_PASSWORD
    BLUESKY_HANDLE_<CHANNEL_ID> / BLUESKY_APP_PASSWORD_<CHANNEL_ID>
    BLUESKY_BASE_URL (опционально, по умолчанию https://bsky.social)

Пароль — именно App Password (Settings → App Passwords), не основной пароль.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Tuple

from ..config import Settings
from ..models import ChannelConfig, GeneratedPost, PublishResult
from .social import SocialAPIError, SocialPublisher, http_json, post_text

logger = logging.getLogger(__name__)

MAX_TEXT = 280  # лимит Bluesky — 300 графем; оставляем запас


class BlueskyPublisher(SocialPublisher):
    """Публикатор поста в Bluesky через AT Protocol."""

    name = "bluesky"

    def _base_url(self) -> str:
        return (self._env_global("BLUESKY_BASE_URL") or "https://bsky.social").rstrip("/")

    @staticmethod
    def _env_global(name: str) -> str:
        from ..utils import env

        return env(name, "") or ""

    def check(self, channel: ChannelConfig = None) -> Tuple[bool, str]:
        if channel is None:
            # без канала проверяем только общий аккаунт
            from ..utils import env

            handle = env("BLUESKY_HANDLE", "") or ""
            password = env("BLUESKY_APP_PASSWORD", "") or ""
        else:
            handle = self._env(channel, "BLUESKY_HANDLE")
            password = self._env(channel, "BLUESKY_APP_PASSWORD")
        if not handle or not password:
            return False, "BLUESKY_HANDLE/BLUESKY_APP_PASSWORD не заданы"
        return True, f"Bluesky: @{handle.lstrip('@')}"

    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        if not self.check(channel)[0]:
            return self._result(post, channel, ok=False, error="Bluesky не настроен: нет кредов")
        handle = self._env(channel, "BLUESKY_HANDLE").lstrip("@")
        password = self._env(channel, "BLUESKY_APP_PASSWORD")
        text = post_text(post, MAX_TEXT, channel)
        try:
            session = http_json(
                f"{self._base_url()}/xrpc/com.atproto.server.createSession",
                payload={"identifier": handle, "password": password},
            )
            access_jwt = str(session.get("accessJwt") or "")
            did = str(session.get("did") or "")
            if not access_jwt or not did:
                raise SocialAPIError("Bluesky: createSession не вернул accessJwt/did")
            record = {
                "$type": "app.bsky.feed.post",
                "text": text,
                "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            }
            data = http_json(
                f"{self._base_url()}/xrpc/com.atproto.repo.createRecord",
                payload={"repo": did, "collection": "app.bsky.feed.post", "record": record},
                headers={"Authorization": f"Bearer {access_jwt}"},
            )
        except SocialAPIError as exc:
            logger.warning("Bluesky: публикация не удалась: %s", exc)
            return self._result(post, channel, ok=False, error=str(exc))
        uri = str(data.get("uri") or "")
        rkey = uri.rsplit("/", 1)[-1] if uri else ""
        url = f"https://bsky.app/profile/{handle}/post/{rkey}" if rkey else ""
        return self._result(post, channel, ok=True, external_id=uri, url=url)
