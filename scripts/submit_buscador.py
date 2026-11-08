#!/usr/bin/env python3
"""Подача каналов в BuscadorTelegram (buscadortelegram.com, ES-каталог).

Открытый JSON API (без капчи/логина):
    GET  /wp-json/bt/v1/fetch-canal?url=https://t.me/<username>  — авто-данные
    POST /wp-json/bt/v1/submit-canal  {"link","name","category","country",
                                       "description","image","email",
                                       "subscribers","website"}

Категории: 34 Criptomonedas, 38 Deportes, 39 Noticias y Medios,
35 Economía y Finanzas, 36 Educacion.
Страны: 77 España, 80 México, 78 Colombia, 79 Perú (пусто = no aplica).
Есть rate-limit: между каналами пауза 60 с; при ответе «Espera un momento…»
скрипт повторяет попытку.

Пример:
    python scripts/submit_buscador.py --channels @HOOPY0007,@AINEWS0007
    python scripts/submit_buscador.py --channels @HOOPY0007 --dry-run
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Sequence

BASE = "https://buscadortelegram.com/wp-json/bt/v1/"
CATEGORIES = {"crypto": "34", "sports": "38", "news": "39", "finance": "35", "education": "36"}
COUNTRIES = {"es": "77", "mx": "80", "co": "78", "pe": "79"}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://buscadortelegram.com",
    "Referer": "https://buscadortelegram.com/anadir-canal/",
}


def api_get(path: str) -> Dict:
    request = urllib.request.Request(BASE + path, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.load(response)


def api_post(path: str, payload: Dict) -> Dict:
    request = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(), headers=HEADERS, method="POST"
    )
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.load(response)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Submit channels to BuscadorTelegram")
    parser.add_argument("--channels", required=True, help="через запятую: @username")
    parser.add_argument("--category", default="crypto", choices=sorted(CATEGORIES))
    parser.add_argument("--country", default="", choices=[""] + sorted(COUNTRIES))
    parser.add_argument("--delay", type=float, default=60.0)
    parser.add_argument("--retries", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    channels: List[str] = [p.strip().lstrip("@") for p in args.channels.split(",") if p.strip()]
    for username in channels:
        link = f"https://t.me/{username}"
        try:
            info = api_get("fetch-canal?url=" + urllib.parse.quote(link))
        except Exception as exc:  # noqa: BLE001
            print(f"{username}: fetch error: {exc}")
            continue
        payload = {
            "link": link,
            "name": info.get("name") or username,
            "category": CATEGORIES[args.category],
            "country": COUNTRIES.get(args.country, ""),
            "description": (info.get("description") or "")[:300],
            "image": info.get("image") or "",
            "email": "",
            "subscribers": str(info.get("subscribers") or ""),
            "website": "",
        }
        print(f"{username}: {payload['name']} | {payload['subscribers']} подписчиков")
        if args.dry_run:
            continue
        sent = False
        for attempt in range(1, max(1, args.retries) + 1):
            try:
                result = api_post("submit-canal", payload)
            except Exception as exc:  # noqa: BLE001
                print(f"{username}: HTTP error {exc}")
                time.sleep(args.delay)
                continue
            if result.get("ok"):
                print(f"{username}: OK — {result.get('msg', '')}")
                sent = True
                break
            print(f"{username}: попытка {attempt}: {result.get('msg')}")
            time.sleep(args.delay)
        if not sent:
            print(f"{username}: не удалось отправить")
        time.sleep(max(args.delay, 5))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
