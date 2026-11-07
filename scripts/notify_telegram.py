#!/usr/bin/env python3
"""Отправляет сообщение в Telegram (алерты/health) — только stdlib.

Нужны переменные окружения:
  TELEGRAM_BOT_TOKEN       — токен бота
  TELEGRAM_ALERT_CHAT_ID   — chat_id получателя (личка или канал)
Текст: первый аргумент или stdin.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_ALERT_CHAT_ID", "").strip()
    text = " ".join(sys.argv[1:]).strip() or sys.stdin.read().strip()
    if not token or not chat_id:
        print("не заданы TELEGRAM_BOT_TOKEN / TELEGRAM_ALERT_CHAT_ID")
        return 1
    if not text:
        print("пустой текст сообщения")
        return 1
    body = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text[:3900], "disable_web_page_preview": "true"}
    ).encode()
    base = (os.environ.get("TELEGRAM_API_BASE", "") or "https://api.telegram.org").rstrip("/")
    req = urllib.request.Request(
        f"{base}/bot{token}/sendMessage",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.load(resp)
        print("sent:", data.get("ok"), data.get("result", {}).get("message_id"))
        return 0 if data.get("ok") else 1
    except Exception as exc:  # noqa: BLE001
        print(f"ОШИБКА отправки: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
