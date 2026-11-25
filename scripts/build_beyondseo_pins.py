#!/usr/bin/env python3
"""Pinterest pins for Travel Finds, built from the BeyondSEO 2.10.0 audit (2026-11-24).

Six 1000x1500 photo pins with keyword-led titles/descriptions aligned with the
audited page headings (cheap flights, flexible dates, train/bus/plane, city
breaks, US eSIM, US car rental). Renders PNGs + API payloads + bulk CSV.

Run from content-factory:

    PYTHONPATH=$PWD/.render-libs \
      ~/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3 \
      scripts/build_beyondseo_pins.py
"""
from __future__ import annotations

import csv
import json
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.brand.design import (  # noqa: E402
    PIN_SIZE,
    PinContent,
    build_pinterest_payload,
    format_attribution,
    render_pin,
)

SITE = "https://travel-finds.surge.sh"
GUIDES = "https://valdislavn-spec.github.io/content-factory/travel-finds"
TRACKER = "https://links-tracker.valdislav-n.workers.dev/r/"
OUT = ROOT / "docs" / "travel-finds" / "pins"
PHOTOS = ROOT / "docs" / "assets" / "photos"
DISCLOSURE = "Ad · affiliate link"
SITE_LABEL = "travel-finds.surge.sh"


def guide_link(path: str, slug: str) -> str:
    query = urllib.parse.urlencode(
        {"utm_source": "pinterest", "utm_medium": "pin", "utm_campaign": slug}
    )
    return f"{GUIDES}/{path}?{query}"


PINS = [
    {
        "slug": "pin-bs-01-search-dates",
        "photo": "flight",
        "tag": "CHEAP FLIGHTS",
        "headline": "SEARCH EVERY\nDATE",
        "promise": "A month of fares, not one day",
        "cta": "Get the playbook",
        "accent": "#ff7a45",
        "board": "Budget Travel",
        "link": TRACKER + "pin-tf-search-dates",
        "title": "How to find cheap flights in 2026: the 7-step playbook",
        "description": (
            "Cheap flights aren't luck, they're search order. Search a whole month of fares, check "
            "secondary airports, compare the total price instead of the headline fare. The free "
            "7-step playbook. Ad · affiliate links."
        ),
        "keywords": "cheap flights, how to find cheap flights, flexible dates, cheap airfare, travel deals 2026",
    },
    {
        "slug": "pin-bs-02-flexible",
        "photo": "dubai",
        "tag": "FARE MATH",
        "headline": "SHIFT ±2\nDAYS",
        "promise": "Often beats any coupon",
        "cta": "See how",
        "accent": "#10b981",
        "board": "Budget Travel",
        "link": TRACKER + "pin-tf-flexible",
        "title": "Flexible dates, cheaper flights: how shifting ±2 days cuts the fare",
        "description": (
            "The biggest lever on airfare isn't a promo code, it's how flexible your dates are. "
            "Search a month instead of a single day, shift one day each way, look at the edges of "
            "the season, then watch the hidden costs of a cheaper date."
        ),
        "keywords": "flexible dates, cheaper flights, save on flights, flight search tips, travel hacks",
    },
    {
        "slug": "pin-bs-03-transport",
        "photo": "lisbon",
        "tag": "EUROPE",
        "headline": "TRAIN · BUS\n· PLANE",
        "promise": "Door-to-door, not station-to-station",
        "cta": "Compare",
        "accent": "#06b6d4",
        "board": "Travel ideas",
        "link": TRACKER + "pin-tf-transport",
        "title": "Train vs bus vs plane in Europe: which is actually cheaper?",
        "description": (
            "None of them wins every time. Compare door-to-door: a plane adds 2–3 hours of airport "
            "overhead, a night train saves a hotel night, and a bus wins on short hops. Costs, time "
            "and when the slow option is the smart one."
        ),
        "keywords": "train vs bus vs plane, europe travel, cheap transport, city to city, budget travel europe",
    },
    {
        "slug": "pin-bs-04-city-breaks",
        "photo": "europe",
        "tag": "CITY BREAKS 2026",
        "headline": "FIVE COSTS,\nFIVE PICKS",
        "promise": "What a cheap city break really costs",
        "cta": "See the five",
        "accent": "#4f46e5",
        "board": "City Breaks",
        "link": TRACKER + "pin-tf-europe-300",
        "title": "Cheapest city breaks in Europe for 2026: five affordable picks",
        "description": (
            "A cheap city break is five costs stacked: flight, two nights, food, local transport and "
            "extras. Midweek departures and secondary airports usually beat Friday evening. Five "
            "affordable 2026 picks and the booking order that works."
        ),
        "keywords": "cheap city breaks, europe city breaks 2026, budget travel, weekend trips, affordable europe",
    },
    {
        "slug": "pin-bs-05-esim",
        "photo": "esim",
        "tag": "US CONNECTIVITY",
        "headline": "LAND WITH\nDATA",
        "promise": "Install before you fly",
        "cta": "Compare eSIMs",
        "accent": "#db2777",
        "board": "Travel ideas",
        "link": TRACKER + "future-05-esim",
        "title": "Best eSIM for a US trip: Airalo vs Yesim vs Saily",
        "description": (
            "A US eSIM gets you online before you land: install it before you fly, switch it on when "
            "you arrive. Coverage, data plans, activation and how much data a trip actually needs — "
            "Airalo vs Yesim vs Saily compared."
        ),
        "keywords": "us esim, esim for travel, airalo vs yesim vs saily, travel data plan, usa travel",
    },
    {
        "slug": "pin-bs-06-car-rental",
        "photo": "car",
        "tag": "US ROAD TRIP",
        "headline": "9 FEES THAT\nCHANGE THE TOTAL",
        "promise": "The price isn't the price",
        "cta": "Check the list",
        "accent": "#f59e0b",
        "board": "Budget Travel",
        "link": guide_link("guides/us-car-rental.html", "pin-bs-06-car-rental"),
        "title": "US car rental for visitors: 9 fees that change the total",
        "description": (
            "The rental price you see is not the rental price you pay. Insurance, tolls, young-driver "
            "and one-way fees add up fast. Nine charges to check before you book, and the 'total for "
            "stay' view that exposes them."
        ),
        "keywords": "us car rental, car rental fees, rental car insurance, usa road trip, travel fees",
    },
]


def main() -> int:
    credits_path = PHOTOS / "credits.json"
    credits = json.loads(credits_path.read_text(encoding="utf-8")) if credits_path.exists() else {}
    OUT.mkdir(parents=True, exist_ok=True)
    rows, meta = [], []
    for pin in PINS:
        photo_path = PHOTOS / f"{pin['photo']}.jpg"
        if not photo_path.exists():
            print(f"photo missing: {photo_path}", file=sys.stderr)
            return 2
        content = PinContent(
            niche="travel",
            headline=pin["headline"],
            subtitle=pin["promise"],
            cta=pin["cta"],
            link=pin["link"],
            tag=pin["tag"],
            disclosure=DISCLOSURE,
            attribution=format_attribution(credits.get(pin["photo"]) or {}),
            title=pin["title"],
            description=pin["description"],
            accent=pin["accent"],
            site=SITE_LABEL,
        )
        rendered = render_pin(
            content,
            size=PIN_SIZE,
            variants=("photo",),
            photo_path=photo_path,
            qr_data=pin["link"],
            font_dir=ROOT / "assets" / "fonts",
        )["photo"]
        image_path = OUT / f"{pin['slug']}.png"
        rendered.save(image_path)
        image_url = f"{SITE}/pins/{image_path.name}"
        payload = build_pinterest_payload(
            content,
            image_url=image_url,
            board_id="<BOARD_ID>",
            disclosure=DISCLOSURE,
            include_link=True,
        )
        payload.update(
            {
                "board": pin["board"],
                "title": pin["title"],
                "description": pin["description"],
                "link": pin["link"],
                "alt_text": pin["title"],
                "keywords": pin["keywords"],
            }
        )
        meta.append(
            {
                "slug": pin["slug"],
                "file": str(image_path.relative_to(ROOT)),
                "image_url": image_url,
                "payload": payload,
            }
        )
        rows.append(
            {
                "Title": pin["title"],
                "Media URL": image_url,
                "Pinterest board": pin["board"],
                "Thumbnail": "",
                "Description": pin["description"],
                "Link": pin["link"],
                "Publish date": "",
                "Keywords": pin["keywords"],
            }
        )
        print(f"pin: {image_path.name} ({image_path.stat().st_size // 1024} KB)")

    (OUT / "beyondseo-pins.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (OUT / "pinterest-import-beyondseo.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "Title",
                "Media URL",
                "Pinterest board",
                "Thumbnail",
                "Description",
                "Link",
                "Publish date",
                "Keywords",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"OK: {len(PINS)} pins -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
