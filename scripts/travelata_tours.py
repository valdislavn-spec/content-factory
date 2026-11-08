#!/usr/bin/env python3
"""Travelata tours: fetch cheapest tours via partners API or summarize the weekly feed.

Examples:
    python scripts/travelata_tours.py --feed data/travelata_tours.csv --top 10
    TRAVELATA_LOGIN=... TRAVELATA_PASSWORD=... python scripts/travelata_tours.py \
        --countries 92 --departure 2 --from 2026-12-01 --to 2026-12-10 --nights 6 8 --top 5

API access: Travelata issues credentials individually after the project is connected
to the Travelata program (Travelpayouts campaign 18) and a support request is sent.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.integrations.travelata import TravelataClient, TravelataError, parse_feed  # noqa: E402


def summarize(rows, top: int):
    rows = sorted(rows, key=lambda r: r.get("price") or 0)
    for row in rows[:top]:
        if "hotelName" in row:  # API row
            print("%-42s %8.0f RUB | %2s nights | %s | %s | %s" % (
                str(row.get("hotelName"))[:42], float(row.get("price") or 0), row.get("nights"),
                row.get("hotelCategoryName"), row.get("checkinDate"), row.get("tourPageUrl", "")[:70]))
        else:  # feed row
            print("%-42s %8d RUB | %2s nights | %-16s | %s | %s" % (
                str(row.get("Название отеля"))[:42], int(row.get("price") or 0),
                row.get("Среднее количество ночей"), row.get("Курорт", "")[:16],
                row.get("Страна", ""), str(row.get("Ссылка на отель", ""))[:60]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", help="path to Travelata weekly feed CSV (UTF-16 tab-separated)")
    parser.add_argument("--save-json", default="")
    parser.add_argument("--countries", nargs="*", type=int, default=[], help="country IDs (e.g. 92 = Turkey)")
    parser.add_argument("--departure", type=int, default=2, help="departure city ID (2 = Moscow)")
    parser.add_argument("--adults", type=int, default=2)
    parser.add_argument("--from", dest="checkin_from", default="")
    parser.add_argument("--to", dest="checkin_to", default="")
    parser.add_argument("--nights", nargs=2, type=int, default=[], help="min max nights")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args(argv)

    if args.feed:
        data = Path(args.feed).read_bytes()
        rows = parse_feed(data)
        print("feed rows:", len(rows))
        summarize(rows, args.top)
        if args.save_json:
            Path(args.save_json).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            print("saved:", args.save_json)
        return 0

    client = TravelataClient.from_env()
    if not client.configured():
        print("Travelata API is not configured: set TRAVELATA_LOGIN / TRAVELATA_PASSWORD")
        print("Access is issued by Travelata after connecting the program (campaign 18) and sending a support request.")
        return 2
    if not args.countries or not args.checkin_from or not args.checkin_to:
        print("--countries, --from, --to are required for API mode")
        return 2
    try:
        tours = client.cheapest_tours(
            countries=args.countries,
            departure_city=args.departure,
            adults=args.adults,
            checkin_from=args.checkin_from,
            checkin_to=args.checkin_to,
            nights_from=args.nights[0] if args.nights else None,
            nights_to=args.nights[1] if len(args.nights) > 1 else None,
        )
    except TravelataError as error:
        print("Travelata API error:", error)
        return 1
    print("tours:", len(tours))
    summarize(tours, args.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
