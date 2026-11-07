#!/usr/bin/env python3
"""Обновляет текст уже закреплённых постов (editMessageText, закреп сохраняется).

chat_id берётся из config/channels.<lang>.yaml и переменных окружения
TELEGRAM_CHAT_ID_<CHANNEL> (как в apply-profile/pin-intro), поэтому работают и
ES-каналы, чьи ID лежат в GitHub Secrets. Сообщение должно быть отправлено
ботом (id — в config/pinned/ids.yaml).
"""
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
sys.path.insert(0, ROOT)

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
    body = urllib.parse.urlencode(payload).encode()
    request = urllib.request.Request(
        f"{base}/bot{token}/{method}", data=body,
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
    parser.add_argument("--language", choices=["en", "es"], required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    load_dotenv()
    os.environ["CONTENT_FACTORY_CHANNELS"] = f"config/channels.{args.language}.yaml"
    settings = Settings.load()
    channels = {
        channel.id: str(channel.telegram_chat_id or "").strip()
        for channel in load_channels(settings)
    }
    texts = yaml.safe_load(open(f"config/pinned/{args.language}.yaml", encoding="utf-8")) or {}
    ids = (yaml.safe_load(open("config/pinned/ids.yaml", encoding="utf-8")) or {}).get(args.language, {})
    ok = 0
    skipped = 0
    for channel_id, text in texts.items():
        chat_id = channels.get(str(channel_id))
        message_id = ids.get(str(channel_id))
        if not chat_id or not message_id or not str(text or "").strip():
            print(f"{channel_id}: нет chat_id/message_id/текста — пропуск")
            skipped += 1
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
    print(f"итого: {ok}/{len(texts) - skipped} (пропущено: {skipped})")
    return 0 if ok or args.dry_run else 1


if __name__ == "__main__":
    sys.exit(main())
