#!/usr/bin/env python3
"""Travelata package-tour digest for the hub (non-RU departures).

Fetches the cheapest package tours (flight + hotel) from non-Russian departure
cities (Minsk, Astana, ...), builds docs/tours/index.html and a digest for social
posts. Env: TRAVELATA_LOGIN, TRAVELATA_PASSWORD.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.integrations.travelata import TravelataClient  # noqa: E402

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

# non-RU departures only (Kazakhstan, Belarus)
DEPARTURES = [(45, "Minsk"), (9, "Astana"), (5, "Almaty"), (3, "Aktau"), (86, "Shymkent")]
COUNTRIES = [92, 29, 68, 87, 1, 110, 56, 43]  # Turkey, Egypt, UAE, Thailand, Abkhazia, Sri Lanka, Maldives, Cyprus
WINDOWS = [("2026-12-01", "2026-12-20"), ("2026-12-20", "2027-01-10"), ("2027-01-10", "2027-02-05"), ("2027-02-05", "2027-03-01")]
NIGHTS = (5, 9)


def collect(client: TravelataClient, limit: int) -> list:
    rows = []
    for dep_id, dep_name in DEPARTURES:
        for checkin_from, checkin_to in WINDOWS:
            try:
                tours = client.cheapest_tours(countries=COUNTRIES, departure_city=dep_id, adults=2,
                                              checkin_from=checkin_from, checkin_to=checkin_to,
                                              nights_from=NIGHTS[0], nights_to=NIGHTS[1])
            except Exception as error:  # noqa: BLE001
                print("skip", dep_name, checkin_from, str(error)[:80])
                continue
            for tour in tours:
                tour["departure"] = dep_name
                rows.append(tour)
    rows.sort(key=lambda item: int(item.get("price") or 0))
    return rows[:limit]


def render(rows: list, updated: str) -> str:
    cards = []
    for row in rows:
        cards.append(
            '<tr>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4">{row.get("departure")}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4">{row.get("hotelName")} '
            f'<span style="color:#9ca3af">{row.get("hotelCategoryName") or ""}</span></td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4;white-space:nowrap">{row.get("checkinDate")}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4">{row.get("nights")} nights</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4;font-weight:600;white-space:nowrap">{int(row.get("price") or 0):,} ₽'.replace(",", " ") + '</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4"><a href="{row.get("tourPageUrl")}" style="color:#2563eb;text-decoration:none">View tour →</a></td>'
            '</tr>'
        )
    return "\n".join([
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
        '<title>Package tours from Minsk and Astana — live prices</title>',
        '<meta name="description" content="Cheapest package tours (flight + hotel) from Minsk, Astana and Almaty: prices, hotels, dates. Updated daily.">',
        f'<link rel="canonical" href="{PUB}/tours/">',
        '<meta name="robots" content="index,follow">',
        DRIVE + '</head>',
        '<body style="margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#111;background:#fff">',
        '<div style="max-width:900px;margin:0 auto;padding:32px 20px 60px">',
        f'<p style="margin:0 0 18px"><a href="{PUB}/" style="color:#2563eb;text-decoration:none">← All channels</a> · <a href="{PUB}/travel/" style="color:#2563eb;text-decoration:none">Travel guides</a> · <a href="{PUB}/flights/" style="color:#2563eb;text-decoration:none">Flights</a></p>',
        '<p style="color:#6b7280;font-size:13px;text-transform:uppercase;letter-spacing:.08em;margin:0 0 8px">Package tours</p>',
        '<h1 style="font-size:32px;margin:0 0 10px">Tours from Minsk &amp; Astana</h1>',
        f'<p style="color:#6b7280;margin:0 0 22px">Updated {updated} · prices in RUB · flight + hotel included · via Travelata</p>',
        '<table style="width:100%;border-collapse:collapse;font-size:15px">',
        '<thead><tr style="text-align:left;color:#6b7280;font-size:13px;text-transform:uppercase">'
        '<th style="padding:8px 12px">From</th><th style="padding:8px 12px">Hotel</th>'
        '<th style="padding:8px 12px">Check-in</th><th style="padding:8px 12px">Stay</th><th style="padding:8px 12px">Price</th><th style="padding:8px 12px"></th></tr></thead>',
        '<tbody>' + "".join(cards) + '</tbody></table>',
        '<p style="color:#6b7280;font-size:13px;margin-top:20px">Affiliate links. Prices change fast; final price is shown at booking.</p>',
        f'<p style="font-size:14px;color:#374151;margin-top:24px">Also: <a href="{PUB}/flights/almaty/">cheap flights from Almaty</a> · <a href="{PUB}/travel/travel-esim.html">travel eSIM</a> · <a href="{PUB}/travel/airport-transfer-guide.html">airport transfers</a></p>',
        f'<p style="font-size:13px;color:#6b7280;margin-top:22px">© Content Factory · <a href="{PUB}/privacy.html" style="color:#6b7280">Privacy</a> · <a href="{PUB}/terms.html" style="color:#6b7280">Terms</a></p>',
        '</div></body></html>',
    ])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--page", default=str(ROOT / "docs" / "tours" / "index.html"))
    parser.add_argument("--snapshot", default=str(ROOT / "docs" / "tours" / "latest.json"))
    args = parser.parse_args(argv)
    client = TravelataClient.from_env()
    if not client.configured():
        print("TRAVELATA_LOGIN / TRAVELATA_PASSWORD are not set")
        return 2
    rows = collect(client, args.limit)
    if not rows:
        print("no tours found")
        return 1
    updated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    page = Path(args.page)
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(render(rows, updated), encoding="utf-8")
    snapshot = Path(args.snapshot)
    snapshot.write_text(json.dumps({"updated": updated, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("page:", page, "| tours:", len(rows))
    for row in rows[:10]:
        print("  %-8s %-32s %8d ₽ | %s | %s" % (row.get("departure"), str(row.get("hotelName"))[:32],
              int(row.get("price") or 0), row.get("checkinDate"), row.get("nights")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
