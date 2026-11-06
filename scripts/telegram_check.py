#!/usr/bin/env python3
"""Проверка Telegram-бота и прав в каналах (читает .env, токен не печатает).

Запуск из папки проекта:

    ./.venv/bin/python scripts/telegram_check.py

Скрипт:
  1) вызывает getMe и показывает бота;
  2) для каждого канала из активного config/*.yaml (или из
     CONTENT_FACTORY_CHANNELS) вызывает getChat/getChatMember;
  3) печатает реальное название, @username, статус бота и право публикации.

Если сеть блокирует api.telegram.org, будет понятная ошибка — значит нужен
VPN/прокси (urllib сам подхватывает переменные https_proxy/HTTPS_PROXY) или
запуск через GitHub Actions.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from content_factory.config import Settings, load_channels
from content_factory.utils import env


def api(token: str, method: str, timeout: float = 20.0, **params):
    """POST в Bot API (напрямую или через релей TELEGRAM_API_BASE)."""
    base = (env("TELEGRAM_API_BASE", "") or "https://api.telegram.org").rstrip("/")
    url = f"{base}/bot{token}/{method}"
    body = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def main() -> int:
    settings = Settings.load()
    token = env("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("TELEGRAM_BOT_TOKEN не задан в .env")
        return 1
    try:
        me = api(token, "getMe")["result"]
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        print(f"getMe: HTTP {exc.code} {detail}")
        return 1
    except Exception as exc:
        print(f"api.telegram.org недоступен: {type(exc).__name__}: {exc}")
        print("Проверьте VPN/прокси (https_proxy) или запускайте через GitHub Actions.")
        return 1

    print(f"Бот: @{me.get('username')} (id {me.get('id')})")
    channels = load_channels(settings)
    ok = 0
    for channel in channels:
        chat_id = str(channel.telegram_chat_id or "").strip()
        label = f"{channel.id:18s}"
        if not chat_id:
            print(f"{label} — chat_id не задан (dry-run)")
            continue
        try:
            chat = api(token, "getChat", chat_id=chat_id)["result"]
            member = api(token, "getChatMember", chat_id=chat_id, user_id=me["id"])["result"]
            title = chat.get("title") or "?"
            username = chat.get("username")
            status = member.get("status")
            can_post = member.get("can_post_messages")
            ok += 1
            print(
                f"{label} {chat_id} | {title!r} | @{username} | {chat.get('type')} "
                f"| бот: {status} | can_post={can_post}"
            )
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            print(f"{label} {chat_id} | ОШИБКА HTTP {exc.code}: {detail}")
        except Exception as exc:
            print(f"{label} {chat_id} | ОШИБКА: {type(exc).__name__}: {exc}")

    print(f"\nПроверено каналов: {len(channels)}, доступно боту: {ok}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
