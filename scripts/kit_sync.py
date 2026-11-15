#!/usr/bin/env python3
"""Синхронизация подписчиков D1 (наш список) → Kit (ConvertKit).

Нужен KIT_API_SECRET (Developer settings → API Secret). Без секрета работает --dry-run.

  .venv/bin/python scripts/kit_sync.py --dry-run     # показать, что будет отправлено
  .venv/bin/python scripts/kit_sync.py               # создать/обновить подписчиков в Kit
  .venv/bin/python scripts/kit_sync.py --tag "Дайджест"   # + подписать на тег (если тег существует)
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

CF = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CF / "scripts"))
from kit_client import Kit, KitError  # noqa: E402

TRACKER = "https://links-tracker.valdislav-n.workers.dev"


def env(key: str) -> str:
    for line in (CF / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    return ""


def subscribers() -> list[dict]:
    token = env("LINK_TRACKER_ADMIN_TOKEN")
    url = f"{TRACKER}/admin/subscribers?token={token}"
    request = urllib.request.Request(url)
    request.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode()).get("subscribers", [])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--tag", default="")
    args = parser.parse_args()

    people = subscribers()
    if args.limit:
        people = people[: args.limit]
    print(f"подписчиков в D1: {len(people)}")

    kit = Kit()
    print(f"Kit: ключ {kit.key[:6]}…, секрет {'есть' if kit.secret else 'НЕТ'}")

    if args.dry_run or not kit.secret:
        for person in people:
            print(f"  → {person['email']} (lang={person.get('lang')}, source={person.get('source')})")
        if not kit.secret:
            print("без KIT_API_SECRET синхронизация невозможна (v3 требует ключ+секрет для подписчиков)")
        return 0

    tag_id = ""
    if args.tag:
        try:
            for tag in kit.tags():
                if (tag.get("name") or "").lower() == args.tag.lower():
                    tag_id = str(tag.get("id"))
                    break
        except KitError as error:
            print(f"теги: {error}")
        print(f"тег «{args.tag}»: {'id ' + tag_id if tag_id else 'не найден (создай в Kit UI)'}")

    created = failed = 0
    for person in people:
        try:
            out = kit.create_subscriber(person["email"])
            subscriber = out.get("subscriber") or {}
            print(f"  ok {person['email']} id={subscriber.get('id')} state={subscriber.get('state')}")
            created += 1
        except KitError as error:
            print(f"  fail {person['email']}: {error}")
            failed += 1
    print(f"итог: ok={created}, fail={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
