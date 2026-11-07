#!/usr/bin/env python3
"""Применяет названия и описания каналов из конфига к Telegram (Bot API).

Для каждого включённого канала с chat_id вызывает setChatTitle и
setChatDescription. Бот должен быть админом с правом «Менять информацию».

Запуск:

    ./.venv/bin/python scripts/telegram_apply_profile.py
    ./.venv/bin/python scripts/telegram_apply_profile.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from content_factory.config import Settings, load_channels
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
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--channel", default="all", help="id канала или all")
    args = parser.parse_args()

    load_dotenv()
    token = env("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("TELEGRAM_BOT_TOKEN не задан")
        return 1
    settings = Settings.load()
    channels = load_channels(settings)
    selected = [c for c in channels if args.channel in ("all", c.id)]
    ok = 0
    for channel in selected:
        if not channel.enabled:
            continue
        chat_id = str(channel.telegram_chat_id or "").strip()
        if not chat_id:
            print(f"{channel.id}: chat_id не задан — пропуск")
            continue
        title = str(channel.title or "").strip()
        description = str(channel.description or "").strip()
        if args.dry_run:
            print(f"{channel.id} ({chat_id}): title={title!r} description={description[:60]!r}…")
            continue
        try:
            if title:
                call(token, "setChatTitle", {"chat_id": chat_id, "title": title})
            if description:
                call(token, "setChatDescription", {"chat_id": chat_id, "description": description})
            print(f"{channel.id} ({chat_id}): OK → {title!r}")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"{channel.id} ({chat_id}): ОШИБКА {type(exc).__name__}: {exc}")
    print(f"\nОбновлено каналов: {ok}/{len(selected)}")
    return 0 if ok or args.dry_run else 1


if __name__ == "__main__":
    sys.exit(main())
