#!/usr/bin/env python3
"""Проверка инлайн-кнопки под фото-карточкой на живом канале.

Отправляет одну карточку с кнопкой, ждёт N секунд и удаляет сообщение.
Нужен для проверки, что reply_markup принимается Telegram.

    python scripts/telegram_card_probe.py --chat-env TELEGRAM_CHAT_ID_FUTBOL_ES

Печатает: message_id, наличие кнопки в ответе, результат удаления.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from content_factory.utils import env, load_dotenv  # noqa: E402

UA = "Mozilla/5.0 (compatible; ContentFactory/1.0) AppleWebKit/537.36 Chrome/124"


def api_base() -> str:
    return (env("TELEGRAM_API_BASE", "") or "https://api.telegram.org").rstrip("/")


def call(token: str, method: str, payload: dict) -> dict:
    body = urllib.parse.urlencode({k: v for k, v in payload.items() if v is not None}).encode()
    request = urllib.request.Request(
        f"{api_base()}/bot{token}/{method}", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": UA}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read().decode("utf-8", "replace") or "{}")


def send_photo(token: str, chat_id: str, photo: Path, markup: str, caption: str) -> dict:
    boundary = "----CF" + uuid.uuid4().hex
    parts = []
    for name, value in (("chat_id", chat_id), ("caption", caption), ("reply_markup", markup)):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"{photo.name}\"\r\n"
        f"Content-Type: image/png\r\n\r\n".encode()
    )
    parts.append(photo.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)
    request = urllib.request.Request(
        f"{api_base()}/bot{token}/sendPhoto", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": UA}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read().decode("utf-8", "replace") or "{}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chat-env", default="TELEGRAM_CHAT_ID_FUTBOL_ES")
    parser.add_argument("--keep", action="store_true", help="не удалять сообщение")
    parser.add_argument("--card", default="assets/avatars/signals.png")
    parser.add_argument("--channel-url", default="https://t.me/SPORTSAnalytics007")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    token = (env("TELEGRAM_BOT_TOKEN", "") or "").strip()
    chat_id = (os.environ.get(args.chat_env, "") or "").strip()
    if not token or not chat_id:
        print(f"нет токена или {args.chat_env}")
        return 2

    photo = ROOT / args.card
    markup = json.dumps({"inline_keyboard": [[{"text": "Проверка кнопки", "url": args.channel_url}]]}, ensure_ascii=False)
    result = send_photo(token, chat_id, photo, markup, "Проверка кнопки под карточкой — сообщение будет удалено")
    if not result.get("ok"):
        print("ОТПРАВКА НЕ УДАЛАСЬ:", json.dumps(result, ensure_ascii=False)[:400])
        return 1
    message_id = str((result.get("result") or {}).get("message_id") or "")
    print(f"отправлено: message_id={message_id}")
    print("кнопка в ответе:", "да" if (result.get("result") or {}).get("reply_markup") else "нет данных")

    if not args.keep and message_id:
        time.sleep(4)
        deleted = call(token, "deleteMessage", {"chat_id": chat_id, "message_id": message_id})
        print("удаление:", "ok" if deleted.get("ok") else json.dumps(deleted, ensure_ascii=False)[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
