#!/usr/bin/env python3
"""Шаг 1 из 2: запросить код входа и сохранить частичную сессию (GitHub Actions).

Запускается workflow `tg-session` (mode=start) на раннере GitHub, где Telegram
доступен даже при блокировке сети локально. Секретов не печатает.

    TG_API_ID=... TG_API_HASH=... PHONE=+7999... python scripts/tg_session_start.py

Создаёт tg_session_partial.json (session + phone + phone_code_hash) для шага 2.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

OUT = Path("tg_session_partial.json")


async def main() -> int:
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        print("pip install 'Telethon>=1.34'", file=sys.stderr)
        return 2
    api_id = os.environ.get("TG_API_ID", "").strip()
    api_hash = os.environ.get("TG_API_HASH", "").strip()
    phone = os.environ.get("PHONE", "").strip()
    if not (api_id.isdigit() and api_hash and phone):
        print("Нужны TG_API_ID, TG_API_HASH и PHONE", file=sys.stderr)
        return 2

    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.connect()
    try:
        sent = await client.send_code_request(phone)
        payload = {
            "session": client.session.save(),
            "phone": phone,
            "phone_code_hash": sent.phone_code_hash,
        }
        OUT.write_text(json.dumps(payload), encoding="utf-8")
        print("Код отправлен в Telegram. Сохранена частичная сессия.")
        print("Дальше: скачайте артефакт tg-session-partial (он в этом запуске),")
        print("затем запустите workflow tg-session с mode=finish и этим start_run_id.")
        return 0
    finally:
        await client.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
