"""Публикация в LinkedIn (организация или личный профиль) через REST API.

Endpoint:
    POST https://api.linkedin.com/rest/posts

Креды в .env (или с суффиксом CHANNEL_ID):
    LINKEDIN_ACCESS_TOKEN
    LINKEDIN_AUTHOR_URN  (urn:li:organization:123 или urn:li:person:abc)

Токен: LinkedIn Developers → приложение → products «Share on LinkedIn» +
«Sign In with LinkedIn» → OAuth 2.0 с scope w_member_social / w_organization_social.
"""
from __future__ import annotations

from typing import Tuple

from ..config import Settings
from ..models import ChannelConfig, GeneratedPost, PublishResult
from .social import SocialAPIError, SocialPublisher, http_json, post_text

MAX_TEXT = 2900
API_URL = "https://api.linkedin.com/rest/posts"
LINKEDIN_VERSION = "202411"


class LinkedInPublisher(SocialPublisher):
    """Публикатор поста в LinkedIn (лента организации/профиля)."""

    name = "linkedin"

    def check(self, channel: ChannelConfig = None) -> Tuple[bool, str]:
        if channel is None:
            from ..utils import env

            token = env("LINKEDIN_ACCESS_TOKEN", "") or ""
            author = env("LINKEDIN_AUTHOR_URN", "") or ""
        else:
            token = self._env(channel, "LINKEDIN_ACCESS_TOKEN")
            author = self._env(channel, "LINKEDIN_AUTHOR_URN")
        if not token or not author:
            return False, "LINKEDIN_ACCESS_TOKEN/LINKEDIN_AUTHOR_URN не заданы"
        return True, "LinkedIn {}".format(author)

    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        ok, detail = self.check(channel)
        if not ok:
            return self._result(post, channel, ok=False, error="LinkedIn не настроен: {}".format(detail))
        token = self._env(channel, "LINKEDIN_ACCESS_TOKEN")
        author = self._env(channel, "LINKEDIN_AUTHOR_URN")
        text = post_text(post, MAX_TEXT, channel)
        payload = {
            "author": author,
            "commentary": text,
            "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED"},
            "lifecycleState": "PUBLISHED",
        }
        try:
            data = http_json(
                API_URL,
                payload=payload,
                headers={
                    "Authorization": "Bearer {}".format(token),
                    "LinkedIn-Version": LINKEDIN_VERSION,
                    "X-Restli-Protocol-Version": "2.0.0",
                },
            )
        except SocialAPIError as exc:
            return self._result(post, channel, ok=False, error=str(exc))
        post_urn = str(data.get("id") or "")
        return self._result(
            post,
            channel,
            ok=True,
            external_id=post_urn,
            url="https://www.linkedin.com/feed/" if not post_urn else "https://www.linkedin.com/feed/",
        )
