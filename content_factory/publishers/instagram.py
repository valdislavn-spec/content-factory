"""Публикация в Instagram (Graph API): фото + подпись.

Instagram API не принимает текст без изображения — нужен публичный HTTPS-URL
картинки (наши карточки можно отдавать через LANDING_HOST / Cloudflare R2).

Креды:
    INSTAGRAM_USER_ID / INSTAGRAM_ACCESS_TOKEN
    INSTAGRAM_IMAGE_URL            (общий) или
    INSTAGRAM_IMAGE_URL_<CHANNEL>  (для канала)

Токен: Meta for Developers → Instagram Graph API →
instagram_basic + instagram_content_publish (нужен Professional account).
"""
from __future__ import annotations

from typing import Tuple

from ..config import Settings
from ..models import ChannelConfig, GeneratedPost, PublishResult
from .social import SocialAPIError, SocialPublisher, http_json, post_text

MAX_CAPTION = 2200
API_BASE = "https://graph.facebook.com/v21.0"


class InstagramPublisher(SocialPublisher):
    """Публикатор фото-поста в Instagram."""

    name = "instagram"

    def _image_url(self, channel: ChannelConfig) -> str:
        url = self._env(channel, "INSTAGRAM_IMAGE_URL")
        if not url:
            url = str((getattr(channel, "options", {}) or {}).get("instagram_image_url", "") or "")
        return url

    def check(self, channel: ChannelConfig = None) -> Tuple[bool, str]:
        if channel is None:
            from ..utils import env

            user_id = env("INSTAGRAM_USER_ID", "") or ""
            token = env("INSTAGRAM_ACCESS_TOKEN", "") or ""
        else:
            user_id = self._env(channel, "INSTAGRAM_USER_ID")
            token = self._env(channel, "INSTAGRAM_ACCESS_TOKEN")
        if not user_id or not token:
            return False, "INSTAGRAM_USER_ID/INSTAGRAM_ACCESS_TOKEN не заданы"
        return True, "Instagram @ {}".format(user_id)

    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        ok, detail = self.check(channel)
        if not ok:
            return self._result(post, channel, ok=False, error="Instagram не настроен: {}".format(detail))
        image_url = self._image_url(channel)
        if not image_url:
            return self._result(
                post, channel, ok=False,
                error="нужен публичный HTTPS-URL картинки: INSTAGRAM_IMAGE_URL[_CHANNEL]",
            )
        user_id = self._env(channel, "INSTAGRAM_USER_ID")
        token = self._env(channel, "INSTAGRAM_ACCESS_TOKEN")
        caption = post_text(post, MAX_CAPTION, channel)
        try:
            container = http_json(
                "{}/{}/media".format(API_BASE, user_id),
                payload={"image_url": image_url, "caption": caption, "access_token": token},
                form=True,
            )
            creation_id = str(container.get("id") or "")
            if not creation_id:
                raise SocialAPIError("Instagram: контейнер не вернул id")
            published = http_json(
                "{}/{}/media_publish".format(API_BASE, user_id),
                payload={"creation_id": creation_id, "access_token": token},
                form=True,
            )
        except SocialAPIError as exc:
            return self._result(post, channel, ok=False, error=str(exc))
        media_id = str(published.get("id") or "")
        return self._result(post, channel, ok=True, external_id=media_id, url="")
