"""Публикация в Reddit через Script App OAuth (password grant).

Endpoints:
    POST https://www.reddit.com/api/v1/access_token
    POST https://oauth.reddit.com/api/submit

Креды в .env:
    REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET  — script app на reddit.com/prefs/apps
    REDDIT_USERNAME / REDDIT_PASSWORD        — аккаунт-владелец
    REDDIT_SUBREDDIT                         — сабреддит (без r/), например "USNewsWire"

Для каждого канала можно переопределить суффиксом CHANNEL_ID:
    REDDIT_SUBREDDIT_CRYPTO_NEWS=r/USCryptoFeed

Публикуем self-пост: заголовок — первая строка поста, тело — весь текст.
Reddit требует уникальные заголовки и не любит частый постинг: 2–3 поста/сутки
на сабреддит безопасно, 90/сутки — гарантированный бан.
"""
from __future__ import annotations

import base64
from typing import Any, Dict, Tuple

from ..config import Settings
from ..models import ChannelConfig, GeneratedPost, PublishResult
import html as html_lib
import re

from ..utils import truncate
from .social import SocialAPIError, SocialPublisher, channel_link, http_json

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_BASE = "https://oauth.reddit.com"
MAX_TITLE = 300
MAX_TEXT = 40000


class RedditPublisher(SocialPublisher):
    """Публикатор self-поста в выбранный сабреддит."""

    name = "reddit"

    def _creds(self, channel: ChannelConfig) -> Dict[str, str]:
        return {
            "client_id": self._env(channel, "REDDIT_CLIENT_ID"),
            "client_secret": self._env(channel, "REDDIT_CLIENT_SECRET"),
            "username": self._env(channel, "REDDIT_USERNAME"),
            "password": self._env(channel, "REDDIT_PASSWORD"),
            "subreddit": self._env(channel, "REDDIT_SUBREDDIT"),
        }

    def check(self, channel: ChannelConfig = None) -> Tuple[bool, str]:
        creds = self._creds(channel) if channel is not None else {}
        if not channel:
            from ..utils import env

            creds = {
                "client_id": env("REDDIT_CLIENT_ID", "") or "",
                "client_secret": env("REDDIT_CLIENT_SECRET", "") or "",
                "username": env("REDDIT_USERNAME", "") or "",
                "password": env("REDDIT_PASSWORD", "") or "",
                "subreddit": env("REDDIT_SUBREDDIT", "") or "",
            }
        missing = [key for key, value in creds.items() if not str(value or "").strip()]
        if missing:
            return False, "Reddit не настроен: нет " + ", ".join(key.upper() for key in missing)
        return True, "Reddit r/{}".format(creds["subreddit"].strip().lstrip("r/"))

    @staticmethod
    def _user_agent(username: str) -> str:
        return "script:content-factory:1.0 (by /u/{})".format(username or "unknown")

    def _token(self, creds: Dict[str, str]) -> str:
        basic = base64.b64encode(
            "{}:{}".format(creds["client_id"], creds["client_secret"]).encode("utf-8")
        ).decode("ascii")
        payload = {
            "grant_type": "password",
            "username": creds["username"],
            "password": creds["password"],
        }
        headers = {
            "Authorization": "Basic {}".format(basic),
            "User-Agent": self._user_agent(creds["username"]),
        }
        data = http_json(TOKEN_URL, payload=payload, headers=headers, form=True)
        token = str(data.get("access_token") or "")
        if not token:
            error = data.get("error") or data.get("message") or "нет access_token"
            raise SocialAPIError("Reddit: токен не получен ({})".format(error))
        return token

    @staticmethod
    def _plain_text(post: GeneratedPost) -> str:
        """Текст с сохранением переносов строк (Reddit читаемее, чем одна строка)."""
        raw = str(getattr(post, "text", "") or "")
        raw = re.sub(r"<br\s*/?>", "\n", raw)
        raw = re.sub(r"</(?:p|div|blockquote)>", "\n", raw)
        raw = re.sub(r"<[^>]+>", "", raw)
        raw = html_lib.unescape(raw)
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)

    @classmethod
    def _title_and_text(cls, post: GeneratedPost, channel: ChannelConfig) -> Tuple[str, str]:
        meta_title = str((getattr(post, "meta", {}) or {}).get("reddit_title") or "").strip()
        plain = cls._plain_text(post)
        lines = [line for line in plain.splitlines() if line.strip()]
        if meta_title:
            return meta_title[:MAX_TITLE], truncate(plain, MAX_TEXT - 60, suffix="…")
        # Заголовок — первая содержательная строка (для дайджеста пропускаем
        # короткую шапку «Resumen · дата»), иначе первая строка.
        title = ""
        for line in lines:
            candidate = re.sub(r"^[^\w]+", "", line).strip()
            if len(candidate) >= 30:
                title = candidate
                break
        if not title:
            title = re.sub(r"^[^\w]+", "", lines[0]).strip() if lines else "Update"
        title = title[:MAX_TITLE]
        text = truncate(plain, MAX_TEXT - 60, suffix="…")
        link = channel_link(channel)
        if link:
            text = f"{text}\n\n{link}".strip()
        return title, text

    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        ok, detail = self.check(channel)
        if not ok:
            return self._result(post, channel, ok=False, error="Reddit не настроен: {}".format(detail))
        creds = self._creds(channel)
        subreddit = creds["subreddit"].strip().lstrip("r/")
        title, text = self._title_and_text(post, channel)
        if not title:
            return self._result(post, channel, ok=False, error="Reddit: пустой заголовок")
        try:
            token = self._token(creds)
            data = http_json(
                API_BASE + "/api/submit",
                payload={
                    "sr": subreddit,
                    "kind": "self",
                    "title": title,
                    "text": text,
                    "api_type": "json",
                    "resubmit": "false",
                },
                headers={
                    "Authorization": "bearer {}".format(token),
                    "User-Agent": self._user_agent(creds["username"]),
                },
                form=True,
            )
        except SocialAPIError as exc:
            return self._result(post, channel, ok=False, error=str(exc))

        body = data.get("json") if isinstance(data, dict) else {}
        errors = (body or {}).get("errors") or []
        if errors:
            return self._result(
                post, channel, ok=False, error="Reddit: {}".format(errors[0] if errors else errors)
            )
        result = (body or {}).get("data") or {}
        external_id = str(result.get("id") or result.get("name") or "")
        url = str(result.get("url") or "")
        if not url and external_id:
            url = "https://www.reddit.com/r/{}/comments/{}".format(subreddit, external_id)
        return self._result(post, channel, ok=True, external_id=external_id, url=url)
