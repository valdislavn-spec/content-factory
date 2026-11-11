#!/usr/bin/env python3
"""Generate travel guide pages on the hub (docs/travel/) + refresh sitemap.

Each article is a static SEO page with Article schema, internal links, affiliate CTA
and the Travelpayouts Drive snippet. Used to build organic traffic for the hub and to
satisfy affiliate program requirements (travel content).
"""

from __future__ import annotations

import json
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
TRAVEL = DOCS / "travel"
PUB = "https://valdislavn-spec.github.io/content-factory"
TODAY = "2026-11-11"

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

ARTICLES = [
    {
        "slug": "europe-under-300",
        "title": "Europe for under $300: real cheap city breaks",
        "headline": "Europe for under $300",
        "desc": "How to plan a 3-night European city break under $300: cheapest months, carry-on tips and booking windows.",
        "intro": "A 3-night European city break for under $300 is possible if you pick the right month, fly carry-on only and book 6–8 weeks ahead. Here is the exact playbook we use.",
        "sections": [
            ("When to go", "March–May and late September–November are the cheapest windows. Avoid school holidays, Easter week and August. Tuesday and Wednesday departures are usually 20–35% cheaper than Friday–Sunday."),
            ("Flights", "Book 6–8 weeks ahead. Use flexible-date search and compare nearby airports. Carry-on only: budget airlines charge more for a checked bag than for the ticket on short routes."),
            ("Where to stay", "Central hostels and 3-star hotels 1–2 metro stops from the centre cut costs by a third. Book refundable rates early, then re-check prices two weeks before the trip."),
            ("Daily budget", "Coffee and bakery breakfast: $5–7. Lunch at a market or local canteen: $10–14. Dinner: $15–20. Public transport day pass: $5–8."),
        ],
        "cta": ("Compare flight deals", "/go/01-europe-for-under-300.html"),
    },
    {
        "slug": "bali-budget",
        "title": "Bali on a budget: what 7 days actually cost",
        "headline": "Bali on a budget",
        "desc": "A realistic 7-day Bali budget: accommodation, food, scooter rental, beaches and when to go to avoid peak prices.",
        "intro": "Seven days in Bali can cost $35–60 per day mid-range if you skip peak season and stay away from beach-club resorts. Here is the breakdown.",
        "sections": [
            ("When to go", "April–June and September–October: dry season with lower prices. July–August and Christmas are peak — accommodation doubles."),
            ("Where to stay", "Canggu and Ubud guesthouses: $25–40 per night with breakfast. Book the first two nights only, then negotiate locally for weekly rates."),
            ("Getting around", "A scooter is $5–7 per day; taxis and ride-hailing are cheap but add up. Rent from a reputable shop with helmets and insurance."),
            ("Food and beaches", "Local warungs: $2–4 per meal. Beach clubs are the budget killer — pick one sunset spot and skip the rest."),
        ],
        "cta": ("Find Bali flight deals", "/go/02-bali-on-a-budget.html"),
    },
    {
        "slug": "rome-48-hours",
        "title": "48 hours in Rome: a first-timer itinerary",
        "headline": "48 hours in Rome",
        "desc": "Two-day Rome itinerary: skip the queues at the Colosseum and Vatican, where to eat in Trastevere, and a realistic walking route.",
        "intro": "Two days is enough for Rome if you book the two big sights ahead and walk the rest. This route avoids the worst queues and the tourist-trap restaurants.",
        "sections": [
            ("Day 1 — ancient Rome", "Colosseum at 8:30 with a timed ticket, then Forum and Palatine Hill. Lunch near Monti. Afternoon: Pantheon, Piazza Navona, Trevi Fountain. Dinner in Trastevere."),
            ("Day 2 — Vatican and centro", "Vatican Museums first entry (8:00–8:30) or St. Peter's Basilica early. Afternoon: Castel Sant'Angelo, Spanish Steps, Borghese Gardens."),
            ("Tickets", "Book Colosseum and Vatican 2–4 weeks ahead. Skip-the-line is worth it at the Colosseum; city passes only pay off if you plan 3+ sights."),
            ("Food", "Away from the main squares: pizza al taglio $4–6, pasta $12–16, gelato $3–4. Avoid restaurants with photo menus."),
        ],
        "cta": ("Get skip-the-line tickets", "/go/03-48-hours-in-rome.html"),
    },
    {
        "slug": "travel-esim",
        "title": "Travel eSIM: stay online abroad without roaming bills",
        "headline": "Travel eSIM",
        "desc": "How travel eSIMs work, how to install one before flying, and when they beat airport SIM cards.",
        "intro": "A travel eSIM gives you mobile data abroad from $4.99 without roaming charges or hunting for a SIM shop at the airport. Here is how to set it up before you fly.",
        "sections": [
            ("What it is", "A digital SIM installed on your phone. You keep your main number active for calls and use the eSIM for data."),
            ("Install before flying", "Buy and install the eSIM at home on Wi-Fi, then activate the data line when you land. Most providers send a QR code by email."),
            ("When it beats airport SIMs", "Short trips and multi-country travel: one eSIM can cover a region. Airport SIMs are pricier and require queueing."),
            ("Check your phone", "Most phones from 2019+ support eSIM. Check settings → mobile network → add eSIM before buying."),
        ],
        "cta": ("Get a travel eSIM", "/go/08-travel-esim.html"),
    },
    {
        "slug": "car-rental-europe",
        "title": "Car rental in Europe: when to book and how to avoid fees",
        "headline": "Car rental without surprises",
        "desc": "Booking windows, fuel policy and excess cover: how to rent a car in Europe without hidden fees.",
        "intro": "Car rental looks cheap until the counter adds insurance, fuel and deposit holds. Here is how to book at the right time and avoid the classic traps.",
        "sections": [
            ("When to book", "2–3 weeks ahead is usually the sweet spot. Last-minute prices spike in summer; too early can be more expensive than waiting."),
            ("Insurance", "Check your card's rental cover and the excess amount. Third-party excess insurance is often cheaper than the counter upsell."),
            ("Fuel and deposit", "Choose full-to-full fuel policy. The deposit is usually blocked on your card — check the amount before booking."),
            ("Check the car", "Photograph every scratch before driving off and return with the same fuel level."),
        ],
        "cta": ("Compare car rental deals", "/go/13-car-rental-booking-window.html"),
    },
    {
        "slug": "airport-transfer-guide",
        "title": "Airport transfers: fixed price, no taxi roulette",
        "headline": "Airport transfer guide",
        "desc": "How to book a reliable airport transfer: fixed prices, meet-and-greet, luggage and late-flight cover.",
        "intro": "An airport transfer with a fixed price removes the classic arrival stress: no haggling, no meter surprises, no queue at midnight. Here is how to book one properly.",
        "sections": [
            ("When to book", "Book 1–3 days ahead. For early-morning flights, book the night before to lock the price and the driver."),
            ("What's included", "Check: meet-and-greet at arrivals, flight tracking, waiting time, child seats, luggage capacity. These are the usual extra fees."),
            ("Price vs taxi", "Fixed transfer is usually 10–30% cheaper than an airport taxi for 2+ people, and the price does not change in traffic."),
            ("Cancellation", "Good providers allow free cancellation up to 24 hours before pickup — check before paying."),
        ],
        "cta": ("Book an airport transfer", "/go/10-airport-transfer.html"),
    },
    {
        "slug": "luggage-storage-guide",
        "title": "Luggage storage: explore the city hands-free",
        "headline": "Luggage storage guide",
        "desc": "Where to leave bags between check-out and your flight: prices, stations and booking tips.",
        "intro": "Late flight but morning check-out? Luggage storage costs $1.9–6 per bag per day and turns a dead afternoon into a city walk. Here is how to find a safe spot.",
        "sections": [
            ("Where to store", "Main train stations, central cafes and dedicated storage shops. Book online to lock the price and skip the queue."),
            ("Prices", "$1.9–6 per bag per day depending on the city and bag size. Cheaper than a late check-out in most hotels."),
            ("Safety", "Choose providers with insurance and 24/7 access, keep valuables on you, photograph the receipt."),
            ("Timing", "Store right after check-out, pick up 2–3 hours before your flight — leave margin for the airport transfer."),
        ],
        "cta": ("Find luggage storage", "/go/14-luggage-storage.html"),
    },
    {
        "slug": "skip-the-line-tickets-guide",
        "title": "Skip-the-line tickets: what's worth it (and what's not)",
        "headline": "Skip-the-line tickets",
        "desc": "Timed entry vs city passes: where skip-the-line actually saves hours, and where it is a waste of money.",
        "intro": "Skip-the-line is worth it at 4–5 attractions in Europe and a waste of money at the rest. Here is the simple rule to decide before you book.",
        "sections": [
            ("Worth it", "Colosseum, Vatican Museums, Eiffel Tower, Anne Frank House, Sagrada Família: queues are 1–3 hours without timed entry."),
            ("Not worth it", "Small museums, churches and neighbourhood sights: queues are short and the premium is 30–50%."),
            ("City passes", "Only pay off if you plan 3+ paid sights in 2–3 days. Do the maths before buying — transport is often not included."),
            ("Book ahead", "2–4 weeks ahead for the big sights in high season. Same-day tickets are resold at a markup."),
        ],
        "cta": ("Get tickets", "/go/11-skip-the-line.html"),
    },
    {
        "slug": "almaty-48-hours",
        "title": "Almaty in 48 hours: mountains, markets and cheap eats",
        "headline": "48 hours in Almaty",
        "desc": "A two-day Almaty itinerary: mountains, Green Bazaar, cable car, where to eat and how much it costs.",
        "intro": "Almaty packs mountains, a Soviet-era metro, a huge green bazaar and some of the cheapest good food in Central Asia into one walkable city. Here is the 48-hour plan we use.",
        "sections": [
            ("Day 1 — city centre", "Start at Panfilov Park and Zenkov Cathedral, walk to Green Bazaar for dried fruit and kazy, then ride the metro (each station is decorated differently) to Republic Square. Sunset at Kok-Tobe — take the cable car up, walk down."),
            ("Day 2 — mountains", "Medeu ice rink and the Shymbulak cable car are 25 minutes from the centre. Go early: queues build by 11:00. Bring a windproof layer — it is 10–15 °C colder than in the city."),
            ("Where to eat", "Lunch at a chaikhana (lagman, plov, samsa): $5–8. Coffee in the Golden Quarter: $3–4. Dinner at a local grill house: $12–18 for two."),
            ("Budget", "Hostel bed: $12–18. 3-star hotel: $45–70. Metro ride: $0.35. Cable car: $4. Airport bus: $1.5."),
        ],
        "cta": ("Cheap flights from Almaty", "/flights/almaty/"),
    },
    {
        "slug": "minsk-weekend",
        "title": "Minsk weekend: what to see, eat and where to stay",
        "headline": "Minsk weekend guide",
        "desc": "A weekend in Minsk: Independence Avenue, old town, museums, food markets and a realistic budget.",
        "intro": "Minsk is a clean, green and surprisingly cheap weekend city: wide avenues, rebuilt old town and excellent food markets. Two days is enough for the highlights.",
        "sections": [
            ("Day 1 — avenues and old town", "Walk Independence Avenue from Independence Square to Victory Square, then the old town (Troitskoye Predmestye) and the Island of Tears. Finish with dinner near Nemiga."),
            ("Day 2 — museums and markets", "Museum of the Great Patriotic War (book 2–3 hours), then Komarovsky market for cheese, honey and smoked fish. Afternoon: Gorky Park and the botanical garden."),
            ("Where to eat", "Draniki and machanka at a local cafeteria: $6–9. Coffee: $2–3. Dinner for two with wine: $25–35."),
            ("Budget", "Hostel bed: $10–15. 3-star hotel: $35–55. Metro: $0.3. Airport bus: $1.2. Package tours from Minsk start at ~130k RUB for 5–7 nights with flights."),
        ],
        "cta": ("Package tours from Minsk", "/tours/"),
    },
]


def render(article: dict, all_links: str) -> str:
    schema = json.dumps({
        "@context": "https://schema.org", "@type": "Article",
        "headline": article["title"], "description": article["desc"],
        "url": f"{PUB}/travel/{article['slug']}.html",
        "author": {"@type": "Organization", "name": "Content Factory"},
        "datePublished": TODAY, "dateModified": TODAY,
    })
    parts = [
        '<!doctype html>', '<html lang="en">', '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>{html.escape(article["title"])}</title>',
        f'<meta name="description" content="{html.escape(article["desc"])}">',
        f'<link rel="canonical" href="{PUB}/travel/{article["slug"]}.html">',
        '<meta property="og:type" content="article">',
        f'<meta property="og:title" content="{html.escape(article["title"])}">',
        f'<meta property="og:description" content="{html.escape(article["desc"])}">',
        f'<meta property="og:url" content="{PUB}/travel/{article["slug"]}.html">',
        '<meta name="robots" content="index,follow">',
        f'<script type="application/ld+json">{schema}</script>',
        DRIVE + '</head>',
        '<body style="margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#111;background:#fff">',
        '<div style="max-width:760px;margin:0 auto;padding:32px 20px 60px">',
        f'<p style="margin:0 0 18px"><a href="{PUB}/" style="color:#2563eb;text-decoration:none">← All channels</a> · <a href="{PUB}/travel/" style="color:#2563eb;text-decoration:none">Travel guides</a></p>',
        '<p style="color:#6b7280;font-size:13px;text-transform:uppercase;letter-spacing:.08em;margin:0 0 8px">Travel guide</p>',
        f'<h1 style="font-size:34px;line-height:1.15;margin:0 0 14px">{html.escape(article["headline"])}</h1>',
        f'<p style="font-size:18px;line-height:1.6;color:#374151">{html.escape(article["intro"])}</p>',
    ]
    for heading, body in article["sections"]:
        parts.append(f'<h2 style="font-size:22px;margin:26px 0 8px">{html.escape(heading)}</h2>')
        parts.append(f'<p style="font-size:16px;line-height:1.65;color:#374151">{html.escape(body)}</p>')
    cta_text, cta_link = article["cta"]
    parts += [
        f'<p style="margin:30px 0 8px"><a href="{PUB}{cta_link}" style="display:inline-block;background:#f59e0b;color:#111;font-weight:600;padding:12px 20px;border-radius:100px;text-decoration:none">{html.escape(cta_text)} →</a></p>',
        '<p style="color:#6b7280;font-size:13px">Ad · affiliate link. Prices and availability change.</p>',
        '<hr style="border:none;border-top:1px solid #e5e7eb;margin:28px 0">',
        f'<p style="font-size:14px;color:#374151">More guides: {all_links}</p>',
        f'<p style="font-size:13px;color:#6b7280;margin-top:22px">© Content Factory · <a href="{PUB}/privacy.html" style="color:#6b7280">Privacy</a> · <a href="{PUB}/terms.html" style="color:#6b7280">Terms</a></p>',
        '</div></body></html>',
    ]
    return "\n".join(parts)


def render_index() -> str:
    cards = "".join(
        f'<li style="margin:0 0 14px"><a href="{PUB}/travel/{a["slug"]}.html" style="color:#2563eb;text-decoration:none;font-size:18px">{html.escape(a["headline"])}</a>'
        f'<p style="margin:4px 0 0;color:#6b7280;font-size:14px">{html.escape(a["desc"])}</p></li>'
        for a in ARTICLES
    )
    return "\n".join([
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
        '<title>Travel guides — budget tips for flights, cities and eSIM</title>',
        '<meta name="description" content="Practical travel guides: cheap European city breaks, Bali on a budget, 48 hours in Rome, eSIM, airport transfers, luggage storage and car rental tips.">',
        f'<link rel="canonical" href="{PUB}/travel/">',
        '<meta name="robots" content="index,follow">',
        DRIVE + '</head>',
        '<body style="margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#111;background:#fff">',
        '<div style="max-width:760px;margin:0 auto;padding:32px 20px 60px">',
        f'<p style="margin:0 0 18px"><a href="{PUB}/" style="color:#2563eb;text-decoration:none">← All channels</a></p>',
        '<h1 style="font-size:34px;margin:0 0 8px">Travel guides</h1>',
        '<p style="font-size:17px;color:#374151;margin:0 0 24px">Practical, tested tips for cheap flights, city breaks, eSIM and car rental.</p>',
        f'<ul style="list-style:none;padding:0;margin:0">{cards}</ul>',
        '<p style="color:#6b7280;font-size:13px;margin-top:26px">Some links are affiliate links (Ad). Prices change.</p>',
        '</div></body></html>',
    ])


def update_sitemap() -> None:
    path = DOCS / "sitemap.xml"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    if "/travel/" in text:
        import re
        text = re.sub(r"\n  <url>\n    <loc>https://valdislavn-spec\.github\.io/content-factory/travel/.*?</url>\n  </url>", "", text, flags=re.S)
    urls = [f"{PUB}/travel/"] + [f"{PUB}/travel/{a['slug']}.html" for a in ARTICLES]
    blocks = "".join(
        f'\n  <url>\n    <loc>{url}</loc>\n    <lastmod>{TODAY}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.8</priority>\n  </url>'
        for url in urls
    )
    text = text.replace("</urlset>", blocks + "\n</urlset>")
    path.write_text(text, encoding="utf-8")
    print("sitemap: +%d travel urls" % len(urls))


def main() -> int:
    TRAVEL.mkdir(parents=True, exist_ok=True)
    links = " · ".join(f'<a href="{PUB}/travel/{a["slug"]}.html">{html.escape(a["headline"])}</a>' for a in ARTICLES)
    for article in ARTICLES:
        others = " · ".join(x for x in links.split(" · ") if f'/travel/{article["slug"]}.html' not in x)
        (TRAVEL / (article["slug"] + ".html")).write_text(render(article, others), encoding="utf-8")
        print("article:", article["slug"])
    (TRAVEL / "index.html").write_text(render_index(), encoding="utf-8")
    print("index written")
    update_sitemap()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
