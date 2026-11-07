"""Общая база для бесплатных соцсетей-публикаторов (Bluesky, Mastodon, Discord).

Все они — «опциональные» публикаторы: включаются в ``publisher_ids`` канала, но
если креды не заданы в ``.env``, конвейер просто пропускает их (без ошибки) —
см. ``Publisher.optional`` и ``pipeline.publish_post``.

Секреты — только в ``.env``. Для каждого канала можно задать свой аккаунт:
``<BASE>_<CHANNEL_ID>`` (например ``BLUESKY_HANDLE_AI_NEWS``), иначе берётся
общий ``<BASE>``. Это позволяет вести разные каналы с разных аккаунтов.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from ..config import Settings
from ..models import ChannelConfig, GeneratedPost
from ..utils import env, normalize_space, strip_html, truncate
from .base import Publisher

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 25.0
_HANDLE_RE = re.compile(r"@([A-Za-z][A-Za-z0-9_]{3,31})")


class SocialAPIError(RuntimeError):
    """Ошибка API соцсети (сеть, HTTP-статус, error в JSON)."""


def channel_suffix(channel: ChannelConfig) -> str:
    """``tech-ai-es`` → ``TECH_AI_ES`` (для имён переменных окружения)."""
    return re.sub(r"[^A-Za-z0-9]+", "_", str(getattr(channel, "id", ""))).strip("_").upper()


def env_for_channel(channel: ChannelConfig, base: str, default: str = "") -> str:
    """``<BASE>_<CHANNEL>`` → иначе общий ``<BASE>`` → иначе ``default``."""
    specific = env("{}".format(f"{base}_{channel_suffix(channel)}"), "") or ""
    if specific.strip():
        return specific.strip()
    common = env(base, "") or ""
    if common.strip():
        return common.strip()
    return default


def channel_link(channel: ChannelConfig, settings: Optional[Settings] = None) -> str:
    """Публичная ссылка канала.

    Приоритет: ``TELEGRAM_CHANNEL_URL_<CHANNEL>`` → ``public_url`` в конфиге
    канала → ``@username`` в ``telegram_chat_id`` → единственное упоминание
    @username в описании (если упоминаний несколько — ссылка неоднозначна, "").
    """
    link = env_for_channel(channel, "TELEGRAM_CHANNEL_URL", "")
    if link:
        return link
    public_url = str(getattr(channel, "public_url", "") or "").strip()
    if public_url:
        return public_url
    chat_id = str(getattr(channel, "telegram_chat_id", "") or "").strip()
    if chat_id.startswith("@"):
        return f"https://t.me/{chat_id.lstrip('@')}"
    description = str(getattr(channel, "description", "") or "")
    mentions = list(dict.fromkeys(_HANDLE_RE.findall(description)))
    if len(mentions) == 1:
        return f"https://t.me/{mentions[0]}"
    return ""


def post_text(post: GeneratedPost, limit: int, channel: Optional[ChannelConfig] = None) -> str:
    """Текст поста для соцсети: plain-text, без HTML, с ссылкой на канал."""
    plain = normalize_space(strip_html(getattr(post, "text", "") or ""))
    link = channel_link(channel) if channel is not None else ""
    if link:
        reserve = len(link) + 2
        plain = truncate(plain, max(20, limit - reserve), suffix="…")
        return f"{plain}\n\n{link}".strip()
    return truncate(plain, limit, suffix="…")


def http_json(
    url: str,
    method: str = "POST",
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    form: bool = False,
    timeout: float = _HTTP_TIMEOUT,
) -> Dict[str, Any]:
    """JSON-запрос к API соцсети; все сетевые/HTTP-ошибки → SocialAPIError."""
    request_headers = {"Accept": "application/json"}
    body: Optional[bytes] = None
    if payload is not None:
        if form:
            body = urllib.parse.urlencode(payload).encode("utf-8")
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
    if headers:
        request_headers.update({k: v for k, v in headers.items() if v})
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=max(5.0, float(timeout))) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # pragma: no cover - нечитаемое тело
            detail = ""
        raise SocialAPIError(f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise SocialAPIError(f"сеть недоступна: {exc}") from exc
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


class SocialPublisher(Publisher):
    """Опциональный публикатор соцсети: пропускается, если не настроен."""

    optional = True

    def _config(self) -> Dict[str, Any]:
        section = self.settings.publishers.get(self.name, {})
        return section if isinstance(section, dict) else {}

    def _env(self, channel: ChannelConfig, base: str) -> str:
        return env_for_channel(channel, base)

    def configured(self, channel: Optional[ChannelConfig] = None) -> bool:
        return bool(self.check(channel)[0])
