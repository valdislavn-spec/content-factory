"""Render the next batch of Travel Finds Pinterest pins."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from content_factory.brand.design import (  # noqa: E402
    PIN_SIZE,
    PinContent,
    build_pinterest_payload,
    format_attribution,
    render_pin,
)

SITE = "https://travel-finds.surge.sh"
TRACKER = "https://links-tracker.valdislav-n.workers.dev/r/"
OUT = ROOT / "docs" / "travel-finds" / "pins"
PHOTOS = ROOT / "docs" / "assets" / "photos"
DISCLOSURE = "Ad · affiliate link"

PINS = [
    {
        "slug": "future-01-lisbon-48h", "photo": "lisbon", "tag": "CITY BREAK",
        "headline": "48 HOURS\nIN LISBON", "promise": "Pastel de nata, miradouros, no queue",
        "cta": "See the route", "accent": "#f59e0b", "board": "City Breaks",
        "title": "48 hours in Lisbon: the compact city-break route",
        "description": "Two days in Lisbon without the tourist-trap tax: where to stay, which tram pass is worth it, the miradouros that are free, and the pastel de nata queue that moves fastest. Ad · affiliate links.",
        "keywords": "lisbon, city break, 48 hours, portugal, budget travel",
    },
    {
        "slug": "future-02-bali-budget", "photo": "bali", "tag": "BUDGET",
        "headline": "BALI ON\nA BUDGET", "promise": "3 nights without the resort markup",
        "cta": "Get the budget", "accent": "#10b981", "board": "Budget Travel",
        "title": "Bali on a budget: 3 nights without the resort markup",
        "description": "Bali can be cheap or painfully expensive. The difference is where you sleep, how you move and which breakfast is included. A realistic 3-night budget with the traps to skip. Ad · affiliate links.",
        "keywords": "bali, budget travel, indonesia, cheap hotels, 3 nights",
    },
    {
        "slug": "future-03-dubai-weekend", "photo": "dubai", "tag": "WEEKEND",
        "headline": "DUBAI IN\n3 DAYS", "promise": "Skip the overpriced tourist traps",
        "cta": "Plan the weekend", "accent": "#0ea5e9", "board": "Travel ideas",
        "title": "Dubai in 3 days: a weekend without overpaying",
        "description": "A 3-day Dubai route that mixes the free skyline views with one paid experience worth it. Where to stay, how to use the metro and which tours to skip. Ad · affiliate links.",
        "keywords": "dubai, weekend, 3 days, uae, travel ideas",
    },
    {
        "slug": "future-04-carry-on", "photo": "flight", "tag": "PACK LIGHT",
        "headline": "CARRY-ON\nONLY", "promise": "7 days, one bag, zero fees",
        "cta": "Get the list", "accent": "#ef4444", "board": "Travel ideas",
        "title": "Carry-on only: 7 days with one bag",
        "description": "The packing list that fits a week into a 40-litre carry-on, the airline fees it avoids, and the three items that are not worth the space. Ad · affiliate links.",
        "keywords": "carry-on, packing list, hand luggage, travel hacks",
    },
    {
        "slug": "future-05-esim", "photo": "esim", "tag": "STAY ONLINE",
        "headline": "TRAVEL eSIM\nTHAT WORKS", "promise": "Coverage, data and activation",
        "cta": "Compare eSIMs", "accent": "#8b5cf6", "board": "Budget Travel",
        "title": "Travel eSIM that works abroad: coverage, data and activation",
        "description": "A travel eSIM should activate before you land and work on the networks you actually need. Compare coverage, data limits, hotspot rules and the real per-GB price. Ad · affiliate links.",
        "keywords": "esim, travel internet, data plan, roaming, travel tech",
    },
    {
        "slug": "future-06-insurance", "photo": "car", "tag": "DON'T LOSE COVER",
        "headline": "INSURANCE\nMISTAKES", "promise": "5 errors that void your policy",
        "cta": "Check the policy", "accent": "#f97316", "board": "Travel ideas",
        "title": "Travel insurance mistakes that void your policy",
        "description": "Five common travel-insurance mistakes that can void a claim: undeclared medical conditions, missed excess, adventure-sport exclusions, late purchase and no police report. Ad · affiliate links.",
        "keywords": "travel insurance, claims, policy, travel safety",
    },
]


def main() -> int:
    credits_path = PHOTOS / "credits.json"
    credits = json.loads(credits_path.read_text(encoding="utf-8")) if credits_path.exists() else {}
    OUT.mkdir(parents=True, exist_ok=True)
    meta = []
    for pin in PINS:
        photo_path = PHOTOS / f"{pin['photo']}.jpg"
        if photo_path.exists() is False:
            print("photo missing: " + str(photo_path), file=sys.stderr)
            return 2
        code = pin["slug"]
        link = TRACKER + code
        content = PinContent(
            niche="travel", headline=pin["headline"], subtitle=pin["promise"],
            cta=pin["cta"], link=link, tag=pin["tag"], disclosure=DISCLOSURE,
            attribution=format_attribution(credits.get(pin["photo"]) or {}),
            title=pin["title"], description=pin["description"],
            accent=pin["accent"], site="travel-finds.surge.sh",
        )
        rendered = render_pin(
            content, size=PIN_SIZE, variants=("photo",), photo_path=photo_path,
            qr_data=link, font_dir=ROOT / "assets" / "fonts",
        )["photo"]
        image_path = OUT / (pin["slug"] + ".png")
        rendered.save(image_path)
        payload = build_pinterest_payload(
            content, image_url=SITE + "/pins/" + image_path.name,
            board_id="<BOARD_ID>", disclosure=DISCLOSURE, include_link=True,
        )
        payload.update({
            "board": pin["board"], "title": pin["title"], "description": pin["description"],
            "link": link, "alt_text": pin["title"], "keywords": pin["keywords"],
        })
        meta.append({
            "id": code, "slug": pin["slug"], "file": str(image_path.relative_to(ROOT)),
            "image_url": SITE + "/pins/" + image_path.name, "payload": payload,
            "board": pin["board"], "title": pin["title"], "description": pin["description"],
            "link": link,
        })
        print("pin: " + image_path.name + " (" + str(image_path.stat().st_size // 1024) + " KB)")
    (OUT / "future-pins.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("OK: " + str(len(meta)) + " pins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
