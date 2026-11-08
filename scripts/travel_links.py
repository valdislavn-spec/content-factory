#!/usr/bin/env python3
"""Travelpayouts: цены + аффилиатные ссылки Aviasales по маркеру.

Использование:
    python scripts/travel_links.py --origin MOW --limit 5
    python scripts/travel_links.py --origin MOW --destination DXB --json out.json

Требует TRAVELPAYOUTS_API_TOKEN и TRAVELPAYOUTS_MARKER в .env.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, ".")
from content_factory.utils import load_dotenv  # noqa: E402

API = "https://api.travelpayouts.com"


def _env() -> tuple[str, str]:
    load_dotenv(".env")
    import os

    token = os.environ.get("TRAVELPAYOUTS_API_TOKEN", "")
    marker = os.environ.get("TRAVELPAYOUTS_MARKER", "")
    if not token or not marker:
        raise SystemExit("нет TRAVELPAYOUTS_API_TOKEN/TRAVELPAYOUTS_MARKER в .env")
    return token, marker


def _get(path: str, params: dict) -> dict:
    url = API + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "content-factory/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def affiliate_link(marker: str, origin: str, destination: str, depart_at: str) -> str:
    """Ссылка на поиск Aviasales с маркером (ддмм из даты)."""
    try:
        d = dt.date.fromisoformat(depart_at[:10])
        ddmm = d.strftime("%d%m")
    except Exception:
        ddmm = ""
    path = f"/search/{origin}{ddmm}{destination}1"
    return f"https://aviasales.ru{path}?marker={urllib.parse.quote(marker)}"


def city_directions(origin: str, token: str, limit: int) -> list[dict]:
    data = _get("/v1/city-directions", {"origin": origin, "token": token, "currency": "rub"})
    if not data.get("success"):
        raise SystemExit(f"API error: {data}")
    rows = []
    for dest, item in list(data.get("data", {}).items())[:limit]:
        rows.append({
            "origin": origin,
            "destination": dest,
            "price_rub": item.get("price"),
            "airline": item.get("airline"),
            "departure_at": item.get("departure_at"),
            "return_at": item.get("return_at"),
            "transfers": item.get("transfers"),
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--origin", default="MOW")
    ap.add_argument("--destination")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--json", dest="json_path")
    args = ap.parse_args()

    token, marker = _env()
    if args.destination:
        data = _get("/v1/prices/cheap", {
            "origin": args.origin, "destination": args.destination,
            "token": token, "currency": "rub",
        })
        rows = []
        for dest, items in data.get("data", {}).items():
            for _, item in items.items():
                rows.append({
                    "origin": args.origin, "destination": dest,
                    "price_rub": item.get("price"),
                    "airline": item.get("airline"),
                    "departure_at": item.get("departure_at"),
                    "return_at": item.get("return_at"),
                })
    else:
        rows = city_directions(args.origin, token, args.limit)

    for r in rows:
        r["affiliate_url"] = affiliate_link(marker, r["origin"], r["destination"], r.get("departure_at") or "")

    print(f"Маркер: {marker} | направлений: {len(rows)}")
    for r in rows:
        print(f"{r['origin']}→{r['destination']}: {r['price_rub']} ₽ | {r.get('departure_at','')[:10]} | {r['affiliate_url']}")

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=1)
        print("JSON:", args.json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
