"""Публикация в Medium через Integration API (самый простой токен).

Endpoints:
    GET  https://api.medium.com/v1/me
    POST https://api.medium.com/v1/users/{id}/posts

Креды в .env:
    MEDIUM_TOKEN   (Settings → Security and apps → Integration tokens)

Публикуем пост как Markdown: заголовок — первая строка текста.
"""
from __future__ import annotations

from typing import Tuple

from ..config import Settings
from ..models import ChannelConfig, GeneratedPost, PublishResult
from .social import SocialAPIError, SocialPublisher, http_json, post_text

MAX_TEXT = 100000
API_BASE = "https://api.medium.com/v1"


class MediumPublisher(SocialPublisher):
    """Публикатор статьи/поста в Medium."""

    name = "medium"

    def check(self, channel: ChannelConfig = None) -> Tuple[bool, str]:
        token = self._env(channel, "MEDIUM_TOKEN") if channel is not None else ""
        if not token:
            from ..utils import env

            token = env("MEDIUM_TOKEN", "") or ""
        if not token:
            return False, "MEDIUM_TOKEN не задан"
        return True, "Medium (Integration API)"

    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        ok, detail = self.check(channel)
        if not ok:
            return self._result(post, channel, ok=False, error="Medium не настроен: {}".format(detail))
        token = self._env(channel, "MEDIUM_TOKEN") or ""
        if not token:
            from ..utils import env

            token = env("MEDIUM_TOKEN", "") or ""
        headers = {"Authorization": "Bearer {}".format(token)}
        text = post_text(post, MAX_TEXT, channel)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        title = (lines[0] if lines else "Update")[:100]
        content = text
        try:
            me = http_json(API_BASE + "/me", method="GET", headers=headers)
            user_id = str(me.get("data", {}).get("id") or "")
            if not user_id:
                raise SocialAPIError("Medium: /me не вернул id пользователя")
            data = http_json(
                "{}/users/{}/posts".format(API_BASE, user_id),
                payload={
                    "title": title,
                    "contentFormat": "markdown",
                    "content": content,
                    "publishStatus": "public",
                },
                headers=headers,
            )
        except SocialAPIError as exc:
            return self._result(post, channel, ok=False, error=str(exc))
        medium_id = str(data.get("data", {}).get("id") or "")
        url = str(data.get("data", {}).get("url") or "")
        return self._result(post, channel, ok=True, external_id=medium_id, url=url)
