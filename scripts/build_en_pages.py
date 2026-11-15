#!/usr/bin/env python3
"""Английские версии: /en/ хаб + 12 страниц направлений, hreflang-пары с русскими.

Тексты — английские оригиналы (не машинный перевод), цены те же из сводки Travelata.

  .venv/bin/python scripts/build_en_pages.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

CF = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CF / "scripts"))

from build_destination_pages import CSS, DATES, DESTINATIONS, GH, UPDATED, esc  # noqa: E402

DOCS = CF / "docs"
EN = {
    "turciya": {"name": "Turkey", "lead": "The most popular foreign destination of the season: sea, "
                "all-inclusive hotels and a wide choice of resorts from Antalya to Bodrum.",
                "hl": ["All-inclusive hotels", "Flight + hotel package", "Sea and pools", "Family friendly"]},
    "egipet": {"name": "Egypt", "lead": "Warm in winter: the Red Sea, coral reefs, diving and "
               "all-inclusive resorts within a short flight.", "hl": ["Red Sea reefs", "Diving and snorkelling",
               "Warm in December", "All-inclusive hotels"]},
    "oae": {"name": "UAE", "lead": "Dubai and the other emirates: beaches, malls, theme parks and a "
            "short flight.", "hl": ["Beaches and water parks", "Shopping", "Modern hotels", "Warm winter"]},
    "tailand": {"name": "Thailand", "lead": "Phuket, Pattaya and the islands: warm sea, street food "
                "and hotels for every budget.", "hl": ["Phuket and Pattaya", "Islands and tours",
                                                       "Warm sea", "Any budget"]},
    "maldivy": {"name": "Maldives", "lead": "Atolls and overwater villas — the most expensive beach "
                "destination in the digest, with a wide price range across hotels.",
                "hl": ["Overwater villas", "Crystal water", "Snorkelling", "Honeymoon"]},
    "kipr": {"name": "Cyprus", "lead": "The Mediterranean and a short flight: quiet holidays and trips "
            "with children.", "hl": ["Mediterranean sea", "Short flight", "Beaches", "Quiet holidays"]},
    "greciya": {"name": "Greece", "lead": "Mainland Greece and the islands: sea, ancient sites and "
                "European service.", "hl": ["Islands", "Ancient sites", "Mediterranean sea", "City walks"]},
    "vietnam": {"name": "Vietnam", "lead": "Long coastline and low prices: Nha Trang, Phu Quoc and "
                "Da Nang with beach hotels and street food.", "hl": ["Long beaches", "Cheap hotels",
                                                                     "Street food", "Winter sun"]},
    "indoneziya": {"name": "Indonesia", "lead": "Bali: rice terraces, temples, surf spots and pool "
                   "villas — a trip beyond the beach.", "hl": ["Rice terraces", "Temples", "Surfing",
                                                               "Pool villas"]},
    "ispaniya": {"name": "Spain", "lead": "Barcelona and Mallorca: architecture, food, city beaches "
                 "and island coves.", "hl": ["City and sea", "Food and wine", "Architecture", "Island coves"]},
    "italiya": {"name": "Italy", "lead": "Rome, Milan and the coast: art, food and the most expensive "
                "packages of the digest.", "hl": ["Art and history", "Food", "Coast", "Shopping"]},
    "abkhaziya": {"name": "Abkhazia", "lead": "The cheapest destination in the digest: Black Sea "
                  "pebbles, subtropical greenery and short trips from Russia.",
                  "hl": ["Lowest price", "Black Sea", "Mountains", "Short trip"]},
}

ABROAD = GH + "/flight-hotel-abroad/"


def en_url(slug: str) -> str:
    return f"{GH}/en/destinations/{slug}/"


def graph(url: str, name: str, slug: str, faq: list[tuple[str, str]]) -> dict:
    return {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "@id": url + "#page", "url": url, "inLanguage": "en", "name": name},
        {"@type": "BreadcrumbList", "@id": url + "#crumb", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": GH + "/en/"},
            {"@type": "ListItem", "position": 2, "name": "Destinations", "item": GH + "/en/"},
            {"@type": "ListItem", "position": 3, "name": name, "item": url}]},
        {"@type": "Product", "@id": url + "#offer", "name": name,
         "description": "Return flight and hotel package",
         "offers": {"@type": "Offer", "priceCurrency": "RUB",
                    "price": DESTINATIONS[[d["slug"] for d in DESTINATIONS].index(slug)]["price"].replace(" ", ""),
                    "availability": "https://schema.org/InStock", "url": url}},
        {"@type": "FAQPage", "@id": url + "#faq", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faq]}]}


def page(slug: str, d: dict, cfg: dict, title: str, desc: str) -> str:
    url = en_url(slug)
    price = d["price"]
    faq = [
        (f"How much is a trip to {cfg['name']} for two?",
         f"The lowest price in the Travelata digest as of {UPDATED} is {price} RUB for two, "
         f"flight and hotel included."),
        ("What is included?",
         "A package of return flight and hotel accommodation. Exact hotels and dates are listed on the "
         "partner page."),
        ("When is this price valid?",
         f"Travel dates of the digest: {DATES}. Check availability for your dates on the partner page."),
    ]
    tags = "".join(f'<span class="tag">{esc(t)}</span>' for t in cfg["hl"])
    sub = f"""
<section class="sub"><h2>Weekly travel digest</h2>
<p>Best package prices to 12 countries once a week. No spam.</p>
<form onsubmit="return false" action="{GH}/en/" method="post">
<input type="email" name="email" placeholder="you@example.com" required>
<button type="submit">Subscribe</button>
</form></section>
"""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<link rel="alternate" hreflang="en" href="{url}">
<link rel="alternate" hreflang="ru" href="{GH}/destinations/{slug}/">
<link rel="alternate" hreflang="x-default" href="{url}">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{GH}/destinations/og/{slug}.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<style>{CSS}</style>
<script type="application/ld+json">{json.dumps(graph(url, cfg['name'], slug, faq), ensure_ascii=False)}</script>
</head><body><div class="wrap">
<p class="crumb"><a href="{GH}/en/">Home</a> → <a href="{GH}/en/">Destinations</a> → {esc(cfg['name'])}</p>
<h1>{esc(cfg['name'])}: packages from {esc(price)} ₽ for two</h1>
<div class="price"><b>{esc(price)} ₽</b><span>for two · flight + hotel</span></div>
<div class="tags">{tags}</div>
<p class="lead">{esc(cfg['lead'])}</p>
<p><a class="btn" href="{ABROAD}?lang=en">See current offers →</a></p>
<p class="note">Lowest price in the digest as of {UPDATED}; travel dates {DATES}. Not an offer.</p>
{sub}
<nav><a href="{GH}/en/">All destinations</a><a href="{GH}/destinations/{slug}/">Русская версия</a>
<a href="{ABROAD}">Price digest</a></nav>
<footer>Prices: Travelata digest · {UPDATED} · for two, flight + hotel.</footer>
</div></body></html>
"""


def hub() -> str:
    url = GH + "/en/"
    cards = "".join(
        f'<a class="card" href="{en_url(d["slug"])}"><b>{esc(EN[d["slug"]]["name"])}</b>'
        f'<span>from {esc(d["price"])} ₽ · {esc(d["nights"])}</span></a>' for d in DESTINATIONS)
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "CollectionPage", "@id": url + "#page", "url": url, "inLanguage": "en",
         "name": "Travel packages to 12 countries"},
        {"@type": "ItemList", "@id": url + "#list", "itemListElement": [
            {"@type": "ListItem", "position": i, "name": EN[d["slug"]]["name"],
             "url": en_url(d["slug"])} for i, d in enumerate(DESTINATIONS, 1)]}]}
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Travel packages to 12 countries: prices for two — winter 2026/2027</title>
<meta name="description" content="Package prices for two: Turkey from 41 754 ₽, Egypt from 74 015 ₽, UAE from 66 704 ₽, Thailand from 98 739 ₽, Maldives from 155 760 ₽. Flight and hotel included.">
<link rel="canonical" href="{url}">
<link rel="alternate" hreflang="en" href="{url}">
<link rel="alternate" hreflang="ru" href="{GH}/destinations/">
<meta name="robots" content="index,follow,max-image-preview:large">
<style>{CSS}</style>
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
</head><body><div class="wrap">
<p class="crumb">Home → Destinations</p>
<h1>Travel packages to 12 countries</h1>
<p class="lead">Lowest package prices for two, flight and hotel included. Travel dates {DATES}, digest updated {UPDATED}.</p>
<div class="grid">{cards}</div>
<p><a class="btn" href="{ABROAD}?lang=en">Full price digest →</a></p>
<nav><a href="{GH}/destinations/">Русская версия</a><a href="{GH}/">Home</a></nav>
<footer>Prices: Travelata digest · {UPDATED} · for two, flight + hotel · not an offer.</footer>
</div></body></html>
"""


def main() -> int:
    created = []
    for d in DESTINATIONS:
        cfg = EN[d["slug"]]
        target = DOCS / "en" / "destinations" / d["slug"] / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        title = f"{cfg['name']} packages from {d['price']} ₽ for two — winter 2026/2027"
        desc = (f"{cfg['name']} travel packages for two from {d['price']} ₽: flight and hotel included, "
                f"{d['nights']}, travel dates {DATES}.")
        target.write_text(page(d["slug"], d, cfg, title, desc), encoding="utf-8")
        created.append(en_url(d["slug"]))
    hub_path = DOCS / "en" / "index.html"
    hub_path.parent.mkdir(parents=True, exist_ok=True)
    hub_path.write_text(hub(), encoding="utf-8")
    created.append(GH + "/en/")

    sitemap = DOCS / "sitemap.xml"
    xml = sitemap.read_text(encoding="utf-8")
    extra = []
    for loc in created:
        if f"<loc>{loc}</loc>" not in xml:
            extra.append(f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>2026-11-15</lastmod>\n"
                         f"    <changefreq>weekly</changefreq>\n    <priority>0.7</priority>\n  </url>")
    if extra:
        sitemap.write_text(xml.replace("</urlset>", "\n".join(extra) + "\n</urlset>"), encoding="utf-8")
    print(f"EN страниц: {len(created)} | в sitemap: {len(extra)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
