"""English-language flight collections for the Kazakhstan audience.

Same source data as the Russian set (rendered /flights/almaty/), but:
  * Kazakhstan departures only — no Minsk, no Russia-facing routes;
  * prices converted to USD, so a reader abroad is not shown roubles;
  * English copy, English city names, `$` amounts.

Layout mirrors the Russian collections: /collections/en/ hub + one page per
collection, plus ready-to-post Telegram messages (HTML) in data/outbox.

FX: open.er-api.com (no key). Falls back to FALLBACK_RUB_USD when the network
is unavailable, and the rate is written into every page ("RUB→USD 0.0121") so
the number can be audited rather than trusted.
"""

from __future__ import annotations

import html
import json
import re
import urllib.request
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

from content_factory import flights_geo as geo
from content_factory.flights_collections import (
    AVIASALES_CTA,
    PUBLIC,
    TELEGRAM_LIMIT,
    Collection,
    Deal,
    analytics_head,
    load_deals,
    page_updated,
    parse_page,
)

ROOT_PREFIX = "/collections/en"
FALLBACK_RUB_USD = 0.01212
FX_URL = "https://open.er-api.com/v6/latest/RUB"
FX_SOURCE = "open.er-api.com"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ---------------------------------------------------------------------------
# Money, dates, fx
# ---------------------------------------------------------------------------
def usd(value: int) -> str:
    return "${:,}".format(int(value)).replace(",", ",")


def fmt_date(value: Optional[date]) -> str:
    if not value:
        return "dates TBA"
    return "%d %s" % (value.day, MONTHS[value.month - 1])


def fmt_dates(dep: Optional[date], ret: Optional[date]) -> str:
    if not dep:
        return "dates TBA"
    if not ret or ret == dep:
        return fmt_date(dep)
    if dep.month == ret.month:
        return "%d–%d %s" % (dep.day, ret.day, MONTHS[ret.month - 1])
    return "%s – %s" % (fmt_date(dep), fmt_date(ret))


def routes(n: int) -> str:
    return "%d %s" % (n, "route" if n == 1 else "routes")


def fetch_rub_usd() -> Tuple[float, str]:
    """RUB→USD rate. Returns (rate, note). Never raises."""
    try:
        request = urllib.request.Request(FX_URL, headers={"User-Agent": "content-factory/1.0"})
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
        rate = float((payload.get("rates") or {}).get("USD") or 0)
        if 0.001 < rate < 1:
            stamp = str(payload.get("time_last_update_utc") or "")[:16]
            return rate, "%s %s" % (FX_SOURCE, stamp)
    except Exception:  # noqa: BLE001
        pass
    return FALLBACK_RUB_USD, "fallback rate"


def convert_to_usd(deals: Iterable[Deal], rate: float) -> List[Deal]:
    return [replace(d, price=max(1, int(round(d.price * rate)))) for d in deals]


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EnSpec:
    slug: str
    title: str
    lead: str
    emoji: str
    match: Callable[[Deal], bool]
    limit: int = 6
    seo: str = ""
    min_deals: int = 3


KAZAKHSTAN_ONLY = lambda d: d.origin == "ALA"  # noqa: E731

EN_SPECS: Sequence[EnSpec] = (
    EnSpec(
        "under-150",
        "Flights from Almaty under $150",
        "Real round-trip fares for under $150 — the cheapest the search returns this week.",
        "💸",
        lambda d: d.price <= 150,
        limit=8,
        seo="Cheap flights from Almaty under $150 — live deals",
    ),
    EnSpec(
        "under-100",
        "Under $100 from Almaty",
        "Weekend-sized fares: two hours in the air, less than a hundred dollars.",
        "🪙",
        lambda d: d.price <= 100,
        min_deals=2,
        seo="Flights from Almaty under $100",
    ),
    EnSpec(
        "central-asia",
        "Central Asia & the Caucasus",
        "Tashkent, Dushanbe, Baku, Yerevan, Batumi: visa-free and usually nonstop.",
        "🏔",
        lambda d: d.country in {"UZ", "TJ", "KG", "TM", "AZ", "AM", "GE"},
        seo="Flights from Almaty to Central Asia and the Caucasus",
    ),
    EnSpec(
        "warm-winter",
        "Warm in winter",
        "Where it is +20 in January: Turkey, the Gulf, South-East Asia.",
        "🌴",
        lambda d: "warm" in d.tags,
        min_deals=2,
        seo="Warm winter destinations from Almaty",
    ),
    EnSpec(
        "kazakhstan",
        "Across Kazakhstan",
        "Shymkent, Aktau, Aktobe, Atyrau: domestic fares are cheaper than most people think.",
        "🇰🇿",
        lambda d: d.country == "KZ",
        seo="Cheap domestic flights in Kazakhstan",
    ),
    EnSpec(
        "week-plus",
        "A week or longer",
        "Fares where the trip is seven nights or more — a holiday, not a weekend.",
        "🧳",
        lambda d: d.nights >= 7,
        seo="Long-stay flight deals from Almaty",
    ),
)


def build(deals: Iterable[Deal], min_deals: int = 3) -> List[Collection]:
    pool = [d for d in deals if d.price > 0 and d.origin == "ALA"]
    result: List[Collection] = []
    for spec in EN_SPECS:
        picked = sorted((d for d in pool if spec.match(d)), key=lambda d: (d.price, d.dest))
        seen, unique = set(), []
        for deal in picked:
            if deal.city in seen:
                continue
            seen.add(deal.city)
            unique.append(deal)
        picked = unique[: spec.limit]
        if len(picked) >= (spec.min_deals or min_deals):
            result.append(Collection(slug=spec.slug, title=spec.title, lead=spec.lead,
                                     emoji=spec.emoji, deals=picked, seo=spec.seo))
    return result


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def _esc(value: str) -> str:
    return html.escape(str(value), quote=True)


def _fmt_updated(updated: Optional[datetime]) -> str:
    if not updated:
        return "today"
    return "%d %s %d, %02d:%02d UTC" % (updated.day, MONTHS[updated.month - 1],
                                        updated.year, updated.hour, updated.minute)


def _nav(public: str) -> str:
    return (
        '<p style="margin:0 0 18px">'
        f'<a href="{public}/" style="color:#2563eb;text-decoration:none">← Home</a> · '
        f'<a href="{public}/flights/" style="color:#2563eb;text-decoration:none">Flights</a> · '
        f'<a href="{public}/collections/en/" style="color:#2563eb;text-decoration:none">All collections</a> · '
        f'<a href="{public}/collections/" style="color:#2563eb;text-decoration:none">На русском</a></p>'
    )


def _rows(col: Collection) -> str:
    out = []
    for deal in col.deals:
        nights = ('<div style="color:#6b7280;font-size:12px">%d %s</div>'
                  % (deal.nights, "night" if deal.nights == 1 else "nights")) if deal.nights else ""
        out.append(
            "<tr>"
            '<td style="padding:10px 12px;border-bottom:1px solid #eef0f4">'
            f'<div style="font-weight:600">{_esc(geo.city_name(deal.dest, "en"))}</div>'
            f'<div style="color:#6b7280;font-size:12px">{_esc(geo.country_name(deal.country, "en"))}</div></td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4;white-space:nowrap">'
            f"{_esc(fmt_dates(deal.dep, deal.ret))}{nights}</td>"
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4">{_esc(deal.airline)}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4;font-weight:600;white-space:nowrap">'
            f"{usd(deal.price)}</td>"
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4">'
            f'<a href="{_esc(deal.link)}" style="color:#2563eb;text-decoration:none">Book →</a></td>'
            "</tr>"
        )
    return "".join(out)


def _cards(cols: Sequence[Collection], public: str, exclude: str = "") -> str:
    out = []
    for col in cols:
        if col.slug == exclude:
            continue
        out.append(
            f'<a href="{public}{ROOT_PREFIX}/{col.slug}/" style="display:block;padding:16px 18px;'
            'border:1px solid #e5e7eb;border-radius:14px;text-decoration:none;color:#111;margin:0 0 12px">'
            f'<div style="font-size:17px;font-weight:600;margin-bottom:4px">{col.emoji} {_esc(col.title)}</div>'
            f'<div style="color:#6b7280;font-size:14px">{routes(col.count)} · from {usd(col.cheapest)}</div>'
            "</a>"
        )
    return "".join(out)


def render_page(col: Collection, cols: Sequence[Collection], updated: Optional[datetime],
                rate: float, fx_note: str, public: str = PUBLIC) -> str:
    title = "%s | Content Factory" % (col.seo or ("%s — cheap flights" % col.title))
    description = "%s %s, from %s. Updated %s." % (
        col.lead, routes(col.count), usd(col.cheapest), _fmt_updated(updated))
    schema = json.dumps({
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "ItemList",
                "name": col.title,
                "url": "%s%s/%s/" % (public, ROOT_PREFIX, col.slug),
                "numberOfItems": col.count,
                "itemListElement": [
                    {"@type": "ListItem", "position": i + 1,
                     "name": "Almaty → %s" % geo.city_name(d.dest, "en"),
                     "url": d.link,
                     "offers": {"@type": "Offer", "price": d.price, "priceCurrency": "USD"}}
                    for i, d in enumerate(col.deals)
                ],
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": public + "/"},
                    {"@type": "ListItem", "position": 2, "name": "Flights", "item": public + "/flights/"},
                    {"@type": "ListItem", "position": 3, "name": "Collections",
                     "item": public + ROOT_PREFIX + "/"},
                    {"@type": "ListItem", "position": 4, "name": col.title,
                     "item": "%s%s/%s/" % (public, ROOT_PREFIX, col.slug)},
                ],
            },
        ],
    }, ensure_ascii=False)

    return "\n".join([
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_esc(title)}</title>",
        f'<meta name="description" content="{_esc(description)}">',
        f'<link rel="canonical" href="{public}{ROOT_PREFIX}/{col.slug}/">',
        '<meta property="og:type" content="article">',
        f'<meta property="og:title" content="{_esc(col.title)} — cheap flights from Almaty">',
        f'<meta property="og:description" content="{_esc(description)}">',
        f'<meta property="og:url" content="{public}{ROOT_PREFIX}/{col.slug}/">',
        f'<script type="application/ld+json">{schema}</script>',
        analytics_head(),
        "</head>",
        '<body style="margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'color:#111;background:#fff">',
        '<div style="max-width:880px;margin:0 auto;padding:32px 20px 60px">',
        _nav(public),
        '<p style="color:#6b7280;font-size:13px;text-transform:uppercase;letter-spacing:.08em;margin:0 0 8px">'
        "Curated · flight deals</p>",
        f'<h1 style="font-size:32px;margin:0 0 10px">{col.emoji} {_esc(col.title)}</h1>',
        f'<p style="font-size:17px;color:#374151;margin:0 0 10px">{_esc(col.lead)}</p>',
        f'<p style="color:#6b7280;margin:0 0 22px">{routes(col.count)} · from {usd(col.cheapest)} · '
        f"updated {_fmt_updated(updated)} · round trip, per person, from Almaty (ALA)</p>",
        '<table style="width:100%;border-collapse:collapse;font-size:15px">',
        '<thead><tr style="text-align:left;color:#6b7280;font-size:13px;text-transform:uppercase">'
        '<th style="padding:8px 12px">Destination</th><th style="padding:8px 12px">Dates</th>'
        '<th style="padding:8px 12px">Airline</th><th style="padding:8px 12px">Price</th>'
        '<th style="padding:8px 12px"></th></tr></thead>',
        "<tbody>" + _rows(col) + "</tbody></table>",
        f'<p style="margin:24px 0 6px"><a href="{AVIASALES_CTA}" style="color:#2563eb;text-decoration:underline">Search all flights →</a></p>',
        '<p style="color:#6b7280;font-size:13px">Affiliate links. Prices change fast; the final '
        "price is shown at booking. Amounts in USD, converted from RUB at %.4f (%s)." % (rate, _esc(fx_note)),
        "</p>",
        f'<p style="font-size:14px;color:#374151;margin-top:22px">Live boards: '
        f'<a href="{public}/flights/almaty/" style="color:#2563eb;text-decoration:none">flights from Almaty</a> · '
        f'<a href="{public}/collections/" style="color:#2563eb;text-decoration:none">Russian version</a></p>',
        '<h2 style="font-size:22px;margin:30px 0 14px">More collections</h2>',
        _cards(cols, public, exclude=col.slug),
        f'<p style="font-size:13px;color:#6b7280;margin-top:26px">© Content Factory · '
        f'<a href="{public}/privacy.html" style="color:#6b7280">Privacy</a> · '
        f'<a href="{public}/terms.html" style="color:#6b7280">Terms</a></p>',
        "</div></body></html>",
    ])


def render_hub(cols: Sequence[Collection], updated: Optional[datetime], rate: float,
               fx_note: str, public: str = PUBLIC) -> str:
    cheapest = min((c.cheapest for c in cols), default=0)
    description = ("Curated cheap-flight collections from Almaty, Kazakhstan: under $150, Central Asia, "
                   "domestic fares and long-stay deals. Refreshed daily.")
    return "\n".join([
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Cheap flights from Almaty — curated collections | Content Factory</title>",
        f'<meta name="description" content="{_esc(description)}">',
        f'<link rel="canonical" href="{public}{ROOT_PREFIX}/">',
        '<meta property="og:type" content="website">',
        '<meta property="og:title" content="Cheap flights from Almaty — curated collections">',
        f'<meta property="og:description" content="{_esc(description)}">',
        f'<meta property="og:url" content="{public}{ROOT_PREFIX}/">',
        analytics_head(),
        "</head>",
        '<body style="margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'color:#111;background:#fff">',
        '<div style="max-width:880px;margin:0 auto;padding:32px 20px 60px">',
        _nav(public),
        '<p style="color:#6b7280;font-size:13px;text-transform:uppercase;letter-spacing:.08em;margin:0 0 8px">'
        "Collections</p>",
        '<h1 style="font-size:32px;margin:0 0 10px">Cheap flights from Almaty</h1>',
        f'<p style="color:#6b7280;margin:0 0 24px">{len(cols)} collections · from {usd(cheapest)} · '
        f"updated {_fmt_updated(updated)}. Built from live Aviasales fares for departures from "
        "Almaty, Kazakhstan.</p>",
        _cards(cols, public),
        f'<p style="font-size:14px;color:#374151;margin-top:18px">Full board: '
        f'<a href="{public}/flights/almaty/" style="color:#2563eb;text-decoration:none">all flights from Almaty</a> · '
        f'<a href="{public}/collections/" style="color:#2563eb;text-decoration:none">русская версия</a></p>',
        f'<p style="color:#6b7280;font-size:13px;margin-top:8px">Affiliate links. Prices change fast. '
        "USD amounts converted from RUB at %.4f (%s)." % (rate, _esc(fx_note)),
        "</p>",
        f'<p style="font-size:13px;color:#6b7280;margin-top:22px">© Content Factory · '
        f'<a href="{public}/privacy.html" style="color:#6b7280">Privacy</a> · '
        f'<a href="{public}/terms.html" style="color:#6b7280">Terms</a></p>',
        "</div></body></html>",
    ])


def render_post(col: Collection, updated: Optional[datetime], public: str = PUBLIC,
                limit: int = 5) -> str:
    deals = col.deals[:limit]
    lines = [
        f"{col.emoji} <b>{_esc(col.title)}</b>",
        f"<i>{routes(col.count)} · updated {updated.day if updated else 'today'} "
        f"{MONTHS[(updated.month - 1) if updated else 0]}</i>",
        "",
    ]
    for deal in deals:
        nights = (" · %d %s" % (deal.nights, "night" if deal.nights == 1 else "nights")) if deal.nights else ""
        lines.append(
            f'• <a href="{_esc(deal.link)}">{_esc(geo.city_name(deal.dest, "en"))}</a> — '
            f"<b>{usd(deal.price)}</b> · {_esc(fmt_dates(deal.dep, deal.ret))}{nights}"
        )
    lines += [
        "",
        f'👉 <a href="{public}{ROOT_PREFIX}/{col.slug}/">Full collection</a> · '
        f'<a href="{AVIASALES_CTA}">Find cheaper</a>',
        "#ad",
    ]
    text = "\n".join(lines)
    while len(text) > TELEGRAM_LIMIT and len(deals) > 1:
        deals = deals[:-1]
        text = render_post(Collection(col.slug, col.title, col.lead, col.emoji, deals, col.seo),
                           updated, public, limit=len(deals))
    return text


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------
def write_site(out_dir: Path, cols: Sequence[Collection], updated: Optional[datetime],
               rate: float, fx_note: str, public: str = PUBLIC) -> List[Path]:
    out_dir = Path(out_dir)
    written: List[Path] = []
    hub = out_dir / "index.html"
    hub.parent.mkdir(parents=True, exist_ok=True)
    hub.write_text(render_hub(cols, updated, rate, fx_note, public), encoding="utf-8")
    written.append(hub)
    keep = {c.slug for c in cols}
    for child in sorted(out_dir.iterdir()):
        if child.is_dir() and child.name not in keep and (child / "index.html").exists():
            (child / "index.html").unlink()
            if not any(child.iterdir()):
                child.rmdir()
    for col in cols:
        target = out_dir / col.slug / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_page(col, cols, updated, rate, fx_note, public), encoding="utf-8")
        written.append(target)
    return written


def write_posts(out_dir: Path, cols: Sequence[Collection], updated: Optional[datetime],
                public: str = PUBLIC) -> List[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for col in cols:
        target = out_dir / ("%s.html" % col.slug)
        target.write_text(render_post(col, updated, public), encoding="utf-8")
        written.append(target)
    return written


def sitemap_urls(cols: Sequence[Collection], public: str = PUBLIC) -> List[str]:
    return [public + ROOT_PREFIX + "/"] + ["%s%s/%s/" % (public, ROOT_PREFIX, c.slug) for c in cols]
