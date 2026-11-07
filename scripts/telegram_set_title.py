#!/usr/bin/env python3
"""Меняет название Telegram-канала через Bot API (setChatTitle).

Запуск (бот должен быть админом с правом «Менять информацию»):

    ./.venv/bin/python scripts/telegram_set_title.py --chat-id -100... --title "Новое имя"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from content_factory.utils import env, load_dotenv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chat-id", required=True)
    parser.add_argument("--title", required=True)
    args = parser.parse_args()

    load_dotenv()
    token = env("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("TELEGRAM_BOT_TOKEN не задан")
        return 1
    base = (env("TELEGRAM_API_BASE", "") or "https://api.telegram.org").rstrip("/")
    url = f"{base}/bot{token}/setChatTitle"
    body = urllib.parse.urlencode({"chat_id": args.chat_id, "title": args.title}).encode()
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = json.load(response)
    except Exception as exc:  # noqa: BLE001
        print(f"Ошибка setChatTitle: {type(exc).__name__}: {exc}")
        return 1
    if not data.get("ok"):
        print("Telegram ответил:", data.get("description"))
        return 1
    print(f"Название канала {args.chat_id} изменено на: {args.title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
