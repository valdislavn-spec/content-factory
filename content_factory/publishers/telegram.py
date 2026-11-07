"""Публикация в Telegram через официальный Bot API (stdlib urllib).

Токен бота берётся из .env/переменных окружения (TELEGRAM_BOT_TOKEN), id
канала — из channel.telegram_chat_id или TELEGRAM_CHAT_ID_<CHANNEL>.
Длинные посты дробятся на несколько сообщений (<= 4096 символов) так, чтобы
HTML-теги не разрывались. Наружу исключения не выходят: ошибки Bot API
возвращаются в PublishResult(ok=False, error=...).
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..config import Settings
from ..models import ChannelConfig, GeneratedPost, PublishResult
from ..utils import env, strip_html
from .base import Publisher, split_html_message

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"


class TelegramAPIError(RuntimeError):
    """Ошибка Telegram Bot API (сеть, HTTP-статус или ok=false)."""


def _extract_description(raw: bytes) -> str:
    """Достаёт человекочитаемое описание ошибки из тела ответа Bot API."""
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except (TypeError, ValueError):
        return raw.decode("utf-8", errors="replace").strip()[:500]
    if isinstance(data, dict):
        return str(data.get("description") or data.get("error") or "").strip()[:500]
    return ""


class TelegramPublisher(Publisher):
    """Публикатор в Telegram-канал через Bot API."""

    name = "telegram"

    # ------------------------------------------------------------------
    # конфигурация
    # ------------------------------------------------------------------
    def _config(self) -> Dict[str, Any]:
        config = self.settings.publishers.get("telegram", {})
        return config if isinstance(config, dict) else {}

    def _token(self) -> str:
        env_name = str(self._config().get("bot_token_env") or "TELEGRAM_BOT_TOKEN")
        return env("{}".format(env_name), "") or ""

    def _chat_id(self, channel: ChannelConfig) -> str:
        chat_id = str(channel.telegram_chat_id or "").strip()
        if chat_id:
            return chat_id
        return str(self.settings.channel_env_chat_id(channel.id) or "").strip()

    @staticmethod
    def _username(chat_id: str) -> str:
        """Публичное имя канала для ссылки t.me, если chat_id задан как @username."""
        chat_id = (chat_id or "").strip()
        if chat_id.startswith("@"):
            return chat_id[1:]
        return ""

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------
    def _call(self, method: str, payload: Dict[str, Any]) -> Any:
        token = self._token()
        if not token:
            raise TelegramAPIError(
                "Не задан токен Telegram-бота (TELEGRAM_BOT_TOKEN). "
                "Создайте бота у @BotFather и заполните .env."
            )
        # TELEGRAM_API_BASE — релей вместо прямого api.telegram.org (например,
        # Pipedream HTTP-trigger), если Telegram блокируется сетью. К базовому
        # URL по-прежнему добавляется /bot<token>/<method>.
        base = str(env("TELEGRAM_API_BASE", "") or self._config().get("api_base") or API_BASE)
        url = "{}/bot{}/{}".format(base.rstrip("/"), token, method)
        body = urllib.parse.urlencode({k: v for k, v in payload.items() if v is not None}).encode(
            "utf-8"
        )
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": self.settings.user_agent or "ContentFactory/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.request_timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read()
            except Exception:  # noqa: BLE001 - тело ошибки может быть недоступно
                raw = b""
            description = _extract_description(raw) or "HTTP {} {}".format(exc.code, exc.reason)
            raise TelegramAPIError("Telegram Bot API: {}".format(description)) from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise TelegramAPIError("Сетевая ошибка Telegram Bot API: {}".format(exc)) from exc

        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise TelegramAPIError("Некорректный ответ Telegram Bot API") from exc
        if not isinstance(data, dict):
            raise TelegramAPIError("Неожиданный формат ответа Telegram Bot API")
        if not data.get("ok"):
            raise TelegramAPIError(
                "Telegram Bot API: {}".format(
                    data.get("description") or "ответ ok=false без описания"
                )
            )
        return data.get("result")

    def _call_multipart(
        self,
        method: str,
        fields: Dict[str, Any],
        files: Dict[str, Tuple[str, bytes]],
    ) -> Any:
        """POST multipart/form-data (нужен для sendPhoto с локальным файлом)."""
        token = self._token()
        if not token:
            raise TelegramAPIError("Не задан токен Telegram-бота (TELEGRAM_BOT_TOKEN).")
        base = str(env("TELEGRAM_API_BASE", "") or self._config().get("api_base") or API_BASE)
        url = "{}/bot{}/{}".format(base.rstrip("/"), token, method)
        boundary = "----ContentFactory{}".format(uuid.uuid4().hex)
        body = bytearray()
        for key, value in fields.items():
            if value is None:
                continue
            body += (
                "--{}\r\nContent-Disposition: form-data; name=\"{}\"\r\n\r\n{}\r\n".format(
                    boundary, key, value
                )
            ).encode("utf-8")
        for key, (filename, content) in files.items():
            body += (
                "--{}\r\nContent-Disposition: form-data; name=\"{}\"; filename=\"{}\"\r\n"
                "Content-Type: application/octet-stream\r\n\r\n".format(boundary, key, filename)
            ).encode("utf-8")
            body += content
            body += b"\r\n"
        body += "--{}--\r\n".format(boundary).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=bytes(body),
            headers={
                "Content-Type": "multipart/form-data; boundary={}".format(boundary),
                "User-Agent": self.settings.user_agent or "ContentFactory/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.request_timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read()
            except Exception:  # noqa: BLE001
                raw = b""
            description = _extract_description(raw) or "HTTP {} {}".format(exc.code, exc.reason)
            raise TelegramAPIError("Telegram Bot API: {}".format(description)) from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise TelegramAPIError("Сетевая ошибка Telegram Bot API: {}".format(exc)) from exc

        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise TelegramAPIError("Некорректный ответ Telegram Bot API") from exc
        if not isinstance(data, dict):
            raise TelegramAPIError("Неожиданный формат ответа Telegram Bot API")
        if not data.get("ok"):
            raise TelegramAPIError(
                "Telegram Bot API: {}".format(data.get("description") or "ответ ok=false без описания")
            )
        return data.get("result")

    # ------------------------------------------------------------------
    # публикация
    # ------------------------------------------------------------------
    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        # Страховка: при settings.dry_run даже прямой вызов не должен слать в сеть.
        if settings.dry_run:
            return self.dry_run_publisher().publish(post, channel, settings)
        try:
            token = self._token()
            if not token:
                return self._result(
                    post,
                    channel,
                    ok=False,
                    error=(
                        "Не задан токен Telegram-бота (TELEGRAM_BOT_TOKEN). "
                        "Заполните .env или включите dry_run."
                    ),
                )
            chat_id = self._chat_id(channel)
            if not chat_id:
                return self._result(
                    post,
                    channel,
                    ok=False,
                    error=(
                        "Не задан chat_id канала {}: заполните telegram_chat_id "
                        "или TELEGRAM_CHAT_ID_{} в .env".format(
                            channel.id,
                            "".join(ch if ch.isalnum() else "_" for ch in channel.id).upper(),
                        )
                    ),
                )

            parts = split_html_message(post.text)
            if not parts:
                return self._result(
                    post,
                    channel,
                    ok=False,
                    error="Пост пустой — отправлять нечего",
                )
            config = self._config()
            parse_mode = str(config.get("parse_mode") or "HTML")
            disable_preview = bool(config.get("disable_preview", False))
            # Сначала — фирменная фото-карточка (Playfair Display + Inter),
            # сгенерированная пайплайном. Если её нет/не удалось загрузить,
            # работаем как раньше: картинка статьи или текст.
            card_message_id = ""
            card_path = str((post.meta or {}).get("card_path") or "").strip()
            if card_path and Path(card_path).is_file():
                try:
                    caption = (
                        parts[0]
                        if len(parts) == 1 and len(strip_html(parts[0])) <= 1000
                        else ""
                    )
                    fields: Dict[str, Any] = {"chat_id": chat_id, "parse_mode": parse_mode}
                    if caption:
                        fields["caption"] = caption
                    photo_result = self._call_multipart(
                        "sendPhoto",
                        fields,
                        {"photo": (Path(card_path).name, Path(card_path).read_bytes())},
                    )
                    message_id = ""
                    if isinstance(photo_result, dict):
                        message_id = str(photo_result.get("message_id") or "")
                    username = self._username(chat_id)
                    url = (
                        "https://t.me/{}/{}".format(username, message_id)
                        if username and message_id
                        else ""
                    )
                    if caption:
                        logger.info(
                            "Telegram: пост %s канала %s опубликован карточкой (id=%s)",
                            post.id,
                            channel.id,
                            message_id or "-",
                        )
                        return self._result(post, channel, ok=True, external_id=message_id, url=url)
                    card_message_id = message_id
                    logger.info(
                        "Telegram: карточка поста %s канала %s загружена (id=%s), далее текст",
                        post.id,
                        channel.id,
                        message_id or "-",
                    )
                except Exception as exc:  # noqa: BLE001 - карточка не должна срывать пост
                    logger.warning(
                        "Telegram: карточка поста %s не загрузилась (%s) — отправляю текст",
                        post.id,
                        exc,
                    )

            image_url = str((post.meta or {}).get("image_url") or "").strip()
            caption_ok = (
                image_url.startswith(("http://", "https://"))
                and len(parts) == 1
                and len(strip_html(parts[0])) <= 1000
            )
            if caption_ok and not card_message_id:
                try:
                    photo_result = self._call(
                        "sendPhoto",
                        {
                            "chat_id": chat_id,
                            "photo": image_url,
                            "caption": parts[0],
                            "parse_mode": parse_mode,
                        },
                    )
                    message_id = ""
                    if isinstance(photo_result, dict):
                        message_id = str(photo_result.get("message_id") or "")
                    username = self._username(chat_id)
                    url = (
                        "https://t.me/{}/{}".format(username, message_id)
                        if username and message_id
                        else ""
                    )
                    logger.info(
                        "Telegram: пост %s канала %s опубликован фото-карточкой (id=%s)",
                        post.id,
                        channel.id,
                        message_id or "-",
                    )
                    return self._result(
                        post, channel, ok=True, external_id=message_id, url=url
                    )
                except TelegramAPIError as exc:
                    logger.warning(
                        "Telegram: sendPhoto не удался (%s) — отправляю текстом", exc
                    )

            message_ids: List[str] = [card_message_id] if card_message_id else []
            for index, part in enumerate(parts, start=1):
                try:
                    result = self._call(
                        "sendMessage",
                        {
                            "chat_id": chat_id,
                            "text": part,
                            "parse_mode": parse_mode,
                            "disable_web_page_preview": "true" if disable_preview else "false",
                        },
                    )
                except TelegramAPIError as exc:
                    sent = len(message_ids)
                    prefix = (
                        "Отправлено {}/{} частей, затем ошибка: ".format(sent, len(parts))
                        if sent
                        else ""
                    )
                    logger.warning(
                        "Telegram: канал %s, пост %s, часть %s/%s: %s",
                        channel.id,
                        post.id,
                        index,
                        len(parts),
                        exc,
                    )
                    return self._result(
                        post,
                        channel,
                        ok=False,
                        external_id=message_ids[0] if message_ids else "",
                        error="{}{}".format(prefix, exc),
                    )
                message_id = ""
                if isinstance(result, dict) and result.get("message_id") is not None:
                    message_id = str(result.get("message_id"))
                message_ids.append(message_id)

            username = self._username(chat_id)
            url = ""
            if username and message_ids and message_ids[0]:
                url = "https://t.me/{}/{}".format(username, message_ids[0])
            logger.info(
                "Telegram: пост %s канала %s опубликован (%s частей, id=%s)",
                post.id,
                channel.id,
                len(parts),
                message_ids[-1] if message_ids else "-",
            )
            return self._result(
                post,
                channel,
                ok=True,
                external_id=message_ids[-1] if message_ids else "",
                url=url,
            )
        except Exception as exc:  # noqa: BLE001 - публикатор не падает наружу
            logger.exception("Telegram: непредвиденная ошибка публикации поста %s", post.id)
            return self._result(
                post,
                channel,
                ok=False,
                error="Непредвиденная ошибка Telegram: {}".format(exc),
            )

    # ------------------------------------------------------------------
    # проверка
    # ------------------------------------------------------------------
    def check(self) -> Tuple[bool, str]:
        token = self._token()
        if not token:
            return (
                False,
                "Не задан токен Telegram-бота: TELEGRAM_BOT_TOKEN (см. .env.example)",
            )
        try:
            result = self._call("getMe", {})
        except TelegramAPIError as exc:
            return False, "Telegram Bot API недоступен: {}".format(exc)
        if isinstance(result, dict):
            username = str(result.get("username") or "").strip()
            if username:
                return True, "Бот @{} доступен, токен принят".format(username)
        return True, "Токен принят Telegram Bot API"
