"""Fediverse-сети, не требующие ревью: Pleroma, Akkoma, GoToSocial, Friendica, Misskey.

Pleroma / Akkoma / GoToSocial / Friendica совместимы с Mastodon API:
    POST https://<instance>/api/v1/statuses   (Bearer access token)

Misskey использует собственный API:
    POST https://<host>/api/notes/create     ({"i": token, "text": ...})

Креды в .env (можно отдельный аккаунт на канал суффиксом <CHANNEL_ID>):
    PLEROMA_BASE_URL / PLEROMA_TOKEN
    AKKOMA_BASE_URL / AKKOMA_TOKEN
    GOTOSOCIAL_BASE_URL / GOTOSOCIAL_TOKEN
    FRIENDICA_BASE_URL / FRIENDICA_TOKEN
    MISSKEY_HOST / MISSKEY_TOKEN

Публикаторы опциональные: без кредов конвейер молча пропускает их.
"""
from __future__ import annotations

import logging
import re
from typing import Tuple

from ..config import Settings
from ..models import ChannelConfig, GeneratedPost, PublishResult
from .social import SocialAPIError, SocialPublisher, http_json, post_text

logger = logging.getLogger(__name__)

MASTODON_COMPAT_LIMIT = 500   # безопасный лимит для всех Mastodon-совместимых
MISSKEY_DEFAULT_LIMIT = 3000


def _global_env(name: str) -> str:
    from ..utils import env

    return (env(name, "") or "").strip()


def _strip_links(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    return re.sub(r"\n{3,}", "\n\n", text)


class MastodonCompatiblePublisher(SocialPublisher):
    """База для сетей с Mastodon-совместимым API (/api/v1/statuses)."""

    name = "mastodon_compatible"
    network = "Fediverse"
    base_env = ""
    token_env = ""

    def check(self, channel: ChannelConfig = None) -> Tuple[bool, str]:
        if channel is None:
            base = _global_env(self.base_env)
            token = _global_env(self.token_env)
        else:
            base = self._env(channel, self.base_env)
            token = self._env(channel, self.token_env)
        if not base or not token:
            return False, f"{self.base_env}/{self.token_env} не заданы"
        return True, f"{self.network}: {base}"

    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        if not self.check(channel)[0]:
            return self._result(
                post, channel, ok=False,
                error=f"{self.network} не настроен: нет кредов",
            )
        base = self._env(channel, self.base_env).rstrip("/")
        token = self._env(channel, self.token_env)
        text = post_text(post, MASTODON_COMPAT_LIMIT, channel)
        no_links = _global_env("MASTODON_NO_LINKS").lower() in {"1", "true", "yes", "on"}
        if no_links:
            text = _strip_links(text)
        try:
            data = http_json(
                f"{base}/api/v1/statuses",
                payload={"status": text},
                headers={"Authorization": f"Bearer {token}"},
                form=True,
            )
        except SocialAPIError as exc:
            logger.warning("%s: публикация не удалась: %s", self.network, exc)
            return self._result(post, channel, ok=False, error=str(exc))
        status_id = str(data.get("id") or "")
        url = str(data.get("url") or data.get("uri") or "")
        return self._result(post, channel, ok=True, external_id=status_id, url=url)


class PleromaPublisher(MastodonCompatiblePublisher):
    name = "pleroma"
    network = "Pleroma"
    base_env = "PLEROMA_BASE_URL"
    token_env = "PLEROMA_TOKEN"


class AkkomaPublisher(MastodonCompatiblePublisher):
    name = "akkoma"
    network = "Akkoma"
    base_env = "AKKOMA_BASE_URL"
    token_env = "AKKOMA_TOKEN"


class GoToSocialPublisher(MastodonCompatiblePublisher):
    name = "gotosocial"
    network = "GoToSocial"
    base_env = "GOTOSOCIAL_BASE_URL"
    token_env = "GOTOSOCIAL_TOKEN"


class FriendicaPublisher(MastodonCompatiblePublisher):
    name = "friendica"
    network = "Friendica"
    base_env = "FRIENDICA_BASE_URL"
    token_env = "FRIENDICA_TOKEN"


class MisskeyPublisher(SocialPublisher):
    """Публикатор в Misskey / Firefish / Sharkey (Misskey API)."""

    name = "misskey"

    def _host(self, channel: ChannelConfig = None) -> str:
        raw = (
            _global_env("MISSKEY_HOST")
            if channel is None
            else self._env(channel, "MISSKEY_HOST")
        ) or _global_env("MISSKEY_HOST")
        host = raw.rstrip("/")
        return re.sub(r"^https?://", "", host).strip("/")

    def check(self, channel: ChannelConfig = None) -> Tuple[bool, str]:
        host = self._host(channel)
        token = (
            _global_env("MISSKEY_TOKEN")
            if channel is None
            else self._env(channel, "MISSKEY_TOKEN")
        ) or _global_env("MISSKEY_TOKEN")
        if not host or not token:
            return False, "MISSKEY_HOST/MISSKEY_TOKEN не заданы"
        return True, f"Misskey: {host}"

    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        if not self.check(channel)[0]:
            return self._result(post, channel, ok=False, error="Misskey не настроен: нет кредов")
        host = self._host(channel)
        token = self._env(channel, "MISSKEY_TOKEN") or _global_env("MISSKEY_TOKEN")
        limit = int(_global_env("MISSKEY_MAX_CHARS") or MISSKEY_DEFAULT_LIMIT)
        text = post_text(post, limit, channel)
        no_links = _global_env("MASTODON_NO_LINKS").lower() in {"1", "true", "yes", "on"}
        if no_links:
            text = _strip_links(text)
        try:
            data = http_json(
                f"https://{host}/api/notes/create",
                payload={"i": token, "text": text, "visibility": "public"},
            )
        except SocialAPIError as exc:
            logger.warning("Misskey: публикация не удалась: %s", exc)
            return self._result(post, channel, ok=False, error=str(exc))
        note = data.get("createdNote") or {}
        note_id = str(note.get("id") or "")
        url = str(note.get("url") or (f"https://{host}/notes/{note_id}" if note_id else ""))
        return self._result(post, channel, ok=True, external_id=note_id, url=url)
