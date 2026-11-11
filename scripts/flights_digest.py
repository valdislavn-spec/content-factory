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
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.integrations.apilayer import ApiLayerClient  # noqa: E402
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

ORIGINS = {
    "MOW": {"slug": "moscow", "name": "Moscow", "page": "docs/flights/moscow/index.html"},
    "ALA": {"slug": "almaty", "name": "Almaty", "page": "docs/flights/almaty/index.html"},
    "MSQ": {"slug": "minsk", "name": "Minsk", "page": "docs/flights/minsk/index.html"},
}

# Российские города-направления исключаем из публикаций (аудитория — KZ/BY, не РФ).
RU_DEST = {
    "MOW", "LED", "KZN", "AER", "KGD", "KUF", "SVX", "MCX", "ROV", "VKO", "DME", "SVO",
    "OVB", "KJA", "UFA", "SAM", "VOG", "GRV", "MRV", "NJC", "PEE", "TJM", "CEK", "IKT",
    "UUS", "VVO", "KHV", "BQS", "ASF", "RTW", "SKX", "TBW", "GOJ", "KRR", "AAQ", "EGO",
    "URS", "VOZ", "CSY", "IAR", "RYB", "ABA", "BAX", "KEJ", "NOZ", "OMS", "OSF", "PEX",
    "PKV", "PEE", "SGC", "STW", "TJM", "TOF", "UUD", "VUS", "YKS", "YOL", "ZIA", "ZST",
}

CITY_NAMES = {
    "IST": "Istanbul", "AYT": "Antalya", "EVN": "Yerevan", "TAS": "Tashkent", "DYU": "Dushanbe",
    "LED": "St. Petersburg", "AER": "Sochi", "KGD": "Kaliningrad", "MCX": "Makhachkala", "SKD": "Samarkand",
    "BKK": "Bangkok", "DXB": "Dubai", "TBS": "Tbilisi", "GYD": "Baku", "ALA": "Almaty", "MSQ": "Minsk",
    "BEG": "Belgrade", "CXR": "Nha Trang", "HKT": "Phuket", "DPS": "Bali", "BCN": "Barcelona", "ROM": "Rome",
    "PAR": "Paris", "LON": "London", "MIL": "Milan", "ATH": "Athens", "LCA": "Larnaca", "MLE": "Maldives",
    "PEK": "Beijing", "SHA": "Shanghai", "HKG": "Hong Kong", "DEL": "Delhi", "GOI": "Goa", "CMB": "Colombo",
}

LOCAL_CURRENCY = {
    "ALA": ("KZT", "₸"),
    "MSQ": ("BYN", "Br"),
}


def load_fx_rates(origin: str) -> dict:
    """Курсы EUR-базы из APILayer (кэш на день) для локальной валюты страницы."""
    if origin not in LOCAL_CURRENCY:
        return {}
    cache = ROOT / "data" / "flights" / "fx.json"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        if cache.exists():
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data.get("date") == today and data.get("rates"):
                return data["rates"]
    except Exception:  # noqa: BLE001
        pass
    try:
        client = ApiLayerClient()
        if not client.configured():
            return {}
        rates = client.latest_rates("RUB,KZT,BYN,USD").get("rates") or {}
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"date": today, "rates": rates}, ensure_ascii=False, indent=2), encoding="utf-8")
        return rates
    except Exception as error:  # noqa: BLE001
        print("fx failed:", str(error)[:120])
        return {}


def local_price(origin: str, price: int, rates: dict) -> str:
    """Цена в локальной валюте (KZT/BYN) как надпись; RUB остаётся основной."""
    meta = LOCAL_CURRENCY.get(origin)
    if not meta or not rates:
        return ""
    code, symbol = meta
    try:
        rub_per_eur = float(rates.get("RUB") or 0)
        local_per_eur = float(rates.get(code) or 0)
    except (TypeError, ValueError):
        return ""
    if rub_per_eur <= 0 or local_per_eur <= 0:
        return ""
    value = price / rub_per_eur * local_per_eur
    return "{:,.0f} {}".format(value, symbol).replace(",", " ")


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


def load_history(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def save_history(path: Path, origin: str, rows: list) -> dict:
    data = load_history(path)
    origin_data = data.get(origin) or {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    for row in rows:
        origin_data[row["destination"]] = {"price": row["price"], "at": now, "city": row["city"]}
    data[origin] = origin_data
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return origin_data


def find_drops(previous: dict, rows: list, min_drop: float = 0.15) -> list:
    drops = []
    for row in rows:
        prev = previous.get(row["destination"])
        if not prev:
            continue
        prev_price = int(prev.get("price") or 0)
        if prev_price <= 0:
            continue
        drop = (prev_price - row["price"]) / prev_price
        if drop >= min_drop:
            drops.append({**row, "previous_price": prev_price, "drop_pct": round(drop * 100)})
    drops.sort(key=lambda d: -d["drop_pct"])
    return drops


def notify_telegram(drops: list, origin: str, public: str, fx: dict = None) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID_TRAVEL") or os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        print("telegram: token/chat not set, skip")
        return
    if not drops:
        return
    lines = ["✈️ Цены на билеты упали из %s:" % ORIGINS.get(origin, {}).get("name", origin)]
    for drop in drops[:5]:
        line = "• %s — %d ₽" % (drop["city"], drop["price"])
        local = local_price(origin, drop["price"], fx or {})
        if local:
            line += " (≈ %s)" % local
        line += " (-%d%%) %s" % (drop["drop_pct"], drop["link"])
        lines.append(line)
    lines.append("Все билеты: %s/flights/" % public.rstrip("/"))
    payload = json.dumps({"chat_id": chat, "text": "\n".join(lines), "disable_web_page_preview": True}).encode()
    request = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % token, data=payload,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            print("telegram alert:", response.status)
    except Exception as error:  # noqa: BLE001
        print("telegram error:", str(error)[:120])


def render_page(rows: list, origin: str, updated: str, drops: list = None, public: str = PUB, fx: dict = None) -> str:
    table = []
    for row in rows:
        table.append(
            '<tr>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4">{row["city"]} <span style="color:#9ca3af">({row["destination"]})</span></td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4;white-space:nowrap">{row["dates"]}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4">{row["airline"]}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4;font-weight:600;white-space:nowrap">{row["price"]:,} ₽'.replace(",", " ")
            + (f'<div style="color:#6b7280;font-size:12px;font-weight:400">≈ {local_price(origin, row["price"], fx)}</div>' if fx and local_price(origin, row["price"], fx) else '')
            + '</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4"><a href="{row["link"]}" style="color:#2563eb;text-decoration:none">Book →</a></td>'
            '</tr>'
        )
    schema = json.dumps({
        "@context": "https://schema.org", "@type": "ItemList",
        "name": f"Cheapest flights from {origin}", "url": f"{PUB}/flights/",
        "numberOfItems": len(rows),
    })
    city_name = ORIGINS.get(origin, {}).get("name", origin)
    slug = ORIGINS.get(origin, {}).get("slug", "")
    canonical = f"{public}/flights/" + (slug + "/" if slug else "")
    nav = f'<p style="margin:0 0 18px"><a href="{public}/" style="color:#2563eb;text-decoration:none">← All channels</a> · <a href="{public}/travel/" style="color:#2563eb;text-decoration:none">Travel guides</a>'
    nav += f' · <a href="{public}/flights/" style="color:#2563eb;text-decoration:none">Flights from Almaty &amp; Minsk</a>'
    nav += f' · <a href="{public}/flights/almaty/" style="color:#2563eb;text-decoration:none">Almaty</a>'
    nav += f' · <a href="{public}/flights/minsk/" style="color:#2563eb;text-decoration:none">Minsk</a></p>'
    drops = drops or []
    drops_html = ""
    if drops:
        drops_html = (
            '<h2 style="font-size:22px;margin:0 0 10px">📉 Price drops today</h2>'
            '<ul style="margin:0 0 22px;padding-left:20px;color:#374151">'
            + "".join(
                f'<li><a href="{d["link"]}" style="color:#2563eb">{d["city"]}</a> — {d["price"]:,} ₽ '.replace(",", " ")
                + f'(было {d["previous_price"]:,} ₽, −{d["drop_pct"]}%)</li>'.replace(",", " ")
                for d in drops[:8]
            )
            + "</ul>"
        )
    return "\n".join([
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>Cheapest flights from {city_name} — deals updated daily</title>',
        f'<meta name="description" content="Cheapest round-trip flights from {city_name}: live Aviasales deals with dates, airlines and prices. Updated daily.">',
        f'<link rel="canonical" href="{canonical}">',
        f'<meta name="robots" content="{"noindex,nofollow" if origin == "MOW" else "index,follow"}">',
        f'<script type="application/ld+json">{schema}</script>',
        DRIVE + '</head>',
        '<body style="margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#111;background:#fff">',
        '<div style="max-width:860px;margin:0 auto;padding:32px 20px 60px">',
        nav,
        '<p style="color:#6b7280;font-size:13px;text-transform:uppercase;letter-spacing:.08em;margin:0 0 8px">Flight deals</p>',
        f'<h1 style="font-size:32px;margin:0 0 10px">Cheapest flights from {city_name}</h1>',
        f'<p style="color:#6b7280;margin:0 0 22px">Updated {updated} · prices in RUB · round-trip unless noted · via Aviasales</p>',
        drops_html,
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


def render_hub(public: str = PUB) -> str:
    """Landing page for flight deals: local departures only (Almaty, Minsk)."""
    cards = [
        ("Almaty", f"{public}/flights/almaty/", "Cheapest round-trip flights from Almaty, updated daily.", "🇰🇿"),
        ("Minsk", f"{public}/flights/minsk/", "Cheapest round-trip flights from Minsk, updated daily.", "🇧🇾"),
    ]
    cards_html = "".join(
        f'<a href="{href}" style="display:block;padding:20px 22px;border:1px solid #e5e7eb;border-radius:16px;text-decoration:none;color:#111;margin:0 0 14px">'
        f'<div style="font-size:20px;font-weight:600;margin-bottom:6px">{flag} Flights from {name}</div>'
        f'<div style="color:#6b7280;font-size:14px">{desc}</div>'
        f'<div style="color:#2563eb;font-size:14px;margin-top:8px">See deals →</div></a>'
        for name, href, desc, flag in cards
    )
    return "\n".join([
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
        '<title>Cheap flights from Almaty and Minsk — live deals</title>',
        '<meta name="description" content="Cheapest round-trip flights from Almaty and Minsk: live Aviasales deals with dates, airlines and prices. Updated daily.">',
        f'<link rel="canonical" href="{public}/flights/">',
        '<meta name="robots" content="index,follow">',
        DRIVE + '</head>',
        '<body style="margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#111;background:#fff">',
        '<div style="max-width:860px;margin:0 auto;padding:32px 20px 60px">',
        f'<p style="margin:0 0 18px"><a href="{public}/" style="color:#2563eb;text-decoration:none">← All channels</a> · <a href="{public}/travel/" style="color:#2563eb;text-decoration:none">Travel guides</a> · <a href="{public}/tours/" style="color:#2563eb;text-decoration:none">Package tours</a></p>',
        '<p style="color:#6b7280;font-size:13px;text-transform:uppercase;letter-spacing:.08em;margin:0 0 8px">Flight deals</p>',
        '<h1 style="font-size:32px;margin:0 0 10px">Cheap flights from Almaty &amp; Minsk</h1>',
        '<p style="color:#6b7280;margin:0 0 24px">Live round-trip deals for local departures: Almaty (Kazakhstan) and Minsk (Belarus). Prices in RUB, updated every morning.</p>',
        cards_html,
        f'<p style="font-size:14px;color:#374151;margin-top:20px">Also: <a href="{public}/tours/" style="color:#2563eb;text-decoration:none">package tours from Minsk &amp; Astana</a> · <a href="{public}/travel/travel-esim.html" style="color:#2563eb;text-decoration:none">travel eSIM</a> · <a href="{public}/travel/airport-transfer-guide.html" style="color:#2563eb;text-decoration:none">airport transfers</a></p>',
        '<p style="color:#6b7280;font-size:13px;margin-top:8px">Ad · affiliate links. Prices change fast; the price is fixed at booking.</p>',
        f'<p style="font-size:13px;color:#6b7280;margin-top:22px">© Content Factory · <a href="{public}/privacy.html" style="color:#6b7280">Privacy</a> · <a href="{public}/terms.html" style="color:#6b7280">Terms</a></p>',
        '</div></body></html>',
    ])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", default="ALA")
    parser.add_argument("--currency", default="rub")
    parser.add_argument("--top", type=int, default=12)
    parser.add_argument("--page", default="")
    parser.add_argument("--history", default=str(ROOT / "docs" / "flights" / "history.json"))
    parser.add_argument("--min-drop", type=float, default=0.15)
    parser.add_argument("--notify", action="store_true", help="send Telegram alert for price drops")
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

    items = [it for it in items if str(it.get("destination") or "").upper() not in RU_DEST]
    rows = build_rows(items, partner_links)
    updated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")

    history_path = Path(args.history)
    previous = load_history(history_path).get(args.origin.upper()) or {}
    drops = find_drops(previous, rows, min_drop=args.min_drop)
    save_history(history_path, args.origin.upper(), rows)

    origin_meta = ORIGINS.get(args.origin.upper(), {})
    page_path = Path(args.page or ROOT / origin_meta.get("page", "docs/flights/index.html"))
    page_path.parent.mkdir(parents=True, exist_ok=True)
    fx = load_fx_rates(args.origin.upper())
    page_path.write_text(render_page(rows, args.origin.upper(), updated, drops, fx=fx), encoding="utf-8")
    hub_path = ROOT / "docs" / "flights" / "index.html"
    if page_path.resolve() != hub_path.resolve():
        hub_path.write_text(render_hub(PUB), encoding="utf-8")
    print("page:", page_path, "| drops:", len(drops))
    if drops:
        for drop in drops[:5]:
            print("  DROP %-14s %d -> %d ₽ (-%d%%)" % (drop["city"], drop["previous_price"], drop["price"], drop["drop_pct"]))
    if args.notify:
        notify_telegram(drops, args.origin.upper(), PUB, fx=fx)

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
