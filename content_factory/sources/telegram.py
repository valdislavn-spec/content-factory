"""Адаптер Telegram-каналов через Telethon.

Telethon — необязательная зависимость (``requirements-optional.txt``),
поэтому импорт выполняется лениво внутри метода. Без установленного Telethon
или без ключей ``TG_API_ID``/``TG_API_HASH`` адаптер бросает понятную
``FetchError`` с инструкцией, а не падает при импорте пакета.
"""
from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Optional

from ..config import Settings
from ..models import Article, SourceConfig, utcnow
from ..utils import FetchError, env, normalize_space, parse_datetime
from .base import SourceAdapter, build_article, clean_title, make_summary

DEFAULT_LIMIT = 30
_ALLOWED_HOSTS = {"t.me", "telegram.me", "www.t.me", "www.telegram.me"}


def _positive_int(value: Any, default: int, minimum: int = 1, maximum: int = 200) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


class TelegramAdapter(SourceAdapter):
    """Адаптер публичных Telegram-каналов (чтение последних сообщений).

    Поддерживаемые options:
      * ``limit`` — сколько последних сообщений прочитать (по умолчанию 30).
    """

    type = "telegram"

    def _probe_options(self) -> Dict[str, Any]:
        return {"limit": 1}

    def fetch(self, source: SourceConfig, settings: Settings) -> List[Article]:
        username = channel_username(source.url)
        api_id, api_hash = telegram_credentials()
        limit = _positive_int((source.options or {}).get("limit"), DEFAULT_LIMIT)
        client = self._create_client(api_id, api_hash, self._session_path(settings))
        messages = self._download_messages(client, username, limit)

        articles: List[Article] = []
        for message in messages:
            article = self._message_to_article(message, source, settings, username)
            if article is not None:
                articles.append(article)
        return articles

    # ------------------------------------------------------------------
    # Telethon: ленивый импорт и точка подмены для тестов
    # ------------------------------------------------------------------
    def _create_client(self, api_id: int, api_hash: str, session: str) -> Any:
        """Создаёт клиент Telethon (в тестах метод подменяется моком)."""
        try:
            from telethon.sync import TelegramClient
        except ImportError as exc:
            raise FetchError(
                "Для Telegram-источников нужен Telethon. Установите необязательные "
                "зависимости: python -m pip install -r requirements-optional.txt"
            ) from exc
        return TelegramClient(session, api_id, api_hash)

    def _download_messages(self, client: Any, username: str, limit: int) -> List[Any]:
        """Читает последние сообщения канала, приводя ошибки к FetchError."""
        try:
            if hasattr(client, "__enter__"):
                with client:
                    return list(client.get_messages(username, limit=limit) or [])
            return list(client.get_messages(username, limit=limit) or [])
        except FetchError:
            raise
        except Exception as exc:
            raise FetchError(
                f"Не удалось прочитать Telegram-канал @{username}: {exc}. "
                "Проверьте TG_API_ID/TG_API_HASH/TG_SESSION и доступность канала."
            ) from exc

    @staticmethod
    def _session_path(settings: Settings) -> str:
        """Путь к файлу сессии Telethon (секрет, в git не попадает)."""
        configured = env("TG_SESSION")
        if configured:
            return configured
        try:
            return str(settings.data_dir / "telegram_sources")
        except Exception:  # pragma: no cover - на случай нестандартных настроек
            return "telegram_sources"

    @staticmethod
    def _message_to_article(
        message: Any,
        source: SourceConfig,
        settings: Settings,
        username: str,
    ) -> Optional[Article]:
        """Преобразует сообщение Telethon в Article; служебные — пропускает."""
        if getattr(message, "action", None) is not None:
            return None
        raw_text = getattr(message, "text", None) or getattr(message, "message", "") or ""
        if not isinstance(raw_text, str):
            return None
        text = normalize_space(raw_text)
        if not text:
            return None
        message_id = getattr(message, "id", None)
        if message_id is None:
            return None
        url = f"https://t.me/{username}/{message_id}"
        title = ""
        for line in raw_text.splitlines():
            line = normalize_space(line)
            if line:
                title = line
                break
        title = clean_title(title or text, 160)
        if not title:
            return None
        published_at = parse_datetime(getattr(message, "date", None)) or utcnow()
        return build_article(
            source=source,
            settings=settings,
            url=url,
            title=title,
            published_at=published_at,
            text=text,
            summary=make_summary(text),
            meta={
                "username": username,
                "message_id": message_id,
                "channel_url": source.url,
            },
        )


def channel_username(url: str) -> str:
    """Достаёт username публичного канала из ссылки t.me/<username>."""
    raw = (url or "").strip()
    if not raw:
        raise FetchError("Telegram-источник: пустой url (ожидается https://t.me/channel)")
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parsed = urllib.parse.urlsplit(raw)
    except ValueError as exc:
        raise FetchError(f"Telegram-источник: некорректная ссылка {url!r}") from exc
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_HOSTS:
        raise FetchError(f"Telegram-источник: ожидается ссылка t.me/<канал>, получено {url!r}")
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        raise FetchError(f"Telegram-источник: в ссылке {url!r} нет имени канала")
    if parts[0] in ("joinchat", "addstickers", "share", "proxy") or parts[0].startswith("+"):
        raise FetchError(
            "Telegram-источник: поддерживаются только публичные каналы вида "
            "https://t.me/<username> (приватные каналы недоступны без аккаунта-участника)"
        )
    if parts[0] == "s" and len(parts) > 1:
        return parts[1].lstrip("@")
    username = parts[0].lstrip("@")
    if not username:
        raise FetchError(f"Telegram-источник: в ссылке {url!r} нет имени канала")
    return username


def telegram_credentials() -> Any:
    """Читает TG_API_ID/TG_API_HASH из окружения и валидирует их."""
    api_id_raw = env("TG_API_ID")
    api_hash = env("TG_API_HASH")
    if not api_id_raw or not api_hash:
        raise FetchError(
            "Не заданы TG_API_ID и/или TG_API_HASH. Получите их бесплатно на "
            "https://my.telegram.org и пропишите в .env (см. .env.example). "
            "Без ключей Telegram-источники отключаются, остальные работают."
        )
    try:
        api_id = int(str(api_id_raw).strip())
    except (TypeError, ValueError) as exc:
        raise FetchError(f"TG_API_ID должен быть числом, получено {api_id_raw!r}") from exc
    return api_id, str(api_hash).strip()


__all__ = ["TelegramAdapter", "channel_username", "telegram_credentials", "DEFAULT_LIMIT"]
