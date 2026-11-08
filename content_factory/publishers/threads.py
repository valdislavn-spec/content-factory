"""Публикация в Threads (Meta Graph API) — текстовые посты.

Двухшаговый API:
    POST https://graph.threads.net/v1.0/{user_id}/threads        (создать контейнер)
    POST https://graph.threads.net/v1.0/{user_id}/threads_publish (опубликовать)

Креды в .env (или с суффиксом CHANNEL_ID):
    THREADS_USER_ID / THREADS_ACCESS_TOKEN
Токен: Meta for Developers → приложение → Threads API →
permissions threads_basic + threads_content_publish.
"""
from __future__ import annotations

from typing import Tuple

from ..config import Settings
from ..models import ChannelConfig, GeneratedPost, PublishResult
from .social import SocialAPIError, SocialPublisher, http_json, post_text

MAX_TEXT = 500
API_BASE = "https://graph.threads.net/v1.0"


class ThreadsPublisher(SocialPublisher):
    """Публикатор текстового поста в Threads."""

    name = "threads"

    def check(self, channel: ChannelConfig = None) -> Tuple[bool, str]:
        if channel is None:
            from ..utils import env

            user_id = env("THREADS_USER_ID", "") or ""
            token = env("THREADS_ACCESS_TOKEN", "") or ""
        else:
            user_id = self._env(channel, "THREADS_USER_ID")
            token = self._env(channel, "THREADS_ACCESS_TOKEN")
        if not user_id or not token:
            return False, "THREADS_USER_ID/THREADS_ACCESS_TOKEN не заданы"
        return True, "Threads @ {}".format(user_id)

    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        ok, detail = self.check(channel)
        if not ok:
            return self._result(post, channel, ok=False, error="Threads не настроен: {}".format(detail))
        user_id = self._env(channel, "THREADS_USER_ID")
        token = self._env(channel, "THREADS_ACCESS_TOKEN")
        text = post_text(post, MAX_TEXT, channel)
        try:
            container = http_json(
                "{}/{}/threads".format(API_BASE, user_id),
                payload={"media_type": "TEXT", "text": text, "access_token": token},
                form=True,
            )
            creation_id = str(container.get("id") or "")
            if not creation_id:
                raise SocialAPIError("Threads: контейнер не вернул id")
            published = http_json(
                "{}/{}/threads_publish".format(API_BASE, user_id),
                payload={"creation_id": creation_id, "access_token": token},
                form=True,
            )
        except SocialAPIError as exc:
            return self._result(post, channel, ok=False, error=str(exc))
        post_id = str(published.get("id") or "")
        return self._result(
            post, channel, ok=True, external_id=post_id, url="https://www.threads.net/"
        )
