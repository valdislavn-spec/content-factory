"""Публикация в X (Twitter) через API v2 — OAuth 1.0a, без браузера.

Endpoints:
    POST https://api.x.com/2/tweets   {"text": "..."}

Креды в .env (можно переопределить для канала суффиксом CHANNEL_ID):
    X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_SECRET
    X_API_KEY_<CHANNEL_ID> и т.д.

Где взять: https://developer.x.com → Projects & Apps → приложение → Keys and
tokens (API Key/Secret, Access Token/Secret с правами Write).
Бесплатный тариф X API позволяет публиковать ~500 постов в месяц.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from typing import Tuple
from urllib.parse import quote

from ..config import Settings
from ..models import ChannelConfig, GeneratedPost, PublishResult
from .social import SocialAPIError, SocialPublisher, http_json, post_text

logger = logging.getLogger(__name__)

MAX_TEXT = 280
API_URL = "https://api.x.com/2/tweets"


def _encode(value: str) -> str:
    """RFC 3986 percent-encoding для OAuth 1.0a."""
    return quote(str(value), safe="~")


def oauth1_header(
    method: str,
    url: str,
    consumer_key: str,
    consumer_secret: str,
    token: str,
    token_secret: str,
) -> str:
    """Заголовок OAuth 1.0a для запроса с JSON-телом (тело в подпись не входит)."""
    params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    parameter_string = "&".join(
        "{}={}".format(_encode(key), _encode(value)) for key, value in sorted(params.items())
    )
    base_string = "&".join([method.upper(), _encode(url), _encode(parameter_string)])
    signing_key = "{}&{}".format(_encode(consumer_secret), _encode(token_secret))
    digest = hmac.new(signing_key.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha1).digest()
    params["oauth_signature"] = base64.b64encode(digest).decode("ascii")
    return "OAuth " + ", ".join(
        '{}="{}"'.format(_encode(key), _encode(value)) for key, value in sorted(params.items())
    )


class XPublisher(SocialPublisher):
    """Публикатор поста в X (Twitter) через API v2."""

    name = "x"

    def _creds(self, channel: ChannelConfig) -> Tuple[str, str, str, str]:
        return (
            self._env(channel, "X_API_KEY"),
            self._env(channel, "X_API_SECRET"),
            self._env(channel, "X_ACCESS_TOKEN"),
            self._env(channel, "X_ACCESS_SECRET"),
        )

    def check(self, channel: ChannelConfig = None) -> Tuple[bool, str]:
        if channel is None:
            from ..utils import env

            creds = (
                env("X_API_KEY", "") or "",
                env("X_API_SECRET", "") or "",
                env("X_ACCESS_TOKEN", "") or "",
                env("X_ACCESS_SECRET", "") or "",
            )
        else:
            creds = self._creds(channel)
        if not all(creds):
            return False, "X_API_KEY/X_API_SECRET/X_ACCESS_TOKEN/X_ACCESS_SECRET не заданы"
        return True, "X (Twitter), API v2"

    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        ok, detail = self.check(channel)
        if not ok:
            return self._result(post, channel, ok=False, error="X не настроен: {}".format(detail))
        consumer_key, consumer_secret, token, token_secret = self._creds(channel)
        text = post_text(post, MAX_TEXT, channel)
        header = oauth1_header(
            "POST", API_URL, consumer_key, consumer_secret, token, token_secret
        )
        try:
            data = http_json(
                API_URL,
                method="POST",
                payload={"text": text},
                headers={"Authorization": header},
            )
        except SocialAPIError as exc:
            logger.warning("X: публикация не удалась: %s", exc)
            return self._result(post, channel, ok=False, error=str(exc))
        tweet_id = str(((data.get("data") or {}).get("id")) or "")
        if not tweet_id:
            message = str(data.get("detail") or data.get("title") or data)[:200]
            return self._result(post, channel, ok=False, error="X: нет id в ответе: " + message)
        return self._result(
            post,
            channel,
            ok=True,
            external_id=tweet_id,
            url="https://x.com/i/web/status/{}".format(tweet_id),
        )
