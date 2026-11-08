"""Публикация в Tumblr — бесплатно, OAuth 1.0a (HMAC-SHA1).

Endpoint: ``POST https://api.tumblr.com/v2/blog/<blog>/post`` (``type=text``).

Креды в ``.env``:
    TUMBLR_CONSUMER_KEY / TUMBLR_CONSUMER_SECRET
        ключи OAuth-приложения с https://www.tumblr.com/oauth/apps
    TUMBLR_OAUTH_TOKEN / TUMBLR_OAUTH_TOKEN_SECRET
        токен доступа пользователя: OAuth 1.0a flow
        (request_token → oauth/authorize → access_token)
    TUMBLR_BLOG
        имя блога (например ``vlad-007``); если не задано — берётся основной
        блог аккаунта через ``/v2/user/info``.

Как и остальные соцсети, поддерживает переопределение на канал:
``TUMBLR_BLOG_<CHANNEL_ID>`` (например ``TUMBLR_BLOG_CRYPTO_ES``).

Публикатор опциональный: без кредов конвейер молча пропускает Tumblr.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import logging
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

from ..config import Settings
from ..models import ChannelConfig, GeneratedPost, PublishResult
from .social import SocialAPIError, SocialPublisher, post_text

logger = logging.getLogger(__name__)

API_BASE = "https://api.tumblr.com"
MAX_TEXT = 12000  # Tumblr принимает длинные текстовые посты
_HTTP_TIMEOUT = 25.0
# how many OAuth credentials are required
_CRED_KEYS = (
    "TUMBLR_CONSUMER_KEY",
    "TUMBLR_CONSUMER_SECRET",
    "TUMBLR_OAUTH_TOKEN",
    "TUMBLR_OAUTH_TOKEN_SECRET",
)


def _pct(value: Any) -> str:
    """Percent-encoding по RFC 3986 (OAuth 1.0a)."""
    return urllib.parse.quote(str(value), safe="~")


def _signature(
    method: str,
    url: str,
    params: Dict[str, str],
    consumer_secret: str,
    token_secret: str = "",
) -> str:
    """HMAC-SHA1 подпись для OAuth 1.0a."""
    pairs = sorted((_pct(k), _pct(v)) for k, v in params.items())
    param_string = "&".join(f"{k}={v}" for k, v in pairs)
    base_string = "&".join([method.upper(), _pct(url), _pct(param_string)])
    signing_key = f"{_pct(consumer_secret)}&{_pct(token_secret)}"
    digest = hmac.new(
        signing_key.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha1
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def _auth_header(oauth_params: Dict[str, str], signature: str) -> str:
    parts = [f'{_pct(k)}="{_pct(v)}"' for k, v in oauth_params.items()]
    parts.append(f'oauth_signature="{_pct(signature)}"')
    return "OAuth " + ", ".join(parts)


def _oauth1_request(
    method: str,
    url: str,
    params: Optional[Dict[str, str]] = None,
    *,
    consumer_key: str,
    consumer_secret: str,
    token: str,
    token_secret: str,
    timeout: float = _HTTP_TIMEOUT,
) -> Dict[str, Any]:
    """Подписанный OAuth 1.0a запрос к API Tumblr → разобранный JSON.

    Все сетевые/HTTP-ошибки превращаются в :class:`SocialAPIError`.
    """
    body_params = dict(params or {})
    oauth_params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": str(random.getrandbits(64)),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_version": "1.0",
        "oauth_token": token,
    }
    signature = _signature(
        method,
        url,
        {**oauth_params, **body_params},
        consumer_secret,
        token_secret,
    )
    headers = {
        "Authorization": _auth_header(oauth_params, signature),
        "Accept": "application/json",
    }
    data: Optional[bytes] = None
    if method.upper() == "GET":
        if body_params:
            url = f"{url}?{urllib.parse.urlencode(body_params)}"
    else:
        data = urllib.parse.urlencode(body_params).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(
        url, data=data, headers=headers, method=method.upper()
    )
    try:
        with urllib.request.urlopen(request, timeout=max(5.0, float(timeout))) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # pragma: no cover - нечитаемое тело
            detail = ""
        raise SocialAPIError(f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise SocialAPIError(f"сеть недоступна: {exc}") from exc
    try:
        parsed = json.loads(raw) if raw else {}
    except ValueError as exc:
        raise SocialAPIError(f"некорректный JSON: {raw[:200]}") from exc
    meta = parsed.get("meta") if isinstance(parsed, dict) else None
    if isinstance(meta, dict) and int(meta.get("status") or 0) >= 400:
        raise SocialAPIError(
            "API Tumblr: {} {}".format(meta.get("status"), meta.get("msg") or "")
        )
    return parsed if isinstance(parsed, dict) else {}


class TumblrPublisher(SocialPublisher):
    """Публикатор текстового поста в Tumblr."""

    name = "tumblr"
    optional = True

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._blog_cache: Optional[str] = None

    # ------------------------------------------------------------------
    # Креды / блог
    # ------------------------------------------------------------------
    def _creds(self, channel: Optional[ChannelConfig] = None) -> Dict[str, str]:
        if channel is None:
            from ..utils import env

            return {key: (env(key, "") or "") for key in _CRED_KEYS}
        return {key: self._env(channel, key) for key in _CRED_KEYS}

    def _blog(self, channel: Optional[ChannelConfig] = None) -> str:
        if channel is not None:
            blog = self._env(channel, "TUMBLR_BLOG")
        else:
            from ..utils import env

            blog = (env("TUMBLR_BLOG", "") or "").strip()
        if blog:
            return blog.strip().lstrip("@")
        return self._blog_cache or ""

    def _resolve_primary_blog(self, creds: Dict[str, str]) -> str:
        """Основной блог аккаунта (если TUMBLR_BLOG не задан)."""
        if self._blog_cache:
            return self._blog_cache
        data = _oauth1_request(
            "GET",
            f"{API_BASE}/v2/user/info",
            {},
            consumer_key=creds["TUMBLR_CONSUMER_KEY"],
            consumer_secret=creds["TUMBLR_CONSUMER_SECRET"],
            token=creds["TUMBLR_OAUTH_TOKEN"],
            token_secret=creds["TUMBLR_OAUTH_TOKEN_SECRET"],
        )
        blogs = ((data.get("response") or {}).get("user") or {}).get("blogs") or []
        for blog in blogs:
            if blog.get("primary") or len(blogs) == 1:
                name = str(blog.get("name") or "").strip()
                if name:
                    self._blog_cache = name
                    return name
        raise SocialAPIError("Tumblr: не найден основной блог аккаунта")

    # ------------------------------------------------------------------
    # Publisher API
    # ------------------------------------------------------------------
    def check(self, channel: Optional[ChannelConfig] = None) -> Tuple[bool, str]:
        creds = self._creds(channel)
        missing = [key for key, value in creds.items() if not value]
        if missing:
            return False, "Tumblr не настроен: не заданы " + ", ".join(missing)
        blog = self._blog(channel)
        detail = f"Tumblr: {blog}" if blog else "Tumblr: ключи есть, блог определится автоматически"
        return True, detail

    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        ready, detail = self.check(channel)
        if not ready:
            return self._result(post, channel, ok=False, error=detail)
        creds = self._creds(channel)
        text = post_text(post, MAX_TEXT, channel)
        body_html = html.escape(text).replace("\n", "<br/>\n")
        params = {
            "type": "text",
            "format": "html",
            "state": "published",
            "body": body_html,
        }
        tags = [str(tag).lstrip("#") for tag in (post.hashtags or []) if str(tag).strip()]
        if tags:
            params["tags"] = ",".join(tags)
        try:
            blog = self._blog(channel) or self._resolve_primary_blog(creds)
            data = _oauth1_request(
                "POST",
                f"{API_BASE}/v2/blog/{urllib.parse.quote(blog, safe='')}/post",
                params,
                consumer_key=creds["TUMBLR_CONSUMER_KEY"],
                consumer_secret=creds["TUMBLR_CONSUMER_SECRET"],
                token=creds["TUMBLR_OAUTH_TOKEN"],
                token_secret=creds["TUMBLR_OAUTH_TOKEN_SECRET"],
            )
        except SocialAPIError as exc:
            logger.warning("Tumblr: публикация не удалась: %s", exc)
            return self._result(post, channel, ok=False, error=str(exc))
        response = data.get("response") or {}
        post_id = str(response.get("id") or "")
        if "." in blog:
            url = f"https://{blog}/post/{post_id}"
        else:
            url = f"https://{blog}.tumblr.com/post/{post_id}"
        return self._result(post, channel, ok=True, external_id=post_id, url=url)
