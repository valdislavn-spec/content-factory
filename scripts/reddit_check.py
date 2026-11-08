#!/usr/bin/env python3
"""Проверка доступа к Reddit Data API (без публикации).

Читает REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET / REDDIT_USERNAME /
REDDIT_PASSWORD / REDDIT_SUBREDDIT из окружения или .env и проверяет:
1) OAuth-токен (password grant для script-приложения);
2) /api/v1/me — кто мы и какая карма/возраст аккаунта;
3) /r/<subreddit>/about — существует ли сабреддит, подписчики, 18+;
4) /r/<subreddit>/about/rules — правила (можно ли self-post);
5) заголовки X-Ratelimit-* (100 запросов/мин на client_id).

    python scripts/reddit_check.py
    python scripts/reddit_check.py --subreddit MySubreddit

Коды выхода: 0 — всё ок, 1 — ошибка запроса/ответа, 2 — нет кредов.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.config import Settings  # noqa: E402
from content_factory.utils import env  # noqa: E402

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_BASE = "https://oauth.reddit.com"


def _user_agent(username: str) -> str:
    return "script:content-factory-check:1.0 (by /u/{})".format(username or "unknown")


def _request(
    url: str,
    *,
    method: str = "GET",
    headers: dict | None = None,
    form: dict | None = None,
    timeout: float = 30.0,
):
    body = urllib.parse.urlencode(form).encode("utf-8") if form else None
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            data = json.loads(raw) if raw else {}
            return response.status, dict(response.headers), data
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            data = json.loads(raw) if raw else {}
        except ValueError:
            data = {"raw": raw.decode("utf-8", "replace")[:400]}
        return exc.code, dict(exc.headers or {}), data


def _token(creds: dict) -> tuple[str, dict]:
    basic = base64.b64encode(
        "{}:{}".format(creds["client_id"], creds["client_secret"]).encode("utf-8")
    ).decode("ascii")
    status, headers, data = _request(
        TOKEN_URL,
        method="POST",
        headers={
            "Authorization": "Basic {}".format(basic),
            "User-Agent": _user_agent(creds["username"]),
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        form={
            "grant_type": "password",
            "username": creds["username"],
            "password": creds["password"],
        },
    )
    token = str(data.get("access_token") or "")
    if status != 200 or not token:
        error = data.get("error") or data.get("message") or json.dumps(data, ensure_ascii=False)
        raise RuntimeError("токен не получен (HTTP {}): {}".format(status, error))
    return token, headers


def _api(token: str, creds: dict, path: str):
    status, headers, data = _request(
        API_BASE + path,
        headers={
            "Authorization": "bearer {}".format(token),
            "User-Agent": _user_agent(creds["username"]),
            "Accept": "application/json",
        },
    )
    return status, headers, data


def _print_ratelimit(headers: dict) -> None:
    used = headers.get("X-Ratelimit-Used") or headers.get("x-ratelimit-used")
    remaining = headers.get("X-Ratelimit-Remaining") or headers.get("x-ratelimit-remaining")
    reset = headers.get("X-Ratelimit-Reset") or headers.get("x-ratelimit-reset")
    if used or remaining or reset:
        print("  rate limit: used={} remaining={} reset={}s".format(used, remaining, reset))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Проверка Reddit Data API")
    parser.add_argument("--subreddit", default="", help="Сабреддит (по умолчанию REDDIT_SUBREDDIT)")
    parser.add_argument("--json", action="store_true", help="Вывести итог в JSON")
    args = parser.parse_args(argv)

    Settings.load()  # подгружает .env в процесс
    creds = {
        "client_id": env("REDDIT_CLIENT_ID", ""),
        "client_secret": env("REDDIT_CLIENT_SECRET", ""),
        "username": env("REDDIT_USERNAME", ""),
        "password": env("REDDIT_PASSWORD", ""),
    }
    subreddit = (args.subreddit or env("REDDIT_SUBREDDIT", "")).strip().lstrip("r/").strip("/")
    missing = [name for name, value in creds.items() if not value]
    if not subreddit:
        missing.append("REDDIT_SUBREDDIT")
    if missing:
        print("Нет кредов: " + ", ".join(name.upper() for name in missing))
        print("Инструкция: docs/promo/reddit-api-setup.md")
        return 2

    result: dict = {"ok": False, "subreddit": subreddit}
    try:
        token, _ = _token(creds)
        result["token"] = True
        status, headers, me = _api(token, creds, "/api/v1/me")
        _print_ratelimit(headers)
        if status != 200:
            print("Ошибка /api/v1/me: HTTP {} {}".format(status, me))
            return 1
        user = {
            "name": me.get("name"),
            "created_utc": me.get("created_utc"),
            "link_karma": me.get("link_karma"),
            "comment_karma": me.get("comment_karma"),
            "is_employee": me.get("is_employee"),
        }
        result["user"] = user
        print("Аккаунт: u/{} (карма: link={}, comment={})".format(
            user["name"], user["link_karma"], user["comment_karma"]
        ))

        status, headers, about = _api(token, creds, "/r/{}/about".format(subreddit))
        _print_ratelimit(headers)
        if status != 200 or not (about.get("data") or {}).get("display_name"):
            print("Ошибка /r/{}/about: HTTP {} {}".format(subreddit, status, about))
            result["subreddit_ok"] = False
            return 1
        sub = about["data"]
        result["subreddit_ok"] = True
        result["subreddit_info"] = {
            "title": sub.get("title"),
            "subscribers": sub.get("subscribers"),
            "over18": sub.get("over18"),
            "submission_type": sub.get("submission_type"),
            "user_is_banned": sub.get("user_is_banned"),
            "user_is_moderator": sub.get("user_is_moderator"),
        }
        print("Сабреддит r/{}: «{}», подписчиков {}".format(
            sub.get("display_name"), sub.get("title"), sub.get("subscribers")
        ))
        if sub.get("user_is_banned"):
            print("  ВНИМАНИЕ: аккаунт забанен в этом сабреддите")

        status, _, rules = _api(token, creds, "/r/{}/about/rules".format(subreddit))
        rules_list = ((rules.get("rules") or []) if isinstance(rules, dict) else [])
        result["rules"] = [rule.get("short_name") for rule in rules_list]
        print("Правил: {}".format(len(rules_list)))
        for rule in rules_list[:8]:
            print("  • {}".format(rule.get("short_name")))

        result["ok"] = True
        print("\nOK: Reddit Data API доступен, можно запускать reddit-digest.")
    except RuntimeError as exc:
        result["error"] = str(exc)
        print("Ошибка: {}".format(exc))
        print("Подсказка: проверьте client_id/secret (script app), пароль и 2FA.")
        return 1
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        print("Ошибка: {}".format(exc))
        return 1
    finally:
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
