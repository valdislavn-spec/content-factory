#!/usr/bin/env python3
"""Cheapest flights digest: Aviasales data API → hub /flights/ page + printable digest.

Idea: daily feed of the cheapest round-trip deals from the chosen origin (city-directions),
each with a Travelpayouts partner link. Output:
  * docs/flights/index.html — SEO landing page with the deals table (Drive + affiliate CTAs)
  * data/flights/latest.json — snapshot for price-drop tracking
  * stdout — digest lines for Telegram/Buffer

Env: TRAVELPAYOUTS_TOKEN (data API), TRAVELPAYOUTS_MARKER, TRAVELPAYOUTS_TRS (link conversion).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.integrations.aviasales import AviasalesClient, search_path  # noqa: E402

PUB = "https://valdislavn-spec.github.io/content-factory"
DRIVE = '''  <!-- Travelpayouts Drive -->
  <script nowprocket data-noptimize="1" data-cfasync="false" data-wpfc-render="false" seraph-accel-crit="1" data-no-defer="1" data-cmp-ab="2">
    (function () {
        var script = document.createElement("script");
        script.async = 1;
        script.setAttribute("data-cmp-ab", "2");
        script.src = 'https://emrld.ltd/NTk3Njcy.js?t=597672';
        document.head.appendChild(script);
    })();
  </script>
'''

CITY_NAMES = {
    "IST": "Istanbul", "AYT": "Antalya", "EVN": "Yerevan", "TAS": "Tashkent", "DYU": "Dushanbe",
    "LED": "St. Petersburg", "AER": "Sochi", "KGD": "Kaliningrad", "MCX": "Makhachkala", "SKD": "Samarkand",
    "BKK": "Bangkok", "DXB": "Dubai", "TBS": "Tbilisi", "GYD": "Baku", "ALA": "Almaty", "MSQ": "Minsk",
    "BEG": "Belgrade", "CXR": "Nha Trang", "HKT": "Phuket", "DPS": "Bali", "BCN": "Barcelona", "ROM": "Rome",
    "PAR": "Paris", "LON": "London", "MIL": "Milan", "ATH": "Athens", "LCA": "Larnaca", "MLE": "Maldives",
    "PEK": "Beijing", "SHA": "Shanghai", "HKG": "Hong Kong", "DEL": "Delhi", "GOI": "Goa", "CMB": "Colombo",
}

COMPARE = [
    ("https://aviasales.tpk.ro/b3PI8GVN", "Compare all flights"),
    ("https://www.aviasales.ru/?marker=674170", "Search on Aviasales"),
]


def pretty_city(code: str) -> str:
    return CITY_NAMES.get(code.upper(), code.upper())


def format_dates(item: dict) -> str:
    dep = str(item.get("departure_at") or "")[:10]
    ret = str(item.get("return_at") or "")[:10]
    return f"{dep} → {ret}" if ret else dep


def build_rows(items: list, partner_links: dict) -> list:
    rows = []
    for item in items:
        dest = str(item.get("destination") or "").upper()
        price = int(item.get("price") or item.get("value") or 0)
        if not dest or price <= 0:
            continue
        rows.append({
            "destination": dest,
            "city": pretty_city(dest),
            "price": price,
            "airline": str(item.get("airline") or "").upper(),
            "dates": format_dates(item),
            "found_at": str(item.get("found_at") or item.get("departure_at") or "")[:16].replace("T", " "),
            "link": partner_links.get(dest) or search_path(item.get("link", "")),
        })
    rows.sort(key=lambda row: row["price"])
    return rows


def convert_links(client_links, items, currency_origin: str) -> dict:
    """Convert aviasales search URLs to Travelpayouts partner links (batch ≤10).

    The links API returns results in the same order as the request, so we map
    the i-th response to the i-th input item.
    """
    if not client_links or not client_links.configured():
        return {}
    by_dest = {}
    for start in range(0, len(items), 10):
        chunk_items = items[start:start + 10]
        chunk = []
        for item in chunk_items:
            dest = str(item.get("destination") or "").upper()
            if not dest:
                continue
            chunk.append({"url": search_path(item.get("link", "")), "sub_id": "flights_" + dest.lower()})
        if not chunk:
            continue
        try:
            converted = client_links.convert(chunk)
        except Exception as error:  # noqa: BLE001
            print("convert failed:", str(error)[:120])
            continue
        paired = list(zip(chunk, converted))
        for request_item, response_item in paired:
            partner = str((response_item or {}).get("partner_url") or "")
            if not partner:
                continue
            url = str(request_item.get("url") or "")
            for item in chunk_items:
                dest = str(item.get("destination") or "").upper()
                if dest and search_path(item.get("link", "")) == url:
                    by_dest[dest] = partner
                    break
    return by_dest


def render_page(rows: list, origin: str, updated: str) -> str:
    table = []
    for row in rows:
        table.append(
            '<tr>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4">{row["city"]} <span style="color:#9ca3af">({row["destination"]})</span></td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4;white-space:nowrap">{row["dates"]}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4">{row["airline"]}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4;font-weight:600;white-space:nowrap">{row["price"]:,} ₽'.replace(",", " ") + '</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4"><a href="{row["link"]}" style="color:#2563eb;text-decoration:none">Book →</a></td>'
            '</tr>'
        )
    schema = json.dumps({
        "@context": "https://schema.org", "@type": "ItemList",
        "name": f"Cheapest flights from {origin}", "url": f"{PUB}/flights/",
        "numberOfItems": len(rows),
    })
    return "\n".join([
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>Cheapest flights from {origin} — deals updated daily</title>',
        f'<meta name="description" content="Cheapest round-trip flights from {origin}: live Aviasales deals with dates, airlines and prices. Updated daily.">',
        f'<link rel="canonical" href="{PUB}/flights/">',
        '<meta name="robots" content="index,follow">',
        f'<script type="application/ld+json">{schema}</script>',
        DRIVE + '</head>',
        '<body style="margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#111;background:#fff">',
        '<div style="max-width:860px;margin:0 auto;padding:32px 20px 60px">',
        f'<p style="margin:0 0 18px"><a href="{PUB}/" style="color:#2563eb;text-decoration:none">← All channels</a> · <a href="{PUB}/travel/" style="color:#2563eb;text-decoration:none">Travel guides</a></p>',
        '<p style="color:#6b7280;font-size:13px;text-transform:uppercase;letter-spacing:.08em;margin:0 0 8px">Flight deals</p>',
        f'<h1 style="font-size:32px;margin:0 0 10px">Cheapest flights from {origin}</h1>',
        f'<p style="color:#6b7280;margin:0 0 22px">Updated {updated} · prices in RUB · round-trip unless noted · via Aviasales</p>',
        '<table style="width:100%;border-collapse:collapse;font-size:15px">',
        '<thead><tr style="text-align:left;color:#6b7280;font-size:13px;text-transform:uppercase">'
        '<th style="padding:8px 12px">Destination</th><th style="padding:8px 12px">Dates</th>'
        '<th style="padding:8px 12px">Airline</th><th style="padding:8px 12px">Price</th><th style="padding:8px 12px"></th></tr></thead>',
        '<tbody>' + "".join(table) + '</tbody></table>',
        '<p style="margin:24px 0 6px"><a href="https://aviasales.tpk.ro/b3PI8GVN" style="display:inline-block;background:#f59e0b;color:#111;font-weight:600;padding:12px 20px;border-radius:100px;text-decoration:none">Compare all flights →</a></p>',
        '<p style="color:#6b7280;font-size:13px">Ad · affiliate link. Prices change fast; the price is fixed at booking.</p>',
        f'<p style="font-size:14px;color:#374151;margin-top:26px">Read more: <a href="{PUB}/travel/europe-under-300.html">Europe for under $300</a> · <a href="{PUB}/travel/bali-budget.html">Bali on a budget</a> · <a href="{PUB}/travel/travel-esim.html">Travel eSIM</a></p>',
        f'<p style="font-size:13px;color:#6b7280;margin-top:22px">© Content Factory · <a href="{PUB}/privacy.html" style="color:#6b7280">Privacy</a> · <a href="{PUB}/terms.html" style="color:#6b7280">Terms</a></p>',
        '</div></body></html>',
    ])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", default="MOW")
    parser.add_argument("--currency", default="rub")
    parser.add_argument("--top", type=int, default=12)
    parser.add_argument("--page", default=str(ROOT / "docs" / "flights" / "index.html"))
    parser.add_argument("--snapshot", default=str(ROOT / "data" / "flights" / "latest.json"))
    args = parser.parse_args(argv)

    client = AviasalesClient.from_env()
    if not client.configured():
        print("TRAVELPAYOUTS_TOKEN is not set")
        return 2
    try:
        items = client.city_directions(origin=args.origin, currency=args.currency)
    except Exception as error:  # noqa: BLE001
        print("Aviasales API error:", error)
        return 1
    if not items:
        print("no deals returned")
        return 1
    items.sort(key=lambda item: int(item.get("price") or item.get("value") or 10**9))
    items = items[: args.top]

    # city-directions has no deep link: fetch prices_for_dates for each top destination
    for item in items:
        dest = str(item.get("destination") or "").upper()
        dep = str(item.get("departure_at") or "")[:10]
        if not dest or not dep:
            continue
        try:
            offers = client.prices_for_dates(args.origin, dest, dep, currency=args.currency, limit=1)
        except Exception:  # noqa: BLE001
            continue
        if offers:
            item["link"] = offers[0].get("link") or ""

    partner_links = {}
    try:
        from content_factory.integrations.travelpayouts import TravelpayoutsClient
        partner_links = convert_links(TravelpayoutsClient.from_env(), items, args.origin)
    except Exception as error:  # noqa: BLE001
        print("link conversion skipped:", error)

    rows = build_rows(items, partner_links)
    updated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")

    page_path = Path(args.page)
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(render_page(rows, args.origin.upper(), updated), encoding="utf-8")
    print("page:", page_path)

    snapshot = Path(args.snapshot)
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(json.dumps({
        "origin": args.origin.upper(), "updated": updated, "currency": args.currency, "rows": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("snapshot:", snapshot)

    for row in rows[:8]:
        print("  %-14s %-8s %8d ₽  %s → %s" % (row["city"], row["airline"], row["price"], row["dates"], row["link"][:60]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
