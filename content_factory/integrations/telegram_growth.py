"""Telegram-нативные механики роста: deep links, inline mode, /start-атрибуция.

Бесплатный контур продвижения (см. docs/free-promo-apis.md):
    * deep link ``https://t.me/<bot>?start=<payload>`` — атрибуция источника;
    * inline mode (``answerInlineQuery``) — бот раздаёт посты канала в чужих чатах;
    * ``switch_inline_query`` кнопки в постах — читатель сам делится постом;
    * ``/start <payload>`` → запись growth-события в SQLite и кнопка «Открыть канал».

Модуль не делает сети: чистые функции ``plan_update_actions``/``build_inline_results``
возвращают готовые вызовы Bot API, а ``TelegramGrowthBot`` их выполняет.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..config import Settings
from ..models import ChannelConfig
from ..publishers.social import channel_link
from ..storage import Storage
from ..utils import env, normalize_space, strip_html, truncate

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
MAX_PAYLOAD = 64
_PAYLOAD_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_PAYLOAD_SEP = "__"
_MAX_INLINE_RESULTS = 50


class TelegramGrowthError(RuntimeError):
    """Ошибка Bot API / конфигурации growth-бота."""


# ---------------------------------------------------------------------------
# deep links и payload
# ---------------------------------------------------------------------------


def payload_channel(channel_id: str) -> str:
    """``tech-ai-es`` → ``tech_ai_es`` (обратимо: '_' → '-')."""
    return re.sub(r"[^A-Za-z0-9]+", "_", str(channel_id or "")).strip("_")


def channel_from_payload_part(part: str) -> str:
    return str(part or "").replace("_", "-")


def make_payload(channel_id: str, slot: str = "", post_id: str = "") -> str:
    """payload для ``?start=``: ``<channel>__<slot>__<post8>`` (≤64 символов)."""
    channel = payload_channel(channel_id)
    slot_part = re.sub(r"[^A-Za-z0-9]+", "", str(slot or ""))
    post_part = re.sub(r"[^A-Za-z0-9]+", "", str(post_id or ""))[:8]
    parts = [channel]
    if slot_part or post_part:
        parts.extend([slot_part or "0", post_part or "0"])
    payload = _PAYLOAD_SEP.join(parts)
    if len(payload) > MAX_PAYLOAD:
        payload = payload[:MAX_PAYLOAD]
    return payload


def parse_payload(payload: str) -> Optional[Dict[str, str]]:
    """Разбирает payload ``/start``; None — если формат не наш."""
    text = str(payload or "").strip()
    if not text or not _PAYLOAD_RE.match(text):
        return None
    parts = text.split(_PAYLOAD_SEP)
    channel_id = channel_from_payload_part(parts[0])
    if not channel_id:
        return None
    return {
        "channel_id": channel_id,
        "slot": parts[1] if len(parts) > 1 else "",
        "post_id": parts[2] if len(parts) > 2 else "",
        "raw": text,
    }


def start_link(bot_username: str, channel_id: str, slot: str = "", post_id: str = "") -> str:
    """Ссылка ``t.me/<bot>?start=...`` для канала/слота/поста."""
    bot = str(bot_username or "").strip().lstrip("@")
    if not bot:
        raise TelegramGrowthError("не задан username бота (TELEGRAM_GROWTH_BOT_USERNAME)")
    payload = make_payload(channel_id, slot=slot, post_id=post_id)
    return f"https://t.me/{bot}?start={payload}"


# ---------------------------------------------------------------------------
# inline mode
# ---------------------------------------------------------------------------


def build_inline_results(
    posts: Sequence[Dict[str, Any]],
    channel_url: str,
    *,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Собирает inline-результаты (article) из последних постов канала."""
    results: List[Dict[str, Any]] = []
    for item in list(posts)[: max(1, min(limit, _MAX_INLINE_RESULTS))]:
        text = normalize_space(strip_html(str(item.get("text") or "")))
        if not text:
            continue
        title = truncate(text, 60, suffix="…")
        description = truncate(text, 120, suffix="…")
        post_id = str(item.get("post_id") or item.get("id") or "post")
        message_text = truncate(text, 3500, suffix="…")
        if channel_url:
            message_text = f"{message_text}\n\n{channel_url}"
        results.append(
            {
                "type": "article",
                "id": f"cf-{post_id}"[:60],
                "title": title,
                "description": description,
                "url": channel_url or "https://t.me",
                "input_message_content": {
                    "message_text": message_text,
                    "disable_web_page_preview": False,
                },
            }
        )
    return results


# ---------------------------------------------------------------------------
# обработка update'ов (чистые функции — легко тестировать)
# ---------------------------------------------------------------------------


def build_start_actions(
    payload: str,
    user_id: Any,
    storage: Storage,
    channels: Sequence[ChannelConfig],
    settings: Optional[Settings] = None,
) -> List[Dict[str, Any]]:
    """``/start <payload>``: записать событие и отправить кнопку на канал."""
    parsed = parse_payload(payload)
    channel = None
    if parsed is not None:
        channel = next((c for c in channels if c.id == parsed["channel_id"]), None)
    channel_id = parsed["channel_id"] if parsed else ""
    storage.save_growth_event(
        "start",
        channel_id=channel_id,
        payload=str(payload or ""),
        user_id=str(user_id or ""),
        source="deep_link",
    )
    link = channel_link(channel, settings) if channel is not None else ""
    if channel is not None and not link:
        link = ""
    text = "Открывайте канал и подписывайтесь:"
    if channel is not None:
        text = f"Канал «{channel.title}» — подписывайтесь:"
    actions: List[Dict[str, Any]] = [
        {
            "method": "sendMessage",
            "payload": {
                "chat_id": user_id,
                "text": text,
                "parse_mode": "HTML",
                **(
                    {
                        "reply_markup": {
                            "inline_keyboard": [[{"text": "Открыть канал", "url": link}]]
                        }
                    }
                    if link
                    else {}
                ),
            },
        }
    ]
    return actions


def build_inline_actions(
    inline_query: Dict[str, Any],
    storage: Storage,
    channels: Sequence[ChannelConfig],
    settings: Optional[Settings] = None,
) -> List[Dict[str, Any]]:
    """``inline_query`` → ``answerInlineQuery`` с постами последнего канала."""
    query = str(inline_query.get("query") or "").strip().lower()
    channel = channels[0] if channels else None
    for candidate in channels:
        if candidate.id in query or candidate.title.lower() in query:
            channel = candidate
            break
    posts: List[Dict[str, Any]] = []
    if channel is not None:
        posts = storage.get_posts(channel.id, days=14, limit=10)
        storage.save_growth_event(
            "inline",
            channel_id=channel.id,
            payload=query[:64],
            user_id=str((inline_query.get("from") or {}).get("id") or ""),
            source="inline_mode",
        )
    results = build_inline_results(posts, channel_link(channel, settings) if channel else "")
    return [
        {
            "method": "answerInlineQuery",
            "payload": {
                "inline_query_id": inline_query.get("id"),
                "results": results,
                "cache_time": 300,
                "is_personal": False,
            },
        }
    ]


def plan_update_actions(
    update: Dict[str, Any],
    storage: Storage,
    channels: Sequence[ChannelConfig],
    settings: Optional[Settings] = None,
) -> List[Dict[str, Any]]:
    """Планирует вызовы Bot API по одному update (без сети)."""
    message = update.get("message") or {}
    text = str(message.get("text") or "")
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        payload = parts[1].strip() if len(parts) > 1 else ""
        user_id = (message.get("from") or {}).get("id")
        return build_start_actions(payload, user_id, storage, channels, settings)
    inline_query = update.get("inline_query")
    if inline_query:
        return build_inline_actions(inline_query, storage, channels, settings)
    return []


# ---------------------------------------------------------------------------
# long-polling бот
# ---------------------------------------------------------------------------


class TelegramGrowthBot:
    """Long-polling бот для deep links и inline mode (stdlib urllib)."""

    def __init__(
        self,
        token: str,
        bot_username: str,
        storage: Storage,
        channels: Sequence[ChannelConfig],
        settings: Optional[Settings] = None,
        *,
        api_base: str = API_BASE,
        timeout: float = 25.0,
    ) -> None:
        if not token:
            raise TelegramGrowthError("не задан TELEGRAM_BOT_TOKEN")
        self.token = token
        self.bot_username = str(bot_username or "").lstrip("@")
        self.storage = storage
        self.channels = list(channels)
        self.settings = settings
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout
        self.offset = 0

    def _api(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.api_base}/bot{self.token}/{method}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise TelegramGrowthError(f"HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TelegramGrowthError(f"Bot API недоступен: {exc}") from exc
        try:
            data = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def poll_once(self, timeout: int = 25) -> int:
        """Один цикл getUpdates: обрабатывает новые update'ы, возвращает число."""
        data = self._api(
            "getUpdates",
            {"offset": self.offset, "timeout": timeout, "allowed_updates": ["message", "inline_query"]},
        )
        updates = data.get("result") or []
        processed = 0
        for update in updates:
            if isinstance(update, dict) and update.get("update_id"):
                self.offset = max(self.offset, int(update["update_id"]) + 1)
            try:
                actions = plan_update_actions(update, self.storage, self.channels, self.settings)
            except Exception as exc:  # update не должен ронять бота
                logger.warning("Growth-бот: ошибка обработки update: %s", exc)
                continue
            for action in actions:
                try:
                    self._api(action["method"], action["payload"])
                    processed += 1
                except TelegramGrowthError as exc:
                    logger.warning("Growth-бот: %s не выполнен: %s", action["method"], exc)
        return processed
