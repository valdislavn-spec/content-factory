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
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..affiliate_inject import maybe_inject
from ..config import Settings
from ..models import ChannelConfig, GeneratedPost, PublishResult
from ..utils import env, strip_html
from .base import Publisher, split_html_message

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"


class TelegramAPIError(RuntimeError):
    """Ошибка Telegram Bot API (сеть, HTTP-статус или ok=false)."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


def _extract_description(raw: bytes) -> str:
    """Достаёт человекочитаемое описание ошибки из тела ответа Bot API."""
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except (TypeError, ValueError):
        return raw.decode("utf-8", errors="replace").strip()[:500]
    if isinstance(data, dict):
        return str(data.get("description") or data.get("error") or "").strip()[:500]
    return ""


def _is_parse_entities_error(exc: Exception) -> bool:
    """Telegram не смог разобрать HTML/Markdown разметку сообщения."""
    message = str(exc).lower()
    return "parse entities" in message or "can't parse entities" in message


def _is_retryable_error(exc: TelegramAPIError) -> bool:
    """Повторяем только явно временные ответы Telegram."""
    return getattr(exc, "status_code", None) in {429, 500, 502, 503, 504}


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
    def _retry_attempts(self) -> int:
        raw = self._config().get("retry_attempts", 3)
        try:
            return max(1, min(5, int(raw)))
        except (TypeError, ValueError):
            return 3

    @staticmethod
    def _retry_delay(exc: TelegramAPIError, attempt: int) -> float:
        retry_after = getattr(exc, "retry_after", None)
        if retry_after is not None:
            try:
                return min(10.0, max(0.0, float(retry_after)))
            except (TypeError, ValueError):
                pass
        return min(10.0, float(2 ** (attempt - 1)))

    def _call(self, method: str, payload: Dict[str, Any]) -> Any:
        attempts = self._retry_attempts()
        for attempt in range(1, attempts + 1):
            try:
                return self._call_once(method, payload)
            except TelegramAPIError as exc:
                if attempt >= attempts or not _is_retryable_error(exc):
                    raise
                delay = self._retry_delay(exc, attempt)
                logger.warning(
                    "Telegram: временная ошибка %s — повтор %s/%s через %.1f с",
                    exc,
                    attempt + 1,
                    attempts,
                    delay,
                )
                time.sleep(delay)
        raise AssertionError("unreachable")

    def _call_multipart(
        self,
        method: str,
        fields: Dict[str, Any],
        files: Dict[str, Tuple[str, bytes]],
    ) -> Any:
        attempts = self._retry_attempts()
        for attempt in range(1, attempts + 1):
            try:
                return self._call_multipart_once(method, fields, files)
            except TelegramAPIError as exc:
                if attempt >= attempts or not _is_retryable_error(exc):
                    raise
                delay = self._retry_delay(exc, attempt)
                logger.warning(
                    "Telegram: временная ошибка %s — повтор %s/%s через %.1f с",
                    exc,
                    attempt + 1,
                    attempts,
                    delay,
                )
                time.sleep(delay)
        raise AssertionError("unreachable")

    def _call_once(self, method: str, payload: Dict[str, Any]) -> Any:
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
            raise TelegramAPIError(
                "Telegram Bot API: {}".format(description), status_code=exc.code
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise TelegramAPIError("Сетевая ошибка Telegram Bot API: {}".format(exc)) from exc

        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise TelegramAPIError("Некорректный ответ Telegram Bot API") from exc
        if not isinstance(data, dict):
            raise TelegramAPIError("Неожиданный формат ответа Telegram Bot API")
        if not data.get("ok"):
            parameters = data.get("parameters") if isinstance(data.get("parameters"), dict) else {}
            retry_after = parameters.get("retry_after")
            raise TelegramAPIError(
                "Telegram Bot API: {}".format(
                    data.get("description") or "ответ ok=false без описания"
                ),
                status_code=data.get("error_code"),
                retry_after=retry_after,
            )
        return data.get("result")

    def _call_multipart_once(
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
            raise TelegramAPIError(
                "Telegram Bot API: {}".format(description), status_code=exc.code
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise TelegramAPIError("Сетевая ошибка Telegram Bot API: {}".format(exc)) from exc

        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise TelegramAPIError("Некорректный ответ Telegram Bot API") from exc
        if not isinstance(data, dict):
            raise TelegramAPIError("Неожиданный формат ответа Telegram Bot API")
        if not data.get("ok"):
            parameters = data.get("parameters") if isinstance(data.get("parameters"), dict) else {}
            raise TelegramAPIError(
                "Telegram Bot API: {}".format(
                    data.get("description") or "ответ ok=false без описания"
                ),
                status_code=data.get("error_code"),
                retry_after=parameters.get("retry_after"),
            )
        return data.get("result")

    # ------------------------------------------------------------------
    # публикация
    # ------------------------------------------------------------------

    def _send_text(
        self,
        chat_id: str,
        text: str,
        parse_mode: str,
        disable_preview: bool,
    ) -> Any:
        """Отправляет текст; при битой разметке повторяет без parse_mode.

        LLM иногда возвращает незакрытый тег (например, ``<b>`` без ``</b>``).
        Telegram отклоняет такое сообщение целиком, поэтому для доставки
        используем безопасный plain-text fallback, а не теряем пост.
        """
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": "true" if disable_preview else "false",
        }
        try:
            return self._call("sendMessage", payload)
        except TelegramAPIError as exc:
            if not parse_mode or not _is_parse_entities_error(exc):
                raise
            plain = strip_html(text)
            if not plain:
                raise
            logger.warning(
                "Telegram: не удалось разобрать разметку (%s) — отправляю простым текстом",
                exc,
            )
            payload["text"] = plain
            payload.pop("parse_mode", None)
            return self._call("sendMessage", payload)

    @staticmethod
    def _card_reply_markup(post: Any, channel: Any) -> str:
        """Инлайн-кнопка под фото: источник статьи, иначе — сам канал.

        Картинка кликнуть нельзя, поэтому ссылка выносится в кнопку Telegram.
        """
        language = str(getattr(channel, "language", "en") or "en")
        label = {"en": "Read the source", "es": "Leer la fuente", "ru": "Открыть источник"}.get(
            language, "Read the source"
        )
        candidates: List[str] = []
        for blob in (getattr(post, "html", "") or "", getattr(post, "text", "") or ""):
            candidates.extend(re.findall(r'href="(https?://[^"]+)"', blob))
            candidates.extend(re.findall(r"(?<![\w@])(https?://[^\s<]+)", blob))
        source = next(
            (url for url in candidates if "t.me/" not in url and not url.endswith((".jpg", ".png"))),
            "",
        )
        if not source:
            source = str(getattr(channel, "public_url", "") or "").strip()
            label = {"en": "Open the channel", "es": "Abrir el canal", "ru": "Открыть канал"}.get(
                language, "Open the channel"
            )
        if not source:
            return ""
        return json.dumps(
            {"inline_keyboard": [[{"text": label, "url": source}]]},
            ensure_ascii=False,
        )

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

            post_text = post.text
            # Партнёрский блок в каждый N-й автопост канала (config/affiliates.yaml).
            # Сбой affiliate-реестра не должен ронять публикацию.
            try:
                post_text, affiliate_meta = maybe_inject(post_text, channel.id)
            except Exception:  # noqa: BLE001 - защитный барьер вокруг affiliate
                logger.exception("affiliate: не удалось добавить блок в канал %s", channel.id)
                affiliate_meta = None
            if affiliate_meta:
                post.meta = {**(post.meta or {}), "affiliate": affiliate_meta}
                logger.info("affiliate: блок %s в %s (пост #%s)", affiliate_meta["program"], channel.id, affiliate_meta["index"])
            parts = split_html_message(post_text)
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
                    markup = self._card_reply_markup(post, channel)
                    if markup:
                        fields["reply_markup"] = markup
                    photo_bytes = {"photo": (Path(card_path).name, Path(card_path).read_bytes())}
                    try:
                        photo_result = self._call_multipart("sendPhoto", fields, photo_bytes)
                    except TelegramAPIError as exc:
                        if not caption or not _is_parse_entities_error(exc):
                            raise
                        logger.warning(
                            "Telegram: подпись карточки содержит битую разметку (%s) — "
                            "отправляю её простым текстом",
                            exc,
                        )
                        fields["caption"] = strip_html(caption)
                        fields.pop("parse_mode", None)
                        photo_result = self._call_multipart("sendPhoto", fields, photo_bytes)
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
            photo_file_id = str((post.meta or {}).get("photo_file_id") or "").strip()
            # photo_file_id — фото, загруженное рекламодателем в бота; image_url —
            # картинка статьи. Оба отправляются через sendPhoto.
            photo_ref = photo_file_id or image_url
            photo_ok = bool(photo_file_id) or image_url.startswith(("http://", "https://"))
            caption_ok = (
                photo_ok
                and len(parts) == 1
                and len(strip_html(parts[0])) <= 1000
            )
            if photo_ok and not card_message_id:
                try:
                    fields: Dict[str, Any] = {
                        "chat_id": chat_id,
                        "photo": photo_ref,
                        "parse_mode": parse_mode,
                    }
                    if caption_ok:
                        fields["caption"] = parts[0]
                    try:
                        photo_result = self._call("sendPhoto", fields)
                    except TelegramAPIError as exc:
                        if not caption_ok or not _is_parse_entities_error(exc):
                            raise
                        logger.warning(
                            "Telegram: подпись фото содержит битую разметку (%s) — "
                            "отправляю её простым текстом",
                            exc,
                        )
                        fields["caption"] = strip_html(parts[0])
                        fields.pop("parse_mode", None)
                        photo_result = self._call("sendPhoto", fields)
                    message_id = ""
                    if isinstance(photo_result, dict):
                        message_id = str(photo_result.get("message_id") or "")
                    username = self._username(chat_id)
                    url = (
                        "https://t.me/{}/{}".format(username, message_id)
                        if username and message_id
                        else ""
                    )
                    if caption_ok:
                        logger.info(
                            "Telegram: пост %s канала %s опубликован фото-карточкой (id=%s)",
                            post.id,
                            channel.id,
                            message_id or "-",
                        )
                        return self._result(
                            post, channel, ok=True, external_id=message_id, url=url
                        )
                    card_message_id = message_id
                    logger.info(
                        "Telegram: фото поста %s канала %s загружено (id=%s), далее текст",
                        post.id,
                        channel.id,
                        message_id or "-",
                    )
                except TelegramAPIError as exc:
                    logger.warning(
                        "Telegram: sendPhoto не удался (%s) — отправляю текстом", exc
                    )

            message_ids: List[str] = [card_message_id] if card_message_id else []
            for index, part in enumerate(parts, start=1):
                try:
                    result = self._send_text(chat_id, part, parse_mode, disable_preview)
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
