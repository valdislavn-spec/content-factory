#!/usr/bin/env python3
"""Проверка APILayer: курсы валют и один рейс.

Запуск: python scripts/apilayer_check.py
Локально при Cloudflare 403: APILAYER_SOCKS_PROXY=socks5h://127.0.0.1:1080
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.integrations.apilayer import ApiLayerClient, ApiLayerError  # noqa: E402


def main() -> int:
    client = ApiLayerClient()
    if not client.configured():
        print("APILAYER_KEY не задан")
        return 2
    try:
        rates = client.latest_rates("USD,EUR,RUB")
        print("FX base={} date={} rates={}".format(rates.get("base"), rates.get("date"), rates.get("rates")))
        flights = client.flights(limit=1, dep_iata="SFO")
        rows = flights.get("data") or []
        if rows:
            first = rows[0]
            print(
                "FLIGHT {} {} -> {} status={}".format(
                    first.get("flight_date"),
                    (first.get("departure") or {}).get("iata"),
                    (first.get("arrival") or {}).get("iata"),
                    first.get("flight_status"),
                )
            )
        else:
            print("FLIGHTS пусто")
    except ApiLayerError as exc:
        print("Ошибка: {}".format(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
