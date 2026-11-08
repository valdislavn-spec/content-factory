#!/usr/bin/env python3
"""Отправка Telegram-каналов в бесплатный каталог WebGrupos (SEO-трафик).

Каталог: https://webgrupos.net — 11 500+ сообществ, индексация Google/Bing,
постоянная обратная ссылка, без регистрации.

Примеры:
    python scripts/submit_webgrupos.py --channels @AINEWS0007,@SPORTNews0007
    python scripts/submit_webgrupos.py --channels @HOOPY0007 --dry-run  # только preview

Скрипт идемпотентен: если канал уже в каталоге, API вернёт exists и публикация
не выполняется.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from typing import List, Optional, Sequence

BASE = "https://webgrupos.net"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
)


def post(path: str, url: str) -> dict:
    data = urllib.parse.urlencode({"url": url}).encode()
    request = urllib.request.Request(
        BASE + path, data=data,
        headers={"User-Agent": USER_AGENT}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.load(response)


def preview(link: str) -> dict:
    return post("/api/preview_telegram.php", link)


def publish(link: str) -> dict:
    return post("/api/publish_telegram.php", link)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Submit channels to WebGrupos directory")
    parser.add_argument("--channels", required=True,
                        help="каналы через запятую: @username или https://t.me/...")
    parser.add_argument("--dry-run", action="store_true", help="только preview, без публикации")
    parser.add_argument("--delay", type=float, default=2.0, help="пауза между каналами, сек")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    channels: List[str] = [part.strip() for part in args.channels.split(",") if part.strip()]
    ok = 0
    for channel in channels:
        link = channel if channel.startswith("http") else "https://t.me/" + channel.lstrip("@")
        try:
            data = preview(link)
        except Exception as exc:  # noqa: BLE001
            print(f"{channel}: preview error: {exc}")
            continue
        if data.get("exists"):
            print(f"{channel}: уже в каталоге — {data.get('title', '')}")
            continue
        item = data.get("data") or {}
        if not data.get("success") or not item.get("title"):
            print(f"{channel}: preview не удался: {json.dumps(data)[:200]}")
            continue
        print(f"{channel}: {item.get('title')} | {item.get('member_count')} подписчиков")
        if args.dry_run:
            continue
        try:
            result = publish(link)
        except Exception as exc:  # noqa: BLE001
            print(f"{channel}: publish error: {exc}")
            continue
        if result.get("success"):
            listing = "/p/{}-{}".format(result.get("id"), item.get("title", "").lower()
                                        .replace(" & ", "-").replace(" ", "-"))
            print(f"{channel}: опубликовано -> {BASE}{listing}")
            ok += 1
        else:
            print(f"{channel}: публикация не удалась: {json.dumps(result)[:200]}")
        time.sleep(max(args.delay, 0.5))
    print(f"готово: опубликовано {ok} из {len(channels)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
