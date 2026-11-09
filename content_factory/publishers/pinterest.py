"""Публикация пина в Pinterest (API v5): картинка + описание.

Нужен публичный HTTPS-URL картинки (как у Instagram).

Креды:
    PINTEREST_ACCESS_TOKEN / PINTEREST_BOARD_ID
    PINTEREST_IMAGE_URL            (общий) или
    PINTEREST_IMAGE_URL_<CHANNEL>

Токен: developers.pinterest.com → приложение → OAuth2 с scope pins:write.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from ..config import Settings
from ..utils import env
from ..models import ChannelConfig, GeneratedPost, PublishResult
from .social import SocialAPIError, SocialPublisher, http_json, post_text

API_BASE = "https://api.pinterest.com/v5"
SANDBOX_BASE = "https://api-sandbox.pinterest.com/v5"
API_URL = API_BASE + "/pins"
MAX_DESCRIPTION = 500


class PinterestPublisher(SocialPublisher):
    """Публикатор пина в Pinterest."""

    name = "pinterest"
    _ROOT = Path(__file__).resolve().parents[2]
    _MANIFEST = _ROOT / "config" / "pinterest_brand_urls.yaml"

    def _manifest_url(self, channel: ChannelConfig) -> str:
        """URL брендового пина с GitHub Pages (config/pinterest_brand_urls.yaml)."""
        try:
            import yaml

            data = yaml.safe_load(self._MANIFEST.read_text(encoding="utf-8")) or {}
            value = str((data.get("channels") or {}).get(str(channel.id)) or "").strip()
            return value if value.startswith(("http://", "https://")) else ""
        except Exception:  # noqa: BLE001 - манифест опционален
            return ""

    def _image_url(self, channel: ChannelConfig, post: Optional[GeneratedPost] = None) -> str:
        env_url = self._env(channel, "PINTEREST_IMAGE_URL")
        if env_url:
            return env_url
        if post is not None:
            meta_url = str((getattr(post, "meta", {}) or {}).get("pinterest_image_url") or "").strip()
            if meta_url.startswith(("http://", "https://")):
                return meta_url
        return self._manifest_url(channel)

    def check(self, channel: ChannelConfig = None) -> Tuple[bool, str]:
        if channel is None:
            from ..utils import env

            token = env("PINTEREST_ACCESS_TOKEN", "") or ""
            board = env("PINTEREST_BOARD_ID", "") or ""
        else:
            token = self._env(channel, "PINTEREST_ACCESS_TOKEN")
            board = self._env(channel, "PINTEREST_BOARD_ID")
        if not token or not board:
            return False, "PINTEREST_ACCESS_TOKEN/PINTEREST_BOARD_ID не заданы"
        return True, "Pinterest board {}".format(board)

    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        ok, detail = self.check(channel)
        if not ok:
            return self._result(post, channel, ok=False, error="Pinterest не настроен: {}".format(detail))
        image_url = self._image_url(channel, post)
        if not image_url:
            return self._result(
                post, channel, ok=False,
                error="нужен публичный HTTPS-URL картинки: PINTEREST_IMAGE_URL[_CHANNEL]",
            )
        token = self._env(channel, "PINTEREST_ACCESS_TOKEN")
        board_id = self._env(channel, "PINTEREST_BOARD_ID")
        text = post_text(post, MAX_DESCRIPTION, channel)
        title = (text.splitlines()[0] if text.splitlines() else "Update")[:100]
        payload = {
            "board_id": board_id,
            "title": title,
            "description": text,
            "alt_text": title,
            "media_source": {"source_type": "image_url", "url": image_url},
        }
        link = self._env(channel, "PINTEREST_LINK") or str(getattr(channel, "public_url", "") or "").strip()
        if link:
            payload["link"] = link
        try:
            base = (env("PINTEREST_API_BASE", API_BASE) or API_BASE).rstrip("/")
            data = http_json(
                base + "/pins",
                payload=payload,
                headers={"Authorization": "Bearer {}".format(token)},
            )
        except SocialAPIError as exc:
            return self._result(post, channel, ok=False, error=str(exc))
        pin_id = str(data.get("id") or "")
        return self._result(
            post, channel, ok=True, external_id=pin_id,
            url="https://www.pinterest.com/pin/{}/".format(pin_id) if pin_id else "",
        )
