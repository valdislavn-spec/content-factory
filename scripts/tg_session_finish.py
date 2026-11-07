#!/usr/bin/env python3
"""Шаг 2 из 2: ввести код, завершить вход и сохранить TG_SESSION.

Запускается workflow `tg-session` (mode=finish); читает tg_session_partial.json
из артефакта предыдущего запуска и пишет tg_session_final.txt.

    CODE=12345 TG_API_ID=... TG_API_HASH=... python scripts/tg_session_finish.py
    # при 2FA: TG_PASSWORD=...
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

PARTIAL = Path("tg_session_partial.json")
OUT = Path("tg_session_final.txt")


async def main() -> int:
    try:
        from telethon import TelegramClient
        from telethon.errors import SessionPasswordNeededError
        from telethon.sessions import StringSession
    except ImportError:
        print("pip install 'Telethon>=1.34'", file=sys.stderr)
        return 2
    if not PARTIAL.is_file():
        print("Нет tg_session_partial.json — сначала запустите mode=start", file=sys.stderr)
        return 2
    data = json.loads(PARTIAL.read_text(encoding="utf-8"))
    api_id = os.environ.get("TG_API_ID", "").strip()
    api_hash = os.environ.get("TG_API_HASH", "").strip()
    code = os.environ.get("CODE", "").strip()
    password = os.environ.get("TG_PASSWORD", "").strip()
    if not (api_id.isdigit() and api_hash and code):
        print("Нужны TG_API_ID, TG_API_HASH и CODE", file=sys.stderr)
        return 2

    client = TelegramClient(StringSession(data["session"]), int(api_id), api_hash)
    await client.connect()
    try:
        try:
            await client.sign_in(
                phone=data["phone"],
                code=code,
                phone_code_hash=data["phone_code_hash"],
            )
        except SessionPasswordNeededError:
            if not password:
                print("Включён 2FA: добавьте секрет TG_PASSWORD и повторите finish.", file=sys.stderr)
                return 3
            await client.sign_in(password=password)
        me = await client.get_me()
        OUT.write_text(client.session.save(), encoding="utf-8")
        print("Вход выполнен:", "@" + (me.username or ""), f"(id {me.id})")
        print("Готово: скачайте артефакт tg-session-final, скопируйте строку")
        print("в GitHub Secret TG_SESSION и удалите артефакты запусков.")
        return 0
    finally:
        await client.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
