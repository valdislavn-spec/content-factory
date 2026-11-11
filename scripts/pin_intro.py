#!/usr/bin/env python3
"""Публикует и закрепляет вводный пост канала (config/pinned/<lang>.yaml)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml  # noqa: E402

from content_factory.config import Settings, load_channels  # noqa: E402
from content_factory.utils import env, load_dotenv  # noqa: E402


# Cloudflare/бот-защита на релее может банить UA «Python-urllib» (ошибка 1010),
# поэтому для всех запросов Bot API используем обычный браузерный UA.
USER_AGENT = (
    "Mozilla/5.0 (compatible; ContentFactory/1.0; +https://t.me/) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0"
)


def api(method: str, payload: dict) -> dict:
    token = env("TELEGRAM_BOT_TOKEN", "")
    base = (env("TELEGRAM_API_BASE", "") or "https://api.telegram.org").rstrip("/")
    body = urllib.parse.urlencode({k: v for k, v in payload.items() if v is not None}).encode()
    request = urllib.request.Request(
        f"{base}/bot{token}/{method}",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--language", choices=["en", "es"], default="en")
    parser.add_argument("--channel", default="", help="обновить только этот канал")
    parser.add_argument("--update", action="store_true", help="править существующий закреп, а не слать новый пост")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    load_dotenv()
    os.environ["CONTENT_FACTORY_CHANNELS"] = f"config/channels.{args.language}.yaml"
    settings = Settings.load()
    channels = load_channels(settings)
    pinned_path = os.path.join("config", "pinned", f"{args.language}.yaml")
    pinned = yaml.safe_load(open(pinned_path, encoding="utf-8")) or {}
    ids_path = os.path.join("config", "pinned", "ids.yaml")
    ids = {}
    if args.update:
        try:
            ids = (yaml.safe_load(open(ids_path, encoding="utf-8")) or {}).get(args.language) or {}
        except OSError:
            ids = {}
    ok = 0
    for channel in channels:
        if args.channel and channel.id != args.channel:
            continue
        text = str(pinned.get(channel.id) or "").strip()
        chat_id = str(channel.telegram_chat_id or "").strip()
        if not text or not chat_id:
            print(f"{channel.id}: нет текста/chat_id — пропуск")
            continue
        if args.dry_run:
            print(f"{channel.id}: {text[:80]}...")
            continue
        pinned_id = ids.get(channel.id)
        if args.update and pinned_id:
            try:
                api("editMessageText", {
                    "chat_id": chat_id,
                    "message_id": pinned_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": "true",
                })
                print(f"{channel.id}: закреп обновлён (msg {pinned_id})")
                ok += 1
            except Exception as exc:  # noqa: BLE001
                print(f"{channel.id}: не удалось обновить закреп {pinned_id}: {exc}")
            continue
        try:
            sent = api("sendMessage", {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            })
            message_id = sent["result"]["message_id"]
            api("pinChatMessage", {
                "chat_id": chat_id,
                "message_id": message_id,
                "disable_notification": "true",
            })
            print(f"{channel.id}: закреплено (msg {message_id})")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"{channel.id}: ОШИБКА {type(exc).__name__}: {exc}")
    print(f"итого: {ok}/{len(channels)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
