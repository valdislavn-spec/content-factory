#!/usr/bin/env python3
"""Нативные кросс-промо-посты между каналами сети (EN+ES).

Публикует один пост за запуск; запись и вариант текста выбираются
детерминированно по дню UTC — состояние хранить не нужно.

    python scripts/cross_promo.py --dry-run
    python scripts/cross_promo.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)


def load_channels() -> dict:
    mapping = {}
    for lang in ("en", "es"):
        path = f"config/channels.{lang}.yaml"
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        for channel in data.get("channels") or []:
            mapping[str(channel.get("id"))] = {
                "chat_id": str(channel.get("telegram_chat_id") or ""),
                "title": channel.get("title") or channel.get("id"),
                "lang": lang,
            }
    return mapping


def token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def send(chat_id: str, text: str) -> dict:
    base = (os.environ.get("TELEGRAM_API_BASE", "") or "https://api.telegram.org").rstrip("/")
    body = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}
    ).encode()
    request = urllib.request.Request(
        f"{base}/bot{token()}/sendMessage",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def pick_entry(entries: list, day_index: int) -> tuple:
    weighted = []
    for entry in entries:
        weighted.extend([entry] * max(1, int(entry.get("weight", 1))))
    entry = weighted[day_index % len(weighted)]
    texts = entry.get("texts") or [""]
    variant = (day_index // len(weighted)) % len(texts)
    return entry, texts[variant]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    with open("config/cross_promo.yaml", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}
    entries = [item for item in config.get("entries") or [] if item.get("enabled", True)]
    if not entries:
        print("cross-promo: нет записей")
        return 0
    channels = load_channels()
    day_index = (datetime.now(timezone.utc).date() - datetime(2026, 1, 1, tzinfo=timezone.utc).date()).days
    entry, text = pick_entry(entries, day_index)
    source = str(entry.get("source") or "")
    channel = channels.get(source)
    if not channel or not channel["chat_id"]:
        print(f"cross-promo: канал-источник {source!r} не найден")
        return 1
    if args.dry_run:
        print(f"[dry-run] {source} -> {entry.get('target')}:")
        print(text)
        return 0
    if not token():
        print("cross-promo: нет TELEGRAM_BOT_TOKEN")
        return 1
    result = send(channel["chat_id"], text)
    ok = bool(result.get("ok"))
    print(f"cross-promo: {source} -> {entry.get('target')} · ok={ok} · msg={result.get('result', {}).get('message_id')}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
