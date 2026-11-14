#!/usr/bin/env python3
"""Проверка Discord-webhook: отправляет тестовое сообщение и удаляет его.

    DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/... python scripts/discord_probe.py
    python scripts/discord_probe.py --keep        # не удалять сообщение

Печатает: имя сервера/канала, id сообщения, результат удаления.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

UA = "Mozilla/5.0 (compatible; ContentFactory/1.0)"


def call(url: str, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json", "User-Agent": UA},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            body = response.read().decode("utf-8", "replace")
            return response.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"raw": body[:200]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="не удалять тестовое сообщение")
    parser.add_argument("--text", default="Content Factory: проверка webhook. Сообщение удалится автоматически.")
    args = parser.parse_args()

    url = (os.environ.get("DISCORD_WEBHOOK_URL", "") or "").strip()
    if not url.startswith("https://discord.com/api/webhooks/"):
        print("DISCORD_WEBHOOK_URL не задан или неверного формата")
        return 2

    status, info = call(url + "?wait=true", "POST", {"content": args.text})
    if status not in (200, 204):
        print(f"ОТПРАВКА НЕ УДАЛАСЬ: HTTP {status} {json.dumps(info, ensure_ascii=False)[:300]}")
        return 1

    message_id = str(info.get("id") or "")
    channel_id = str(info.get("channel_id") or "")
    guild_id = str(info.get("guild_id") or "")
    print(f"отправлено: message_id={message_id} channel={channel_id} guild={guild_id}")

    if guild_id and channel_id:
        s, guild = call(f"https://discord.com/api/v10/guilds/{guild_id}")
        if s == 200:
            print(f"сервер: {guild.get('name')}")

    if not args.keep and message_id:
        s, _ = call(f"{url}/messages/{message_id}", "DELETE")
        print("удаление:", "ok" if s in (200, 204) else f"HTTP {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
