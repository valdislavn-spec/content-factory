#!/usr/bin/env python3
"""Photo pins v5 (Pinterest best practices) rendered with the brand design engine.

Real Commons photo background + contrast scrim, auto-fit headline (<=3 lines),
keyword pill, subtitle, CTA pill, QR + disclosure footer and mandatory photo
attribution for CC BY / CC BY-SA.  Every pin is a 1000x1500 PNG plus a JSON
sidecar with the Pinterest payload and measured QA metrics.

Usage:
    python scripts/build_photo_pins.py                       # docs/assets/pins/photo
    PYTHONPATH=/tmp/segno <dsh-python> scripts/build_photo_pins.py --out docs/assets/pins-v5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.integrations.partner_links import (
    check_links_live,
    load_partner_links,
    resolve_program_link,
    validate_link,
)
from content_factory.brand.design import (  # noqa: E402
    DISCLOSURE_AFFILIATE,
    PIN_SIZE,
    PinContent,
    board_for_niche,
    build_pinterest_payload,
    format_attribution,
    keywords_for,
    render_pin,
)

#: Photo pin definitions.  ``program`` names an affiliate program from
#: ``config/affiliate_links.yaml``; its partner URL is the pin destination and QR target.
PINS = [
    {
        "slug": "bali-budget-qr",
        "photo": "bali",
        "niche": "travel",
        "tag": "BUDGET",
        "headline": "BALI ON\nA BUDGET",
        "promise": "7 days of rice terraces, surf and $3 meals",
        "cta": "Find flights",
        "program": "aviasales",
        "accent": "#80DCAA",
        "title": "Bali on a budget: 7 days of rice terraces and $3 meals",
        "description": (
            "A 7-day Bali budget plan: cheap rice-terrace stays, where to eat for $3 "
            "and how to get around without overspending."
        ),
    },
    {
        "slug": "dubai-weekend-qr",
        "photo": "dubai",
        "niche": "travel",
        "tag": "WEEKEND",
        "headline": "DUBAI IN\n3 DAYS",
        "promise": "Desert dunes, skyline and duty-free \u2014 one carry-on",
        "cta": "Find flights",
        "program": "aviasales",
        "accent": "#FFC45C",
        "title": "Dubai in 3 days: desert, skyline and a carry-on weekend",
        "description": (
            "A 3-day Dubai weekend itinerary: desert dunes, the skyline, "
            "duty-free and how to do it with one carry-on bag."
        ),
    },
    {
        "slug": "winter-sun-qr",
        "photo": "lisbon",
        "niche": "travel",
        "tag": "WINTER SUN",
        "headline": "3 WINTER\nESCAPES",
        "promise": "Lisbon 15\u00b0C \u00b7 Dubai 25\u00b0C \u00b7 Bali 30\u00b0C",
        "cta": "Find flights",
        "program": "aviasales",
        "accent": "#78C4FF",
        "title": "3 winter sun escapes: Lisbon, Dubai and Bali",
        "description": (
            "Three winter sun destinations compared: Lisbon 15C, Dubai 25C and "
            "Bali 30C, with the best months and flight tips."
        ),
    },
    {
        "slug": "europe-under-300-qr",
        "photo": "europe",
        "niche": "travel",
        "tag": "BUDGET",
        "headline": "EUROPE\nUNDER $300",
        "promise": "A 3-night city break: cheapest months and booking windows",
        "cta": "Find flights",
        "program": "aviasales",
        "accent": "#FF8CA0",
        "title": "Europe under $300: cheap city breaks by month",
        "description": (
            "How to book a 3-night European city break under $300: "
            "cheapest months, carry-on rules and the best booking window."
        ),
    },
    {
        "slug": "travel-esim-qr",
        "photo": "esim",
        "niche": "travel",
        "tag": "TRAVEL ESSENTIAL",
        "headline": "TRAVEL eSIM\nTHAT WORKS",
        "promise": "Install before you fly \u2014 data in 200+ countries",
        "cta": "Get eSIM",
        "program": "yesim",
        "accent": "#A896FF",
        "title": "Travel eSIM that works: install before you fly",
        "description": (
            "How a travel eSIM works, when it beats airport SIM cards and how to "
            "install one before you fly for data in 200+ countries."
        ),
    },
    {
        "slug": "car-rental-qr",
        "photo": "car",
        "niche": "travel",
        "tag": "TRAVEL ESSENTIAL",
        "headline": "CAR RENTAL\nNO SURPRISES",
        "promise": "Local renters, clear fuel policy, excess cover",
        "cta": "Rent a car",
        "program": "localrent",
        "accent": "#FFA06E",
        "title": "Car rental without surprises: fuel policy and excess cover",
        "description": (
            "How to rent a car without hidden fees: local renters, full-to-full "
            "fuel policy, excess cover and the best booking window."
        ),
    },
    {
        "slug": "flight-compensation-qr",
        "photo": "flight",
        "niche": "travel",
        "tag": "TRAVEL MONEY",
        "headline": "FLIGHT\nDELAYED?",
        "promise": "You may be owed up to \u20ac600 \u2014 check in 2 minutes",
        "cta": "Check my flight",
        "program": "compensair",
        "accent": "#78F0DC",
        "title": "Flight delayed? Check if you are owed up to 600 EUR",
        "description": (
            "Flight delayed or cancelled? What EU261 compensation you may be "
            "owed (up to 600 EUR), and a 2-minute way to check your flight."
        ),
    },
]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Render photo pins (v5 design engine)")
    parser.add_argument("--photos", default=str(ROOT / "docs" / "assets" / "photos"))
    parser.add_argument("--out", default=str(ROOT / "docs" / "assets" / "pins" / "photo"))
    parser.add_argument("--limit", type=int, default=0, help="max pins (0 = all)")
    parser.add_argument("--no-qr", action="store_true", help="omit QR codes from the footer")
    parser.add_argument(
        "--check-links",
        action="store_true",
        help="live-check every resolved partner link (HTTP 2xx/3xx) before rendering",
    )
    args = parser.parse_args(argv)

    try:
        import PIL  # noqa: F401
    except ImportError:
        print(
            "Pillow is required to render pins.\n"
            "Use the DSH python: PYTHONPATH=/tmp/segno <dsh-python> scripts/build_photo_pins.py",
            file=sys.stderr,
        )
        return 2

    photos = Path(args.photos)
    out = Path(args.out)
    credits_path = photos / "credits.json"
    credits = json.loads(credits_path.read_text(encoding="utf-8")) if credits_path.exists() else {}
    pins = PINS[: args.limit] if args.limit else PINS
    out.mkdir(parents=True, exist_ok=True)
    public_base = "https://valdislavn-spec.github.io/content-factory"
    partner_links = load_partner_links()
    resolved_links = {}
    for item in pins:
        link = resolve_program_link(item.get("program"), partner_links, fallback=public_base + "/")
        problems = validate_link(link)
        if problems:
            print("pin %s: неактивная ссылка: %s" % (item["slug"], "; ".join(problems)), file=sys.stderr)
            return 2
        resolved_links[item["slug"]] = link
    if args.check_links:
        print("live-check partner links:")
        bad = []
        for check in check_links_live(resolved_links.values()):
            print("  %-4s %s -> %s" % (check.status or "ERR", check.url, check.reason or check.final_url))
            if not check.ok:
                bad.append(check.url)
        if bad:
            print("неактивные ссылки: %s" % ", ".join(bad), file=sys.stderr)
            return 2
    meta = []
    for pin in pins:
        photo_path = photos / ("%s.jpg" % pin["photo"])
        if not photo_path.exists():
            print("photo missing: %s (skipped)" % photo_path, file=sys.stderr)
            continue
        credit = credits.get(pin["photo"]) or {}
        content = PinContent(
            niche=pin["niche"],
            headline=pin["headline"],
            subtitle=pin["promise"],
            cta=pin["cta"],
            link=resolved_links[pin["slug"]],
            tag=pin["tag"],
            disclosure=DISCLOSURE_AFFILIATE,
            attribution=format_attribution(credit),
            title=pin["title"],
            description=pin["description"],
            accent=pin["accent"],
        )
        try:
            rendered = render_pin(
                content,
                size=PIN_SIZE,
                variants=("photo",),
                photo_path=photo_path,
                qr_data="" if args.no_qr else resolved_links[pin["slug"]],
                font_dir=ROOT / "assets" / "fonts",
            )["photo"]
        except Exception as error:  # noqa: BLE001
            print("pin %s failed quality gates: %s" % (pin["slug"], error), file=sys.stderr)
            return 3
        image_path = out / ("%s.png" % pin["slug"])
        rendered.save(image_path)
        try:
            relative = image_path.resolve().relative_to((ROOT / "docs").resolve()).as_posix()
        except ValueError:
            relative = image_path.name
        image_url = "%s/%s" % (public_base, relative)
        payload = build_pinterest_payload(
            content,
            image_url=image_url,
            board_id="<BOARD_ID>",
            disclosure=DISCLOSURE_AFFILIATE,
            include_link=True,
        )
        board = board_for_niche(pin["niche"])
        keywords = keywords_for(pin["niche"], pin["title"], pin["description"], pin["promise"])
        entry = {
            "image_url": image_url,
            "link": resolved_links[pin["slug"]],
            "file": str(image_path),
            "slug": pin["slug"],
            "niche": pin["niche"],
            "affiliate": True,
            "disclosure": DISCLOSURE_AFFILIATE,
            "board": board,
            "keywords": list(keywords),
            "variant": "photo",
            "pin": payload,
            "metrics": rendered.metrics.to_dict(),
        }
        sidecar = out / ("%s.json" % pin["slug"])
        sidecar.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
        meta.append(entry)
        print(
            "pin: %s (%d KB) minfont=%d body=%.2f heading=%.2f margins=%s"
            % (
                image_path,
                image_path.stat().st_size // 1024,
                rendered.metrics.min_font_size,
                rendered.metrics.min_body_contrast,
                rendered.metrics.min_heading_contrast,
                rendered.metrics.margins,
            )
        )
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "index.json").write_text(
        json.dumps({"engine": "brand.design", "variant": "photo", "pins": meta}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("done: %d photo pins in %s" % (len(meta), out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
