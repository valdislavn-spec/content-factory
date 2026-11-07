#!/usr/bin/env python3
"""Рассылка предложений о ВП/обмене рекламы владельцам каналов (Telethon).

Нужен user-session (не бот): TG_API_ID, TG_API_HASH, TG_SESSION (StringSession).
По умолчанию dry-run — только печатает сообщения. Реальная отправка: --live.

    python scripts/vp_outreach.py --region en --limit 5
    python scripts/vp_outreach.py --region en --live --limit 3

Список берётся из docs/promo/outreach-tracker.csv (status=prospect).
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "docs/promo/outreach-tracker.csv"

OUR = {
    "en": {
        "name": "Crypto & Blockchain",
        "url": "https://t.me/HOOPY0007",
        "stats": "3.7k subscribers, ~165 views/post, US crypto news",
    },
    "es": {
        "name": "ES Sports Analytics",
        "url": "https://t.me/SPORTSAnalytics007",
        "stats": "nuevo canal de deporte con datos y cuotas (18+)",
    },
}


def build_message(row: dict, region: str) -> str:
    if region == "es":
        return (
            "Hola 👋 Llevamos ES Sports Analytics — deporte con datos, cuotas y "
            "análisis (18+). Estamos buscando canales de deporte en español para "
            "un intercambio nativo: nuestro post en tu canal a cambio de uno tuyo "
            "en el nuestro (24–48 h, sin spam ni casino). También podemos empezar "
            "con un post pagado pequeño ($3–8) para probar el resultado. "
            f"¿Te interesa? Nuestro canal: {OUR['es']['url']}"
        )
    try:
        target_views = int(float(row.get("avg_views") or 0))
    except ValueError:
        target_views = 0
    offer = (
        "2:1 (two posts on our side for one on yours)"
        if target_views >= 250
        else "1:1"
    )
    return (
        f"Hey! We run {OUR['en']['name']} ({OUR['en']['stats']}). "
        "We're setting up a few native cross-promos this month — "
        f"{offer}, 24–48h each, no money involved. Native post, no casino/scam. "
        f"Would you be up for a swap this week? {OUR['en']['url']}"
    )


def load_rows(region: str, limit: int) -> list[dict]:
    with TRACKER.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    selected = []
    for row in rows:
        if (row.get("status") or "").strip().lower() not in ("", "prospect"):
            continue
        row_region = (row.get("region") or "").strip().upper()
        if region != "all" and row_region and row_region.lower() != region.lower():
            continue
        partner = (row.get("contact") or row.get("partner") or "").strip()
        if not partner:
            continue
        if not partner.startswith("@"):
            partner = "@" + partner
        row["_target"] = partner
        selected.append(row)
    return selected[:limit]


async def send(args: argparse.Namespace) -> int:
    rows = load_rows(args.region, args.limit)
    if not rows:
        print("Нет целей со статусом prospect в трекере.")
        return 0
    api_id = os.environ.get("TG_API_ID", "").strip()
    api_hash = os.environ.get("TG_API_HASH", "").strip()
    session = os.environ.get("TG_SESSION", "").strip()

    if not args.live:
        if not (api_id and api_hash and session):
            print("Сессия не задана: только dry-run (сообщения ниже).")
        for row in rows:
            region = args.region if args.region != "all" else (row.get("region") or "en").lower()
            print(f"\n--- {row['_target']} ---\n{build_message(row, region)}")
        return 0
    if not (api_id and api_hash and session):
        print("Нет TG_API_ID/TG_API_HASH/TG_SESSION — отправка невозможна.", file=sys.stderr)
        return 2

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        print("Нужен Telethon: pip install 'Telethon>=1.34'", file=sys.stderr)
        return 2
    async with TelegramClient(StringSession(session), int(api_id), api_hash) as client:
        me = await client.get_me()
        print(f"Отправка от @{getattr(me, 'username', me.id)}; целей: {len(rows)}")
        for row in rows:
            target = row["_target"]
            region = args.region if args.region != "all" else (row.get("region") or "en").lower()
            text = build_message(row, region)
            print(f"\n--- {target} ---\n{text}")
            try:
                await client.send_message(target, text)
                print(f"OK: отправлено {target}")
            except Exception as exc:  # noqa: BLE001 - не роняем рассылку из-за одного контакта
                print(f"FAIL {target}: {exc}", file=sys.stderr)
            pause = random.uniform(args.min_delay, args.max_delay)
            print(f"пауза {pause:.0f} c")
            await asyncio.sleep(pause)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ВП/реклама: рассылка владельцам каналов")
    parser.add_argument("--region", choices=["en", "es", "all"], default="en")
    parser.add_argument("--limit", type=int, default=5, help="сколько контактов за запуск")
    parser.add_argument("--live", action="store_true", help="реально отправить (по умолчанию dry-run)")
    parser.add_argument("--min-delay", type=float, default=20.0)
    parser.add_argument("--max-delay", type=float, default=45.0)
    args = parser.parse_args()
    return asyncio.run(send(args))


if __name__ == "__main__":
    raise SystemExit(main())
