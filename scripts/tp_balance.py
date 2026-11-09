#!/usr/bin/env python3
"""Travelpayouts: баланс, следующая выплата и история выплат.

    python scripts/tp_balance.py
    python scripts/tp_balance.py --json out.json

Требует TRAVELPAYOUTS_API_TOKEN в .env / окружении.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.integrations.travelpayouts import TravelpayoutsClient, TravelpayoutsError  # noqa: E402
from content_factory.utils import load_dotenv  # noqa: E402


def programs_count() -> int:
    try:
        import yaml

        data = yaml.safe_load((ROOT / "config" / "affiliate_links.yaml").read_text(encoding="utf-8")) or {}
        return len((data.get("programs") or {}))
    except Exception:  # noqa: BLE001
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path", default="")
    args = parser.parse_args()
    load_dotenv(str(ROOT / ".env"))
    token = os.environ.get("TRAVELPAYOUTS_API_TOKEN", "").strip()
    marker = os.environ.get("TRAVELPAYOUTS_MARKER", "").strip()
    client = TravelpayoutsClient(token=token, marker=marker, trs=os.environ.get("TRAVELPAYOUTS_TRS", "597672"))
    try:
        balance = client.balance()
        payout = client.next_payout()
        payments = client.payments(limit=5)
    except TravelpayoutsError as error:
        print("Ошибка Travelpayouts:", error)
        return 1
    print("Баланс: $" + str(balance.get("usd", "0")) + " / €" + str(balance.get("eur", "0")) + " / " + str(balance.get("rub", "0")) + " ₽")
    print("Следующая выплата: $" + str(payout.get("usd", "0")))
    print("Подключено программ: %d" % programs_count())
    print("Выплат: %d" % len(payments))
    for payment in payments[:5]:
        print("  •", payment.get("paid_at"), "$" + str(payment.get("amount")), payment.get("currency"))
    if args.json_path:
        Path(args.json_path).write_text(json.dumps({"balance": balance, "next_payout": payout, "payments": payments}, ensure_ascii=False, indent=1), encoding="utf-8")
        print("JSON:", args.json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
