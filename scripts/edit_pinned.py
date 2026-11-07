#!/usr/bin/env python3
"""Обновляет текст уже закреплённых постов (editMessageText, закреп сохраняется)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)


def api(method: str, payload: dict) -> dict:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    base = (os.environ.get("TELEGRAM_API_BASE", "") or "https://api.telegram.org").rstrip("/")
    body = urllib.parse.urlencode(payload).encode()
    request = urllib.request.Request(
        f"{base}/bot{token}/{method}", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--language", choices=["en", "es"], required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    texts = yaml.safe_load(open(f"config/pinned/{args.language}.yaml", encoding="utf-8")) or {}
    ids = (yaml.safe_load(open("config/pinned/ids.yaml", encoding="utf-8")) or {}).get(args.language, {})
    channels = {}
    data = yaml.safe_load(open(f"config/channels.{args.language}.yaml", encoding="utf-8")) or {}
    for channel in data.get("channels") or []:
        channels[str(channel.get("id"))] = str(channel.get("telegram_chat_id") or "")
    ok = 0
    for channel_id, text in texts.items():
        chat_id = channels.get(str(channel_id))
        message_id = ids.get(str(channel_id))
        if not chat_id or not message_id or not str(text or "").strip():
            print(f"{channel_id}: нет chat_id/message_id/текста — пропуск")
            continue
        if args.dry_run:
            print(f"{channel_id} (msg {message_id}): {str(text)[:90]}…")
            continue
        try:
            result = api("editMessageText", {
                "chat_id": chat_id,
                "message_id": str(message_id),
                "text": str(text).strip(),
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            })
            print(f"{channel_id}: обновлён (ok={result.get('ok')})")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"{channel_id}: ОШИБКА {type(exc).__name__}: {exc}")
    print(f"итого: {ok}/{len(texts)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
