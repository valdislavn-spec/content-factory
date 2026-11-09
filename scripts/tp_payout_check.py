#!/usr/bin/env python3
"""Проверка готовности к выплате Travelpayouts: баланс, пороги, окно выплат.

    python scripts/tp_payout_check.py

Способы для резидента РФ (минимумы):
    WebMoney WMZ        — 10 USD
    карта/счёт физлица  — 1 000 ₽ (Restaff, НДФЛ 13%)
    самозанятый         — 1 000 ₽
    ИП/юрлицо           — 10 000 ₽
    валютный перевод    — 400 USD (недоступен в РФ)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.integrations.travelpayouts import TravelpayoutsClient, TravelpayoutsError  # noqa: E402
from content_factory.utils import load_dotenv  # noqa: E402

THRESHOLDS = [
    ("WebMoney WMZ", 10.0, "USD"),
    ("Карта/счёт физлица (Restaff)", 1000.0, "RUB"),
    ("Самозанятый", 1000.0, "RUB"),
    ("ИП/юрлицо", 10000.0, "RUB"),
    ("Валютный перевод (недоступен РФ)", 400.0, "USD"),
]


def _today() -> datetime:
    return datetime.now(timezone.utc)


def main() -> int:
    load_dotenv(str(ROOT / ".env"))
    token = os.environ.get("TRAVELPAYOUTS_API_TOKEN", "").strip()
    client = TravelpayoutsClient(
        token=token,
        marker=os.environ.get("TRAVELPAYOUTS_MARKER", "").strip(),
        trs=os.environ.get("TRAVELPAYOUTS_TRS", "597672"),
    )
    try:
        balance = client.balance()
        payout = client.next_payout()
        payments = client.payments(limit=5)
    except TravelpayoutsError as error:
        print("Ошибка Travelpayouts:", error)
        return 1

    usd = float(str(balance.get("usd") or 0).replace(",", "."))
    rub = float(str(balance.get("rub") or 0).replace(",", "."))
    print("Баланс: $%.2f / %.2f ₽" % (usd, rub))
    print("Следующая выплата: $%s" % payout.get("usd", "0"))
    print("Выплат получено: %d" % len(payments))
    print("\nПороги выплат:")
    reached = []
    for name, threshold, currency in THRESHOLDS:
        value = usd if currency == "USD" else rub
        ready = value >= threshold
        if ready and "недоступен" not in name:
            reached.append(name)
        print("  %-38s %8.2f %s  %s" % (name, threshold, currency, "✅ баланс позволяет" if ready else "— рано"))

    now = _today()
    print("\nОкно выплат: 10–20 число каждого месяца (сейчас %s)" % now.strftime("%d.%m.%Y"))
    if reached:
        print("Можно получить: " + ", ".join(reached))
        print("Если способ ещё не добавлен: app.travelpayouts.com/finance/requisites")
    else:
        print("До первой выплаты не хватает: WMZ $%.2f или карта РФ %.2f ₽" % (max(0, 10 - usd), max(0, 1000 - rub)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
