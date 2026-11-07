"""Публикация на страницу Facebook через Graph API (токен страницы).

Endpoint:
    POST https://graph.facebook.com/v21.0/{page_id}/feed
         message=<текст>&access_token=<page token>

Креды в .env (или с суффиксом CHANNEL_ID):
    FACEBOOK_PAGE_ID / FACEBOOK_PAGE_TOKEN

Токен: Meta for Developers → приложение → Graph API Explorer → permissions
pages_manage_posts, pages_read_engagement → получить Page Access Token
(долгий токен лучше обменять на long-lived).
"""
from __future__ import annotations

from typing import Tuple

from ..config import Settings
from ..models import ChannelConfig, GeneratedPost, PublishResult
from .social import SocialAPIError, SocialPublisher, http_json, post_text

MAX_TEXT = 60000
API_BASE = "https://graph.facebook.com/v21.0"


class FacebookPublisher(SocialPublisher):
    """Публикатор поста на страницу Facebook."""

    name = "facebook"

    def check(self, channel: ChannelConfig = None) -> Tuple[bool, str]:
        if channel is None:
            from ..utils import env

            page_id = env("FACEBOOK_PAGE_ID", "") or ""
            token = env("FACEBOOK_PAGE_TOKEN", "") or ""
        else:
            page_id = self._env(channel, "FACEBOOK_PAGE_ID")
            token = self._env(channel, "FACEBOOK_PAGE_TOKEN")
        if not page_id or not token:
            return False, "FACEBOOK_PAGE_ID/FACEBOOK_PAGE_TOKEN не заданы"
        return True, "Facebook Page {}".format(page_id)

    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        ok, detail = self.check(channel)
        if not ok:
            return self._result(post, channel, ok=False, error="Facebook не настроен: {}".format(detail))
        page_id = self._env(channel, "FACEBOOK_PAGE_ID")
        token = self._env(channel, "FACEBOOK_PAGE_TOKEN")
        text = post_text(post, MAX_TEXT, channel)
        try:
            data = http_json(
                "{}/{}/feed".format(API_BASE, page_id),
                payload={"message": text, "access_token": token},
                form=True,
            )
        except SocialAPIError as exc:
            return self._result(post, channel, ok=False, error=str(exc))
        post_id = str(data.get("id") or "")
        if not post_id:
            return self._result(post, channel, ok=False, error="Facebook: нет id в ответе")
        return self._result(
            post,
            channel,
            ok=True,
            external_id=post_id,
            url="https://www.facebook.com/{}".format(post_id),
        )
