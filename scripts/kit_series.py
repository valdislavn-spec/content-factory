#!/usr/bin/env python3
"""Серия брендированных рассылок Kit по направлениям (RU), расписание 16–22.11.

Идемпотентно: если рассылка с такой темой уже есть — пропускаем.
  .venv/bin/python scripts/kit_series.py --dry-run
  .venv/bin/python scripts/kit_series.py --create
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

CF = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CF / "scripts"))
from brand_email import build  # noqa: E402
from kit_v4 import KitV4  # noqa: E402

TAG_ID = 25918468  # «Дайджест»
# (день, страна, цена, ночи, фраза)
SERIES = [
    ("2026-11-16", "Турция", "41 754", "5–9 ночей", "в Турцию"),
    ("2026-11-17", "Египет", "74 015", "5–9 ночей", "в Египет"),
    ("2026-11-18", "ОАЭ", "66 704", "5–9 ночей", "в ОАЭ"),
    ("2026-11-19", "Таиланд", "98 739", "5–9 ночей", "в Таиланд"),
    ("2026-11-20", "Мальдивы", "155 760", "5–9 ночей", "на Мальдивы"),
    ("2026-11-21", "Абхазия", "18 473", "5 ночей", "в Абхазию"),
    ("2026-11-22", "Италия", "240 442", "5–9 ночей", "в Италию"),
]


def variant(country: str, price: str, nights: str, phrase: str) -> tuple[str, str]:
    subject = f"Тур {phrase}: от {price} ₽ за двоих — ноябрь–декабрь 2026"
    html = build("ru", "reader@example.com")
    html = html.replace("Куда поехать в декабре", f"Тур {phrase}")
    html = html.replace("12 зарубежных направлений с минимальными ценами за двоих",
                        f"{country}: перелёт + отель, {nights}, минимальная цена из сводки")
    html = html.replace("от 18 473 ₽", f"от {price} ₽")
    return subject, html


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--create", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    kit = KitV4()
    existing = {b.get("subject") for b in kit.get("/broadcasts").get("broadcasts", [])}
    print(f"уже есть рассылок: {len(existing)}")
    for day, country, price, nights, phrase in SERIES:
        subject, html = variant(country, price, nights, phrase)
        if subject in existing:
            print(f"skip: {subject}")
            continue
        if not args.create:
            print(f"план {day} 09:00 PST | {subject} | {len(html)//1024} KB")
            continue
        send_at = f"{day}T17:00:00Z"
        try:
            out = kit.create_broadcast(subject=subject, content=html, description="travel series",
                                       send_at=send_at, preview_text=f"{country} от {price} ₽",
                                       subscriber_filter=[{"all": [{"type": "tag", "ids": [TAG_ID]}]}])
            b = out.get("broadcast", {})
            print(f"создано {b.get('id')} | {send_at} | {subject}")
        except Exception as error:  # noqa: BLE001
            print(f"ошибка {country}: {type(error).__name__}: {str(error)[:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
