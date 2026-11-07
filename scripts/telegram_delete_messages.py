#!/usr/bin/env python3
"""Удаляет сообщения из Telegram-каналов (Bot API deleteMessage).

Вход — JSON-массив пар: [{"chat_id": "-100...", "message_id": 123}, ...].
Можно передать файлом или строкой в --json.

    ./.venv/bin/python scripts/telegram_delete_messages.py --file /tmp/dups.json
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


def call(token: str, method: str, payload: dict) -> dict:
    base = (env("TELEGRAM_API_BASE", "") or "https://api.telegram.org").rstrip("/")
    body = urllib.parse.urlencode({k: v for k, v in payload.items() if v is not None}).encode()
    request = urllib.request.Request(
        f"{base}/bot{token}/{method}",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="JSON-файл со списком сообщений")
    parser.add_argument("--json", help="JSON-список строкой")
    args = parser.parse_args()

    load_dotenv()
    token = env("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("TELEGRAM_BOT_TOKEN не задан")
        return 1
    raw = args.json or ""
    if args.file:
        raw = open(args.file, encoding="utf-8").read()
    if not raw.strip():
        print("Нужен --file или --json со списком сообщений")
        return 1
    items = json.loads(raw)
    ok = 0
    for item in items:
        chat_id = str(item.get("chat_id") or "")
        message_id = item.get("message_id")
        try:
            call(token, "deleteMessage", {"chat_id": chat_id, "message_id": message_id})
            print(f"удалено: {chat_id} / msg {message_id}")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"ОШИБКА {chat_id} / msg {message_id}: {type(exc).__name__}: {exc}")
    print(f"\nУдалено: {ok}/{len(items)}")
    return 0 if ok == len(items) else 1


if __name__ == "__main__":
    sys.exit(main())
