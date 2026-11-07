#!/usr/bin/env python3
"""Локальное создание TG_SESSION (StringSession) для GitHub Actions.

Запускать ТОЛЬКО на своём компьютере, не в CI. Скрипт попросит номер телефона,
код из Telegram и пароль 2FA (если включён), затем выведет строку сессии.

    cd content-factory
    ./.venv/bin/pip install "Telethon>=1.34"
    ./.venv/bin/python scripts/make_tg_session.py

Полученную строку вставить в GitHub → Settings → Secrets and variables →
Actions → New repository secret с именем TG_SESSION.
TG_API_ID и TG_API_HASH — из https://my.telegram.org → API development tools.

ВАЖНО: сессия = полный доступ к аккаунту. Не коммитить, не пересылать,
хранить только в GitHub Secrets. Отозвать: Telegram → Settings → Devices.
"""
from __future__ import annotations

import asyncio
import getpass
import os
import sys


async def main() -> int:
    try:
        from telethon import TelegramClient
        from telethon.errors import SessionPasswordNeededError
        from telethon.sessions import StringSession
    except ImportError:
        print("Сначала: pip install 'Telethon>=1.34'", file=sys.stderr)
        return 2

    api_id = (os.environ.get("TG_API_ID") or input("TG_API_ID (число): ")).strip()
    api_hash = (os.environ.get("TG_API_HASH") or input("TG_API_HASH: ")).strip()
    if not api_id.isdigit() or not api_hash:
        print("Нужны числовой TG_API_ID и TG_API_HASH из my.telegram.org", file=sys.stderr)
        return 2

    proxy = os.environ.get("TG_PROXY", "").strip()
    proxy_arg = None
    if proxy:
        # socks5://user:pass@host:port или socks5://host:port
        from urllib.parse import urlparse
        parsed = urlparse(proxy if "://" in proxy else "socks5://" + proxy)
        proxy_arg = (
            parsed.scheme or "socks5",
            parsed.hostname,
            parsed.port or 1080,
            True,
            parsed.username,
            parsed.password,
        )
    client = TelegramClient(StringSession(), int(api_id), api_hash, proxy=proxy_arg)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            phone = (os.environ.get("TG_PHONE") or input("Телефон в формате +7999...: ")).strip()
            sent = await client.send_code_request(phone)
            code = (os.environ.get("TG_CODE") or input("Код из Telegram: ")).strip()
            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
            except SessionPasswordNeededError:
                password = os.environ.get("TG_PASSWORD") or getpass.getpass("Пароль 2FA: ")
                await client.sign_in(password=password)
        me = await client.get_me()
        session = client.session.save()
        print()
        print("Вошли как:", "@" + (me.username or ""), f"(id {me.id})")
        print()
        print("=== TG_SESSION (скопировать целиком, в одну строку) ===")
        print(session)
        print("========================================================")
        print()
        print("Дальше: GitHub → Settings → Secrets and variables → Actions →")
        print("New repository secret: TG_API_ID, TG_API_HASH, TG_SESSION.")
        print("После этого: Actions → vp-outreach → dry_run=true, потом false.")
        return 0
    finally:
        await client.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
