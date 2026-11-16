#!/usr/bin/env python3
"""Generate the US travel-deals landing page: docs/flight-hotel-us/index.html.

English page for a US audience: partner promos (verified, from
.local/distribution/us-promos.json when present), 12 destination cards with
deep CTA to tracked Travelpayouts links, and trip-tool cards.

Run:
    content-factory/.venv/bin/python scripts/build_us_landing.py
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "flight-hotel-us" / "index.html"
BASE = "https://valdislavn-spec.github.io/content-factory/flight-hotel-us"
TELEGRAM_URL = "https://t.me/GOODTRAVEL007"
# Direct channel link is used until a permanent public invite is generated.
DISCORD_URL = "https://discord.com/channels/1467224878875807878/1571257984364060722"
PROMOS_JSON = ROOT.parent / ".local" / "distribution" / "us-promos.json"
FARES_JSON = ROOT / "docs" / "flight-hotel-us" / "fares.json"

CITY_NAMES = {
    "MIA": "Miami", "LAX": "Los Angeles", "CUN": "Cancún", "FCO": "Rome",
    "LHR": "London", "NRT": "Tokyo", "JFK": "New York", "EWR": "New York",
    "LGA": "New York",
}
AIRLINE_NAMES = {
    "F9": "Frontier", "AS": "Alaska Airlines", "UA": "United", "TP": "TAP Air Portugal",
    "AC": "Air Canada", "AA": "American Airlines", "B6": "JetBlue", "DL": "Delta",
}

LINKS = {
    "aviasales": "https://aviasales.tpk.ro/2ZW95Xpf",
    "tiqets": "https://tiqets.tpk.ro/ufgJDVmO",
    "klook": "https://klook.tpk.ro/2NhHWOSD",
    "airalo": "https://airalo.tpk.ro/IQhjJkbT",
    "saily": "https://saily.tpk.ro/QSNyiXp7",
    "yesim": "https://yesim.tpk.ro/uzjpBpju",
    "kiwitaxi": "https://kiwitaxi.tpk.ro/xmQYmqIl",
    "gettransfer": "https://gettransfer.tpk.ro/sMmU1wE7",
    "welcomepickups": "https://tpk.ro/kTevGAQP",
    "localrent": "https://localrent.tpk.ro/edD3Ejwe",
    "economybookings": "https://economybookings.tpk.ro/IwQqKHL3",
    "qeeq": "https://qeeq.tpk.ro/9W1Pi9hm",
    "getrentacar": "https://getrentacar.tpk.ro/tyEGMAcd",
    "kiwi": "https://kiwi.tpk.ro/RJINNJJm",
    "gocity": "https://gocity.tpk.ro/yoqmgDkj",
    "radicalstorage": "https://radicalstorage.tpk.ro/wskVrPYh",
    "airhelp": "https://airhelp.tpk.ro/rZjahO3R",
    "compensair": "https://compensair.tpk.ro/4klXfGpD",
    "kkday": "https://kkday.tpk.ro/11CJTQvo",
}

#: destination, emoji, region, flight note from NYC, best season, first CTA program
DESTINATIONS = [
    ("Cancún", "🏖", "Mexico", "nonstop · 4h", "Dec–Apr", "tiqets"),
    ("London", "🇬🇧", "UK", "nonstop · 7h", "May–Sep", "klook"),
    ("Paris", "🗼", "France", "nonstop · 7h 30m", "Apr–Jun, Sep–Oct", "tiqets"),
    ("Rome", "🏛", "Italy", "nonstop · 9h", "Apr–Jun, Sep–Oct", "tiqets"),
    ("Barcelona", "🌞", "Spain", "nonstop · 8h", "May–Jun, Sep", "klook"),
    ("Lisbon", "🚋", "Portugal", "1 stop · ~9h", "Apr–Jun, Sep–Oct", "klook"),
    ("Reykjavík", "🌋", "Iceland", "nonstop · 5h 30m", "Jun–Aug, Sep", "tiqets"),
    ("Dublin", "🍀", "Ireland", "nonstop · 6h 30m", "May–Sep", "klook"),
    ("Tokyo", "🗾", "Japan", "nonstop · 14h", "Mar–May, Oct–Nov", "klook"),
    ("Bali", "🌴", "Indonesia", "1 stop · ~22h", "Apr–Oct", "klook"),
    ("Mexico City", "🌮", "Mexico", "nonstop · 5h", "Mar–May, Oct–Nov", "tiqets"),
    ("Punta Cana", "🥥", "Dominican Rep.", "nonstop · 4h", "Dec–Apr", "tiqets"),
]

TOOLS = [
    ("eSIM", "📶", "Stay online without roaming:", [("airalo", "Airalo"), ("yesim", "Yesim"), ("saily", "Saily")]),
    ("Transfers", "🚕", "Fixed-price airport rides:", [("kiwitaxi", "Kiwitaxi"), ("gettransfer", "GetTransfer"), ("welcomepickups", "Welcome Pickups")]),
    ("Car rental", "🚗", "Compare local and global brands:", [("economybookings", "Economybookings"), ("qeeq", "Qeeq"), ("getrentacar", "GetRentacar")]),
    ("City passes", "🎫", "One pass, many attractions:", [("gocity", "Go City"), ("tiqets", "Tiqets"), ("klook", "Klook")]),
    ("Trains & buses", "🚆", "Between cities:", [("kiwi", "Kiwi.com")]),
    ("Luggage", "🧳", "Left-bag storage:", [("radicalstorage", "RadicalStorage")]),
    ("Flight delay", "🛟", "Claim compensation:", [("airhelp", "AirHelp"), ("compensair", "Compensair")]),
]

#: Top Travelpayouts programs by outbound clicks (Oct 17 – Nov 16, 2026).
TOP_PARTNERS = [
    ("Airport transfers", "🚕", "Fixed-price airport rides — the most-clicked tool in the last 30 days.", "kiwitaxi", "Book a transfer"),
    ("Flights", "✈️", "Compare fares from New York, Los Angeles, Miami, Chicago and other US hubs.", "aviasales", "Search flights"),
    ("eSIM — Yesim", "📶", "Instant mobile data for the US and abroad — no roaming surprises.", "yesim", "Get an eSIM"),
    ("Trains & buses", "🚆", "Book intercity travel across Europe, Japan and beyond.", "kiwi", "Find routes"),
    ("Tours & experiences", "🎟️", "Attractions, day trips and local experiences in 100+ cities.", "klook", "Explore experiences"),
    ("eSIM — Saily", "📱", "Affordable data plans for short trips and longer stays.", "saily", "Compare plans"),
]

#: brand (lowercase, как в us-promos.json) → трекинговая ссылка Travelpayouts
BRAND_LINKS = {
    "aviasales": "aviasales", "tiqets": "tiqets", "klook": "klook",
    "airalo": "airalo", "yesim": "yesim", "saily": "saily",
    "kiwitaxi": "kiwitaxi", "gettransfer": "gettransfer", "welcomepickups": "welcomepickups",
    "gocity": "gocity", "kiwi": "kiwi", "radicalstorage": "radicalstorage",
    "airhelp": "airhelp", "compensair": "compensair",
    "economybookings": "economybookings", "localrent": "localrent", "qeeq": "qeeq",
    "kkday": "kkday",
}


def tracked(brand: str) -> str:
    key = BRAND_LINKS.get(re.sub(r"[^a-z0-9]", "", brand.lower()))
    return LINKS.get(key or "", "")


def load_promos() -> list[dict]:
    if not PROMOS_JSON.exists():
        return []
    try:
        data = json.loads(PROMOS_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    items = data if isinstance(data, list) else data.get("promos") or []
    return [p for p in items if isinstance(p, dict) and p.get("brand")]


def esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def load_fares() -> list[dict]:
    if not FARES_JSON.exists():
        return []
    try:
        data = json.loads(FARES_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [f for f in data.get("fares", []) if isinstance(f, dict) and f.get("price")]


def fmt_duration(minutes: int) -> str:
    hours, mins = divmod(int(minutes or 0), 60)
    return f"{hours}h {mins:02d}m" if hours else f"{mins}m"


def fares_html() -> str:
    fares = load_fares()
    if not fares:
        return ""
    cards = []
    for f in fares:
        origin = f.get("origin", "")
        dest = f.get("destination", "")
        origin_name = CITY_NAMES.get(origin, origin)
        dest_name = CITY_NAMES.get(dest, dest)
        stops = "nonstop" if int(f.get("transfers", 0)) == 0 else f"{f.get('transfers')} stop"
        airline = AIRLINE_NAMES.get(f.get("airline", ""), f.get("airline", ""))
        cards.append(
            f'<a class="fare" href="{LINKS["aviasales"]}" target="_blank" rel="noopener sponsored">'
            f'<span class="fare-route"><b>{esc(origin)} → {esc(dest)}</b>'
            f'<span>{esc(origin_name)} → {esc(dest_name)}</span></span>'
            f'<span class="fare-price">${int(f["price"]):,}</span>'
            f'<span class="fare-meta">{esc(stops)} · {esc(fmt_duration(f.get("duration_min", 0)))} · {esc(airline)}</span>'
            f'<span class="fare-cta">Check live price →</span></a>'
        )
    return f"""
<section class="sec" id="fares">
  <h2>Sample one-way fares from the US</h2>
  <p class="lead">Fresh sample from Travelpayouts MCP: one-way, per person, USD, checked 2026-11-16 for departure on 2026-12-10.
  Prices and availability change — the partner site shows the live fare.</p>
  <div class="grid fares">{''.join(cards)}</div>
  <p class="note">Affiliate links: we may earn a commission when you book — the price you pay stays the same.</p>
</section>
"""


def promos_html(promos: list[dict]) -> str:
    if not promos:
        return ""
    cards = []
    for p in promos:
        brand = esc(p.get("brand", ""))
        offer = esc(p.get("offer", ""))
        terms = esc(p.get("terms", ""))
        code = p.get("promo_code") or ""
        until = p.get("valid_until") or ""
        track = p.get("affiliate_url") or tracked(brand)
        url = track or p.get("source_url") or "#"
        ext = "" if track else '<span class="ext">official page</span>'
        code_html = f'<span class="code">{esc(code)}</span>' if code else ""
        until_html = f'<span class="until">until {esc(until)}</span>' if until else ""
        cards.append(
            f'<a class="promo-card" href="{esc(url)}" target="_blank" rel="noopener sponsored">'
            f'<span class="p-brand">{brand}</span>'
            f'<span class="p-offer">{offer}</span>'
            f'<span class="p-terms">{terms}</span>'
            f'<span class="p-meta">{code_html}{until_html}{ext}</span></a>')
    return f"""
<section class="sec" id="promos">
  <h2>🔥 Deals &amp; promo codes right now</h2>
  <p class="lead">Verified offers from our travel partners. Codes are applied on the partner site; terms are shown on their page.</p>
  <div class="grid promos">{''.join(cards)}</div>
  <p class="note">Advertising / affiliate links: we may earn a commission — the price you pay stays the same.
  Deals are checked on {date.today().isoformat()} and can change without notice.</p>
</section>
"""


def destinations_html() -> str:
    cards = []
    for name, emoji, region, flight, season, cta in DESTINATIONS:
        cards.append(
            f'<article class="card"><div class="card-top"><span class="emoji">{emoji}</span>'
            f'<h3>{esc(name)}</h3><span class="tag">{esc(region)}</span></div>'
            f'<div class="facts"><span>🛫 {esc(flight)}</span><span>📅 Best: {esc(season)}</span></div>'
            f'<div class="ctas"><a href="{LINKS["aviasales"]}" target="_blank" rel="noopener sponsored">Flights →</a>'
            f'<a href="{LINKS[cta]}" target="_blank" rel="noopener sponsored">Experiences →</a></div></article>')
    return f"""
<section class="sec" id="destinations">
  <h2>🌎 Where to go from the US</h2>
  <p class="lead">Twelve easy escapes — nonstop or one-stop flights from New York, and the season when each one is at its best.</p>
  <div class="grid dest">{''.join(cards)}</div>
</section>
"""


def tools_html() -> str:
    cards = []
    for title, emoji, text, pairs in TOOLS:
        refs = " · ".join(
            f'<a href="{LINKS[key]}" target="_blank" rel="noopener sponsored">{esc(label)}</a>'
            for key, label in pairs)
        cards.append(f'<div class="tool"><b>{emoji} {esc(title)}</b><span>{esc(text)}</span><span>{refs}</span></div>')
    return f"""
<section class="sec" id="tools">
  <h2>🧳 Trip tools</h2>
  <p class="lead">Everything around the flight — from the airport ride to staying online.</p>
  <div class="grid tools">{''.join(cards)}</div>
</section>
"""


def social_html() -> str:
    return f"""
<div class="social-row" aria-label="Travel community links">
  <a class="social-btn tg" href="{TELEGRAM_URL}" target="_blank" rel="noopener">Telegram deals ↗</a>
  <a class="social-btn dc" href="{DISCORD_URL}" target="_blank" rel="noopener">Discord trip chat ↗</a>
</div>
<p class="social-note">Join the community for fresh fare drops, mistake fares and trip-planning help.</p>
"""


def top_partners_html() -> str:
    cards = "".join(
        f'<a class="partner" href="{LINKS[key]}" target="_blank" rel="noopener sponsored">'
        f'<span class="partner-icon">{emoji}</span>'
        f'<span class="partner-body"><b>{esc(title)}</b><span>{esc(text)}</span></span>'
        f'<span class="partner-cta">{esc(cta)} →</span></a>'
        for title, emoji, text, key, cta in TOP_PARTNERS
    )
    return f"""
<section class="sec" id="start">
  <h2>Most-clicked travel tools</h2>
  <p class="lead">Ranked by outbound clicks from our links over the last 30 days — the tools US travelers actually use.</p>
  <div class="grid partners">{cards}</div>
  <p class="note">Travelpayouts, Oct 17 – Nov 16, 2026 · 557 tracked clicks. Affiliate links: we may earn a commission when you book — the price you pay stays the same.</p>
</section>
"""


def build() -> str:
    promos = load_promos()
    promo_count = len(promos)
    kpi_promos = f"{promo_count} promo{'s' if promo_count != 1 else ''} live" if promo_count else "10+ partners"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>US Travel Deals — flights, stays &amp; experiences</title>
<meta name="description" content="Curated travel deals for US travelers: verified flight, hotel and experience promos, 12 easy destinations, eSIM, transfers and car rental.">
<meta property="og:type" content="website">
<meta property="og:locale" content="en_US">
<meta property="og:site_name" content="Travelata Deals">
<meta property="og:title" content="US Travel Deals — flights, stays &amp; experiences">
<meta property="og:description" content="Verified promos from travel partners, 12 easy destinations from the US, plus eSIM, transfers and car rental.">
<meta property="og:url" content="{BASE}/">
<meta property="og:image" content="{BASE}/preview-social.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="US Travel Deals — flights, stays &amp; experiences">
<meta name="twitter:description" content="Verified travel promos + 12 easy destinations from the US.">
<meta name="twitter:image" content="{BASE}/preview-social.png">
<style>
* {{ box-sizing: border-box; }}
body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
  background:#070b18; color:#eef2ff; line-height:1.55; }}
.hero {{ padding:56px 22px 42px; background:
  radial-gradient(900px 420px at 12% -10%, #4c1d95 0%, transparent 60%),
  radial-gradient(760px 380px at 88% 0%, #0e7490 0%, transparent 55%),
  linear-gradient(180deg,#0b1226 0%,#070b18 100%); }}
.wrap {{ max-width:1080px; margin:0 auto; }}
.tag {{ display:inline-block; font-size:11px; letter-spacing:.12em; text-transform:uppercase;
  color:#a5b4fc; background:rgba(99,102,241,.14); border:1px solid rgba(129,140,248,.35);
  padding:6px 11px; border-radius:999px; }}
h1 {{ font-size:clamp(30px,4.8vw,48px); line-height:1.06; margin:16px 0 12px; }}
h1 em {{ font-style:normal; background:linear-gradient(92deg,#fbbf24,#f472b6 45%,#818cf8);
  -webkit-background-clip:text; background-clip:text; color:transparent; }}
.lead {{ color:#b9c3e6; font-size:15.5px; max-width:760px; }}
.kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:26px 0 4px; }}
.kpi {{ background:rgba(255,255,255,.045); border:1px solid rgba(148,163,255,.18);
  border-radius:16px; padding:14px 16px; }}
.kpi b {{ display:block; font-size:22px; }}
.kpi span {{ color:#94a3c6; font-size:12px; }}
.sec {{ max-width:1080px; margin:0 auto; padding:30px 22px 8px; }}
h2 {{ font-size:22px; margin:6px 0 10px; }}
.grid {{ display:grid; gap:12px; }}
.grid.promos {{ grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); }}
.grid.dest {{ grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); }}
.grid.tools {{ grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); }}
.promo-card {{ display:flex; flex-direction:column; gap:5px; padding:16px; border-radius:16px;
  text-decoration:none; color:inherit; border:1px solid rgba(251,191,36,.35);
  background:linear-gradient(160deg,rgba(251,191,36,.1),rgba(244,114,182,.07));
  transition:transform .15s,border-color .15s; }}
.promo-card:hover {{ transform:translateY(-2px); border-color:rgba(251,191,36,.7); }}
.p-brand {{ font-weight:800; font-size:15px; color:#fde68a; }}
.p-offer {{ font-size:16px; font-weight:700; }}
.p-terms {{ font-size:12px; opacity:.72; }}
.p-meta {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:4px; }}
.code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12.5px;
  background:rgba(251,191,36,.16); border:1px dashed rgba(251,191,36,.6);
  border-radius:8px; padding:2px 8px; }}
.until {{ font-size:11.5px; opacity:.7; align-self:center; }}
.ext {{ font-size:10.5px; letter-spacing:.06em; text-transform:uppercase; color:#94a3c6;
  border:1px solid rgba(148,163,255,.35); border-radius:6px; padding:1px 6px; align-self:center; }}
.card {{ background:rgba(255,255,255,.045); border:1px solid rgba(148,163,255,.18);
  border-radius:16px; padding:16px; }}
.card-top {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; }}
.card-top h3 {{ margin:0; font-size:17px; }}
.emoji {{ font-size:20px; }}
.card-top .tag {{ font-size:9.5px; padding:3px 8px; letter-spacing:.06em; }}
.facts {{ display:flex; flex-direction:column; gap:2px; font-size:12.5px; color:#a9b6dd; margin:10px 0 12px; }}
.ctas {{ display:flex; gap:10px; flex-wrap:wrap; font-size:13px; }}
.ctas a {{ color:#a5b4fc; font-weight:600; text-decoration:none; }}
.ctas a:hover {{ color:#e0e7ff; }}
.tool {{ display:flex; flex-direction:column; gap:4px; padding:14px 16px; border-radius:14px;
  background:rgba(255,255,255,.04); border:1px solid rgba(148,163,255,.15); font-size:13px; }}
.tool b {{ font-size:14px; }}
.tool span {{ color:#a9b6dd; }}
.tool a {{ color:#a5b4fc; text-decoration:none; font-weight:600; }}
.note {{ font-size:11.5px; color:#8b98bf; margin:12px 0 0; }}
footer {{ max-width:1080px; margin:16px auto 0; padding:22px; color:#7c89ad; font-size:12.5px; }}
footer a {{ color:#a5b4fc; }}
.social-row {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:22px; }}
.social-btn {{ display:inline-flex; align-items:center; justify-content:center; padding:11px 16px;
  border-radius:12px; color:#fff; text-decoration:none; font-size:14px; font-weight:800; }}
.social-btn.tg {{ background:#229ED9; }}
.social-btn.dc {{ background:#5865F2; }}
.social-btn:hover {{ filter:brightness(1.08); }}
.social-note {{ color:#94a3c6; font-size:12.5px; margin:9px 0 0; }}
.grid.partners {{ grid-template-columns:repeat(auto-fit,minmax(290px,1fr)); }}
.grid.fares {{ grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); }}
.fare {{ display:flex; flex-direction:column; gap:6px; padding:15px 16px; border-radius:16px;
  background:rgba(255,255,255,.045); border:1px solid rgba(148,163,255,.18);
  color:#eef2ff; text-decoration:none; }}
.fare:hover {{ border-color:rgba(165,180,252,.6); }}
.fare-route {{ display:flex; flex-direction:column; gap:2px; }}
.fare-route b {{ font-size:18px; letter-spacing:.02em; }}
.fare-route span {{ color:#94a3c6; font-size:11.5px; }}
.fare-price {{ font-size:31px; font-weight:900; color:#fbbf24; line-height:1.1; margin-top:4px; }}
.fare-meta {{ color:#a9b6dd; font-size:12px; }}
.fare-cta {{ color:#c4b5fd; font-size:12px; font-weight:800; margin-top:4px; }}
.partner {{ display:flex; align-items:flex-start; gap:12px; padding:16px; border-radius:16px;
  background:rgba(255,255,255,.045); border:1px solid rgba(148,163,255,.18);
  color:#eef2ff; text-decoration:none; transition:border-color .15s, transform .15s; }}
.partner:hover {{ border-color:rgba(165,180,252,.6); transform:translateY(-1px); }}
.partner-icon {{ font-size:22px; line-height:1.2; }}
.partner-body {{ display:flex; flex-direction:column; gap:3px; flex:1; }}
.partner-body b {{ font-size:15px; }}
.partner-body span {{ color:#a9b6dd; font-size:12.5px; }}
.partner-cta {{ color:#c4b5fd; font-size:12px; font-weight:800; white-space:nowrap; }}
@media (max-width:820px) {{ .kpis {{ grid-template-columns:repeat(2,1fr); }} }}
</style>
</head>
<body>
<div class="hero"><div class="wrap">
  <span class="tag">deals · updated {date.today().isoformat()}</span>
  <h1>Travel more, <em>pay less</em></h1>
  <p class="lead">Hand-picked flight, hotel and experience deals for travelers in the United States.
  Compare options from New York, Los Angeles, Miami, Chicago and other US hubs — flights, city passes,
  tours, eSIM, airport transfers and car rental in one place.</p>
  {social_html()}
  <div class="kpis">
    <div class="kpi"><b>12</b><span>easy destinations</span></div>
    <div class="kpi"><b>{len(LINKS)}</b><span>travel partners</span></div>
    <div class="kpi"><b>557</b><span>tracked clicks / 30 days</span></div>
    <div class="kpi"><b>$0</b><span>hidden fees</span></div>
  </div>
</div></div>
{top_partners_html()}{fares_html()}{promos_html(promos)}{destinations_html()}{tools_html()}
<footer>
  <p>Join us: <a href="{TELEGRAM_URL}" target="_blank" rel="noopener">Telegram</a> ·
  <a href="{DISCORD_URL}" target="_blank" rel="noopener">Discord</a></p>
  <p>Partner links: we may earn a commission when you book — the price stays the same for you. Deals and terms are set by the partners.</p>
  <p>Updated {date.today().isoformat()} · <a href="{BASE}/">flight-hotel-us</a> · <b>Not an offer; prices change.</b></p>
</footer>
</body>
</html>
"""


def main() -> int:
    html = build()
    from seo_enhance import enhance_us
    html = enhance_us(html)
    from add_subscribe_forms import EN_BLOCK, ENDPOINT
    if 'id="subscribe"' not in html:
        html = html.replace(
            '<footer>',
            EN_BLOCK.replace('__SOURCE__', 'landing-us').replace('__ENDPOINT__', ENDPOINT) + '<footer>',
            1,
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    promos = len(load_promos())
    print(f"written {OUT} ({len(html)} bytes, promos: {promos})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
