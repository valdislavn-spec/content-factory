#!/usr/bin/env python3
"""Create a Telethon session for post views/reactions (one-time, interactive).

    python scripts/telegram_auth.py
    python scripts/telegram_auth.py --session data/telegram.session

Requires TG_API_ID / TG_API_HASH from https://my.telegram.org (free), and a
Telegram user account that can read the channels.  The session file contains
login material: keep it out of Git and never share it.

The Bot API cannot return views/reactions; Telethon is the only automated way.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.utils import env  # noqa: E402


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Создать Telethon-сессию для метрик")
    parser.add_argument(
        "--session",
        default=env("TG_SESSION", "data/telegram.session"),
        help="путь к .session (по умолчанию TG_SESSION или data/telegram.session)",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    api_id = env("TG_API_ID", "")
    api_hash = env("TG_API_HASH", "")
    if not api_id or not api_hash:
        print("Нужны TG_API_ID и TG_API_HASH: https://my.telegram.org → API development tools")
        return 2
    try:
        from telethon import TelegramClient
    except ImportError:
        print("Нужен Telethon: pip install -r requirements-optional.txt")
        return 2
    session = Path(args.session)
    if not session.is_absolute():
        session = Path(ROOT) / session
    session.parent.mkdir(parents=True, exist_ok=True)
    print(f"Сессия: {session}")
    print("Telethon попросит номер телефона и код из Telegram (интерактивно).")
    client = TelegramClient(str(session), int(api_id), api_hash)
    client.start()
    me = client.get_me()
    if me is not None:
        print(f"Готово: @{getattr(me, 'username', None) or me.id}")
    client.disconnect()
    print("Дальше: TG_SESSION=" + str(session) + " python -m content_factory telegram-metrics")
    print("Не коммить .session: это доступ к аккаунту.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
