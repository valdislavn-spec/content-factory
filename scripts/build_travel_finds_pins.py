#!/usr/bin/env python3
"""Pinterest pins for the English Travel Finds landing (travel-finds.surge.sh).

Renders 5 photo pins 1000x1500 with the brand design engine (photo background,
scrim, auto-fit headline, disclosure, attribution, QR to the landing page) and
writes the bulk-upload CSV, API payloads, Telegram drafts and the UTM matrix.

Run from content-factory with a Pillow-capable interpreter:

    PYTHONPATH=$PWD/.render-libs \
      ~/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3 \
      scripts/build_travel_finds_pins.py

Outputs (deployed with the site folder):
    docs/travel-finds/pins/pin-XX-*.png (+ meta.json)
    docs/travel-finds/pins/pinterest-import.csv
    docs/travel-finds/pins/telegram-posts-en.md
    docs/travel-finds/pins/utm-links.md
"""
from __future__ import annotations

import csv
import json
import sys
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
OUT = ROOT / "docs" / "travel-finds" / "pins"
PHOTOS = ROOT / "docs" / "assets" / "photos"
DISCLOSURE = "Ad · affiliate link"
BOARD = "Travel Finds | Deals"
SITE_LABEL = "travel-finds.surge.sh"


def source_link(source: str, medium: str) -> str:
    return f"{SITE}/?utm_source={source}&utm_medium={medium}&utm_campaign=travelfinds"


PINS = [
    {
        "slug": "pin-01-search-dates",
        "photo": "flight",
        "tag": "SEARCH EVERY DATE",
        "headline": "CHEAP FLIGHTS\n+ HOTELS",
        "promise": "Compare fares across flexible dates, not just one",
        "cta": "Find deals",
        "accent": "#ff7a45",
        "title": "Cheap flights + hotels: search every date instead of one",
        "description": (
            "A flexible-date search beats a fixed one: compare a whole month of fares at once and "
            "pick the cheapest day to fly. Free tools, no hidden fees, ad · affiliate links."
        ),
        "keywords": "cheap flights, hotel deals, flexible dates, travel deals, flight search, 2026",
    },
    {
        "slug": "pin-02-europe-300",
        "photo": "europe",
        "tag": "CITY BREAKS",
        "headline": "EUROPE FOR\nUNDER $300",
        "promise": "Flights + 3 nights, no tourist traps",
        "cta": "See the guide",
        "accent": "#4f46e5",
        "title": "Europe for under $300: real cheap city breaks",
        "description": (
            "How to do 3 nights in a European city on a $300 budget: cheapest months, carry-on only, "
            "Mon–Wed departures and the booking window that actually saves money."
        ),
        "keywords": "cheap europe, city breaks, budget travel, europe under 300, weekend trips",
    },
    {
        "slug": "pin-03-flexible",
        "photo": "lisbon",
        "tag": "FARE MATH",
        "headline": "FLEXIBLE DATES\n= CHEAPER",
        "promise": "Shift by ±3 days, save up to 40%",
        "cta": "Learn the trick",
        "accent": "#10b981",
        "title": "Flexible dates = cheaper flights: shift ±3 days, save up to 40%",
        "description": (
            "Why shifting a trip by a few days changes the fare, which weekdays are cheapest to fly, "
            "and how to compare a whole date grid in one search."
        ),
        "keywords": "flexible dates, cheap flights, how to save on flights, travel hacks",
    },
    {
        "slug": "pin-04-book-window",
        "photo": "dubai",
        "tag": "TIMING",
        "headline": "BOOK 6–8\nWEEKS AHEAD",
        "promise": "The sweet spot for cheap fares",
        "cta": "Read the math",
        "accent": "#db2777",
        "title": "When to book flights: the 6–8 week window",
        "description": (
            "Booking too early and too late both cost more. Here is the timing window that usually "
            "captures the lowest fare, by season and route."
        ),
        "keywords": "when to book flights, booking window, travel timing, cheap fares",
    },
    {
        "slug": "pin-05-train-bus-plane",
        "photo": "bali",
        "tag": "EUROPE",
        "headline": "TRAIN · BUS\n· PLANE",
        "promise": "Pick the cheapest way between cities",
        "cta": "Compare routes",
        "accent": "#06b6d4",
        "title": "Train vs bus vs plane: the cheapest way across Europe",
        "description": (
            "A side-by-side comparison of train, bus and plane for city-to-city hops in Europe: "
            "real costs, time, and when the slow option wins."
        ),
        "keywords": "train vs bus vs plane, europe travel, cheap transport, city to city",
    },
]


def telegram_posts(link: str) -> str:
    return f"""# Telegram EN — Travel Finds landing

Links already carry UTM: `utm_source=telegram`. Add “Ad · affiliate links” where the platform requires it.

## Post 1 — flexible dates

✈️ **Stop searching one date. Search the whole month.**

A fixed-date search shows you one fare. A flexible search shows you the cheapest day in the window — often 20–40% less.

Full guide + free comparison tips:
👉 {link}

## Post 2 — Europe under $300

🌍 **3 nights in Europe for under $300 — actually possible**

The math: cheapest months, carry-on only, Mon–Wed departures, 6–8 week booking window.

Breakdown:
👉 {link}

## Post 3 — train vs bus vs plane

🚆 **Train, bus or plane? It depends on the route — here is the comparison**

Sometimes the 6-hour bus beats a 1-hour flight once transfers and bags are added.

👉 {link}
"""


def utm_matrix() -> str:
    rows = [
        ("Pinterest (organic)", source_link("pinterest", "organic")),
        ("Telegram (channel)", source_link("telegram", "channel")),
        ("Email newsletter", source_link("email", "newsletter")),
        ("Reddit", source_link("reddit", "social")),
        ("Facebook page", source_link("facebook", "social")),
        ("TikTok bio", source_link("tiktok", "bio")),
        ("Instagram bio", source_link("instagram", "bio")),
    ]
    table = "\n".join(f"| {name} | {url} |" for name, url in rows)
    return f"""# UTM links — Travel Finds

| Source | Link |
|---|---|
{table}

## Measurement note

UTM tags need an analytics counter on the page (none yet) or the project's own click tracker
(`links-tracker.valdislav-n.workers.dev`). Without either, the only visible signal is
Travelpayouts click/conversion reports for the partner links.
"""


def main() -> int:
    credits_path = PHOTOS / "credits.json"
    credits = json.loads(credits_path.read_text(encoding="utf-8")) if credits_path.exists() else {}
    OUT.mkdir(parents=True, exist_ok=True)
    link = source_link("pinterest", "organic")
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
            link=link,
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
            qr_data=link,
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
                "board": BOARD,
                "title": pin["title"],
                "description": pin["description"],
                "link": link,
                "alt_text": pin["title"],
                "keywords": pin["keywords"],
            }
        )
        meta.append({"slug": pin["slug"], "file": str(image_path.relative_to(ROOT)), "image_url": image_url, "payload": payload})
        rows.append(
            {
                "Title": pin["title"],
                "Media URL": image_url,
                "Pinterest board": BOARD,
                "Thumbnail": "",
                "Description": pin["description"],
                "Link": link,
                "Publish date": "",
                "Keywords": pin["keywords"],
            }
        )
        print(f"pin: {image_path.name} ({image_path.stat().st_size // 1024} KB)")

    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (OUT / "pinterest-import.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["Title", "Media URL", "Pinterest board", "Thumbnail", "Description", "Link", "Publish date", "Keywords"])
        writer.writeheader()
        writer.writerows(rows)
    (OUT / "telegram-posts-en.md").write_text(telegram_posts(source_link("telegram", "channel")), encoding="utf-8")
    (OUT / "utm-links.md").write_text(utm_matrix(), encoding="utf-8")
    print(f"OK: {len(PINS)} pins -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
