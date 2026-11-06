"""Публикация во ВКонтакте через метод wall.post (stdlib urllib).

ВКонтакте работает в России без VPN и бесплатен для сообществ — это пример
расширяемости контент-завода за пределы Telegram. Токен группы и её числовой
id берутся из .env (VK_ACCESS_TOKEN, VK_GROUP_ID). Сообщения ВК не понимают
HTML, поэтому отправляется очищенный текст.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Tuple

from ..config import Settings
from ..models import ChannelConfig, GeneratedPost, PublishResult
from ..utils import env, strip_html, truncate
from .base import VK_MESSAGE_LIMIT, Publisher

logger = logging.getLogger(__name__)

API_URL = "https://api.vk.com/method/wall.post"


class VKAPIError(RuntimeError):
    """Ошибка VK API (сеть, HTTP-статус или error в JSON)."""


def _extract_error(raw: bytes) -> str:
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except (TypeError, ValueError):
        return raw.decode("utf-8", errors="replace").strip()[:500]
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            return str(
                error.get("error_msg") or error.get("error_text") or error.get("error_code") or ""
            )[:500]
    return ""


class VKPublisher(Publisher):
    """Публикатор записи на стену сообщества ВКонтакте."""

    name = "vk"

    # ------------------------------------------------------------------
    # конфигурация
    # ------------------------------------------------------------------
    def _config(self) -> Dict[str, Any]:
        config = self.settings.publishers.get("vk", {})
        return config if isinstance(config, dict) else {}

    def _token(self) -> str:
        env_name = str(self._config().get("access_token_env") or "VK_ACCESS_TOKEN")
        return env("{}".format(env_name), "") or ""

    def _group_id(self) -> str:
        env_name = str(self._config().get("group_id_env") or "VK_GROUP_ID")
        return env("{}".format(env_name), "") or ""

    def _api_version(self) -> str:
        return str(self._config().get("api_version") or "5.199")

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------
    def _call(self, payload: Dict[str, Any]) -> Any:
        body = urllib.parse.urlencode({k: v for k, v in payload.items() if v is not None}).encode(
            "utf-8"
        )
        request = urllib.request.Request(
            API_URL,
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
            description = _extract_error(raw) or "HTTP {} {}".format(exc.code, exc.reason)
            raise VKAPIError("VK API: {}".format(description)) from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise VKAPIError("Сетевая ошибка VK API: {}".format(exc)) from exc

        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise VKAPIError("Некорректный ответ VK API") from exc
        if not isinstance(data, dict):
            raise VKAPIError("Неожиданный формат ответа VK API")
        if isinstance(data.get("error"), dict):
            error = data["error"]
            raise VKAPIError(
                "VK API: [{}] {}".format(
                    error.get("error_code", "?"), error.get("error_msg", "неизвестная ошибка")
                )
            )
        return data.get("response")

    # ------------------------------------------------------------------
    # публикация
    # ------------------------------------------------------------------
    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        # Страховка: в dry_run настоящая публикация невозможна.
        if settings.dry_run:
            return self.dry_run_publisher().publish(post, channel, settings)
        try:
            token = self._token()
            group_id = self._group_id()
            if not token:
                return self._result(
                    post,
                    channel,
                    ok=False,
                    error=(
                        "Не задан токен ВКонтакте (VK_ACCESS_TOKEN). "
                        "Заполните .env или используйте только Telegram."
                    ),
                )
            if not group_id:
                return self._result(
                    post,
                    channel,
                    ok=False,
                    error="Не задан id сообщества ВКонтакте (VK_GROUP_ID)",
                )

            message = strip_html(post.text).strip()
            if not message:
                return self._result(
                    post, channel, ok=False, error="Пост пустой — отправлять нечего"
                )
            if len(message) > VK_MESSAGE_LIMIT:
                message = truncate(message, VK_MESSAGE_LIMIT)

            try:
                result = self._call(
                    {
                        "owner_id": "-{}".format(str(group_id).lstrip("-")),
                        "message": message,
                        "from_group": 1,
                        "v": self._api_version(),
                        "access_token": token,
                    }
                )
            except VKAPIError as exc:
                logger.warning("VK: канал %s, пост %s: %s", channel.id, post.id, exc)
                return self._result(post, channel, ok=False, error=str(exc))

            if not isinstance(result, dict) or result.get("post_id") is None:
                return self._result(
                    post,
                    channel,
                    ok=False,
                    error="VK API не вернул post_id",
                )
            post_vk_id = str(result.get("post_id"))
            owner = "-{}".format(str(group_id).lstrip("-"))
            url = "https://vk.com/wall{}_{}".format(owner, post_vk_id)
            logger.info("VK: пост %s канала %s опубликован (%s)", post.id, channel.id, url)
            return self._result(
                post,
                channel,
                ok=True,
                external_id="{}_{}".format(str(group_id).lstrip("-"), post_vk_id),
                url=url,
            )
        except Exception as exc:  # noqa: BLE001 - публикатор не падает наружу
            logger.exception("VK: непредвиденная ошибка публикации поста %s", post.id)
            return self._result(
                post, channel, ok=False, error="Непредвиденная ошибка VK: {}".format(exc)
            )

    # ------------------------------------------------------------------
    # проверка
    # ------------------------------------------------------------------
    def check(self) -> Tuple[bool, str]:
        problems: List[str] = []
        if not self._token():
            problems.append("не задан VK_ACCESS_TOKEN")
        if not self._group_id():
            problems.append("не задан VK_GROUP_ID")
        if problems:
            return False, "ВКонтакте: " + "; ".join(problems) + " (см. .env.example)"
        return (
            True,
            "ВКонтакте: токен и group_id заданы (публикация от имени сообщества {})".format(
                self._group_id()
            ),
        )
