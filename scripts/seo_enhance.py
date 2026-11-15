#!/usr/bin/env python3
"""Пост-процессор SEO для travel-лендингов: canonical/hreflang/robots, JSON-LD
(WebPage + BreadcrumbList + ItemList + FAQPage), видимый FAQ и футер-навигация.

Идемпотентен: повторный прогон ничего не дублирует (проверяет canonical и ld+json).

Использование::

    .venv/bin/python scripts/seo_enhance.py --page all        # обновить все три страницы
    .venv/bin/python scripts/seo_enhance.py --page abroad

Модуль также импортируется генераторами (build_us_landing.py, add_travel_promos.py,
publish_nezabyvaemoe.py), чтобы SEO не терялось при пересборке страниц.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
GH = "https://valdislavn-spec.github.io/content-factory"
SURGE = "https://nezabyvaemoe.surge.sh/"

PRICE_FALLBACK = {
    "Абхазия": "18473", "Турция": "41754", "ОАЭ": "66704", "Египет": "74015",
    "Кипр": "69302", "Таиланд": "98739", "Греция": "89757", "Вьетнам": "120509",
    "Индонезия": "124999", "Мальдивы": "155760", "Испания": "171488", "Италия": "240442",
}
NOTES = {
    "Абхазия": "5 ночей · самое дешёвое направление", "Турция": "5–9 ночей · всё включено",
    "ОАЭ": "море и шопинг", "Египет": "тепло и дайвинг", "Кипр": "5 ночей",
    "Таиланд": "Пхукет и Паттайя", "Греция": "5 ночей", "Вьетнам": "5 ночей",
    "Индонезия": "5 ночей", "Мальдивы": "виллы над водой", "Испания": "5 ночей",
    "Италия": "5 ночей · самое дорогое",
}
US_DESTS = [
    ("Cancún", "Mexico", "4h nonstop", "Best Dec–Apr"),
    ("London", "UK", "7h nonstop", "Best May–Sep"),
    ("Paris", "France", "7h 30m nonstop", "Best Apr–Jun, Sep–Oct"),
    ("Rome", "Italy", "9h nonstop", "Best Apr–Jun, Sep–Oct"),
    ("Barcelona", "Spain", "8h nonstop", "Best May–Jun, Sep"),
    ("Lisbon", "Portugal", "~9h, 1 stop", "Best Apr–Jun, Sep–Oct"),
    ("Reykjavík", "Iceland", "5h 30m nonstop", "Best Jun–Aug, Sep"),
    ("Dublin", "Ireland", "6h 30m nonstop", "Best May–Sep"),
    ("Tokyo", "Japan", "14h nonstop", "Best Mar–May, Oct–Nov"),
    ("Bali", "Indonesia", "~22h, 1 stop", "Best Apr–Oct"),
    ("Mexico City", "Mexico", "5h nonstop", "Best Mar–May, Oct–Nov"),
    ("Punta Cana", "Dominican Republic", "4h nonstop", "Best Dec–Apr"),
]

FAQ_ABROAD = [
    ("Что входит в пакетный тур?", "Перелёт и проживание в отеле. Трансфер, питание и страховка зависят от выбранного отеля и тарифа — они указаны в карточке предложения на Travelata."),
    ("Сколько стоит тур на двоих в ноябре–декабре 2026?", "В сводке 958 предложений: от 18 473 ₽ за двоих (Абхазия, 5 ночей) до 240 442 ₽ (Италия). Даты заездов — 17.11–17.12.2026, 5–9 ночей."),
    ("Куда дешевле всего поехать зимой?", "Самые низкие цены в сводке: Абхазия от 18 473 ₽, Турция от 41 754 ₽, ОАЭ от 66 704 ₽, Кипр от 69 302 ₽, Египет от 74 015 ₽, Греция от 89 757 ₽."),
    ("На сколько ночей рассчитаны предложения?", "От 5 до 9 ночей в зависимости от отеля и даты заезда. Точный срок указан в карточке каждого предложения."),
    ("Нужна ли виза?", "Зависит от страны и гражданства. Для части направлений виза не нужна, для других требуется оформление — проверяйте условия перед бронированием."),
    ("Как забронировать тур?", "Нажмите на карточку отеля в сводке — откроется страница Travelata с датами и ценами. Цена фиксируется в момент бронирования."),
]
FAQ_PACKAGE = [
    ("Что такое сводка пакетных туров?", "Одна страница со всеми направлениями сезона: минимальные цены за двоих, даты заездов и отели с карточками на Travelata."),
    ("Сколько стран в сводке?", "12 зарубежных направлений плюс туры по России. По каждому направлению указана минимальная цена и число предложений."),
    ("Какие даты заездов?", "Сводка собрана на ноябрь–декабрь 2026, длительность — 5–9 ночей в зависимости от отеля."),
    ("Почему цены такие разные?", "Цена зависит от страны, отеля, питания, срока и даты вылета. Самые дешёвые направления — Абхазия и Турция, самые дорогие — Италия и Испания."),
    ("Цены настоящие?", "Да, это минимальные цены из живых предложений Travelata на дату сборки. Цены меняются ежедневно, актуальные видны по клику на отель."),
    ("Как забронировать?", "Нажмите на отель в сводке — откроется карточка на Travelata с датами, составом тура и ценой. Бронирование и оплата происходят на стороне партнёра."),
]
FAQ_US = [
    ("What's included in these packages?", "Flight and hotel. Transfers, meals and insurance depend on the rate you pick — each partner page lists exactly what's covered."),
    ("How long is the flight from New York?", "From 4 hours nonstop to Cancún and Punta Cana, up to 14 hours to Tokyo. One-stop options (Lisbon, Bali) take longer."),
    ("When is the cheapest time to travel?", "Shoulder months are usually cheaper: May–June and September–October for Europe, May–November for the Caribbean. Each card lists the best months for that destination."),
    ("Do I need a visa?", "It depends on your passport and destination. US passport holders don't need a visa for Mexico, the Dominican Republic, the UK or the EU for short trips, but rules change — verify before booking."),
    ("Are the promo codes verified?", "Yes — we check them on the partner's own page and record the date. Codes can expire or change, so the final terms are always shown at checkout."),
    ("Do you show live prices?", "No. We show destinations, flight times and seasons, then send you to a live search page where current prices are shown for your dates."),
]


# ---------- helpers ----------

def _prices(html: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for name in PRICE_FALLBACK:
        idx = html.find(name)
        if idx < 0:
            continue
        seg = html[idx:idx + 1500]
        match = re.search(r"([0-9][0-9 ]{3,7})\s*₽", seg)
        if match:
            found[name] = match.group(1).replace(" ", "")
    return found


def _faq_html(items: list[tuple[str, str]], title: str, subtitle: str) -> str:
    rows = "".join(
        '<details style="background:rgba(255,255,255,.04);border:1px solid rgba(148,163,255,.2);'
        'border-radius:14px;padding:16px 20px;margin:0 0 12px">'
        f'<summary style="cursor:pointer;font-size:18px;font-weight:700">{q}</summary>'
        f'<p style="margin:12px 0 0;color:#b9c3e6;font-size:15.5px;line-height:1.55">{a}</p>'
        "</details>"
        for q, a in items
    )
    return (f'<section id="faq" style="margin:44px 0 0">'
            f'<h2 style="font-size:28px;margin:0 0 12px">{title}</h2>'
            f'<p style="margin:0 0 20px;color:#b9c3e6;font-size:16px">{subtitle}</p>'
            f"{rows}</section>\n")


def _graph(url: str, lang: str, page_name: str, crumbs: list[tuple[str, str]], extra: list[dict]) -> str:
    data = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "@id": url + "#page", "url": url, "name": page_name, "inLanguage": lang,
         "isPartOf": {"@type": "WebSite", "@id": GH + "/#website", "name": "Travelata — сводки цен", "url": GH + "/"}},
        {"@type": "BreadcrumbList", "@id": url + "#breadcrumb",
         "itemListElement": [{"@type": "ListItem", "position": i, "name": n, "item": u}
                             for i, (n, u) in enumerate(crumbs, 1)]},
        *extra]}
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + "</script>\n"


def _faq_schema(items: list[tuple[str, str]], url: str, lang: str) -> dict:
    return {"@type": "FAQPage", "@id": url + "#faq", "inLanguage": lang,
            "mainEntity": [{"@type": "Question", "name": q,
                            "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in items]}


def _list_schema(items: list[dict], url: str, lang: str, name: str) -> dict:
    return {"@type": "ItemList", "@id": url + "#list", "name": name, "inLanguage": lang,
            "itemListElement": items}


def _head(url: str, lang: str) -> str:
    return (f'<link rel="canonical" href="{url}">\n'
            '<meta name="robots" content="index,follow,max-image-preview:large">\n'
            f'<link rel="alternate" hreflang="{lang}" href="{url}">\n'
            f'<link rel="alternate" hreflang="x-default" href="{url}">\n')


def _nav(lang: str) -> str:
    if lang == "ru":
        links = [(SURGE, "Пакетные туры 2026"), (GH + "/flight-hotel-abroad/", "Туры за рубеж"),
                 (GH + "/flight-hotel-us/", "US travel deals"), (GH + "/travel/", "Гайды по путешествиям")]
    else:
        links = [(GH + "/flight-hotel-us/", "US travel deals"), (SURGE, "Package tours (RU)"),
                 (GH + "/flight-hotel-abroad/", "Tours abroad (RU)"), (GH + "/travel/", "Travel guides")]
    a = "".join(f'<a href="{u}" style="color:#a5b4fc;text-decoration:none;margin-right:16px">{t}</a>' for u, t in links)
    return f'<nav style="margin:26px 0;font-size:14.5px;line-height:2">{a}</nav>\n'


def _titles(html: str, old_title: str, new_title: str, new_desc: str) -> str:
    if old_title and old_title not in html:
        return html
    html = re.sub(r"<title>[^<]*</title>", f"<title>{new_title}</title>", html, count=1)
    html = re.sub(r'<meta name="description" content="[^"]*">',
                  f'<meta name="description" content="{new_desc}">', html, count=1)
    return html


# ---------- pages ----------

def enhance_abroad(html: str) -> str:
    url = GH + "/flight-hotel-abroad/"
    html = _titles(html, "Пакетные туры за рубеж — сводка предложений", "Пакетные туры за рубеж 2026: 12 стран от 18 473 ₽",
                   "Пакетные туры за рубеж на ноябрь–декабрь 2026: 958 предложений по 12 странам, от 18 473 ₽ за двоих. Турция, Египет, ОАЭ, Таиланд, Мальдивы — цены и отели.")
    if 'rel="canonical" href="' + url in html:
        return html
    anchor = re.search(r'<meta name="description" content="[^"]*">\n', html)
    if anchor:
        html = html[:anchor.end()] + _head(url, "ru") + html[anchor.end():]
    prices = _prices(html) or PRICE_FALLBACK
    items = [{"@type": "ListItem", "position": i,
              "item": {"@type": "Product", "name": f"Пакетный тур: {name}",
                       "description": NOTES.get(name, ""),
                       "offers": {"@type": "Offer", "price": prices.get(name, PRICE_FALLBACK[name]),
                                  "priceCurrency": "RUB", "availability": "https://schema.org/InStock",
                                  "url": url}}}
             for i, name in enumerate(PRICE_FALLBACK, 1)]
    ld = _graph(url, "ru", "Пакетные туры за рубеж 2026 — цены по 12 странам",
                [("Главная", GH + "/"), ("Пакетные туры за рубеж", url)],
                [_list_schema(items, url, "ru", "Направления и минимальные цены"), _faq_schema(FAQ_ABROAD, url, "ru")])
    faq = _faq_html(FAQ_ABROAD, "Частые вопросы о пакетных турах",
                    "Цены и даты — из сводки, 5–9 ночей, на двоих.")
    return html.replace("<footer>", ld + faq + _nav("ru") + "<footer>", 1)


def enhance_us(html: str) -> str:
    url = GH + "/flight-hotel-us/"
    html = _titles(html, "US Travel Deals — flights, stays &amp; experiences", "US Travel Deals 2026: 12 winter escapes + promo codes",
                   "Cheap travel deals from the US: 12 destinations from New York with flight times and best months, plus verified partner promo codes. Flights, stays and experiences.")
    if 'rel="canonical" href="' + url in html:
        return html
    anchor = re.search(r'<meta name="description" content="[^"]*">\n', html)
    if anchor:
        html = html[:anchor.end()] + _head(url, "en") + html[anchor.end():]
    items = [{"@type": "ListItem", "position": i,
              "item": {"@type": "TouristDestination", "name": name,
                       "description": f"{country} · {flight} · {season}", "url": url + "#destinations"}}
             for i, (name, country, flight, season) in enumerate(US_DESTS, 1)]
    ld = _graph(url, "en", "US travel deals — flights, stays and experiences",
                [("Home", GH + "/"), ("US travel deals", url)],
                [_list_schema(items, url, "en", "Destinations from the US"), _faq_schema(FAQ_US, url, "en")])
    faq = _faq_html(FAQ_US, "Frequently asked questions",
                    "Destinations and seasons are checked regularly; prices change daily.")
    return html.replace("<footer>", ld + faq + _nav("en") + "<footer>", 1)


def enhance_package(html: str) -> str:
    url = SURGE
    if 'application/ld+json' in html and 'id="faq"' in html:
        return html
    html = re.sub(r"<title>Незабываемое путешествие — Travelata</title>",
                  "<title>Пакетные туры 2026: 12 стран, от 18 473 ₽ за двоих</title>", html, count=1)
    if '<link rel="canonical"' in html and 'max-image-preview' not in html:
        html = re.sub(r'(<link rel="canonical"[^>]*>\n?)',
                      r'\1<meta name="robots" content="index,follow,max-image-preview:large">\n'
                      f'<link rel="alternate" hreflang="ru" href="{url}">\n'
                      f'<link rel="alternate" hreflang="x-default" href="{url}">\n', html, count=1)
    prices = _prices(html) or PRICE_FALLBACK
    items = [{"@type": "ListItem", "position": i,
              "item": {"@type": "Product", "name": f"Тур: {name} — {NOTES.get(name, '')}",
                       "offers": {"@type": "Offer", "price": prices.get(name, PRICE_FALLBACK[name]),
                                  "priceCurrency": "RUB", "availability": "https://schema.org/InStock",
                                  "url": url}}}
             for i, name in enumerate(PRICE_FALLBACK, 1)]
    ld = _graph(url, "ru", "Пакетные туры 2026 — сводка цен по 12 направлениям",
                [("Главная", GH + "/"), ("Пакетные туры", url)],
                [_list_schema(items, url, "ru", "Направления и минимальные цены"), _faq_schema(FAQ_PACKAGE, url, "ru")])
    faq = _faq_html(FAQ_PACKAGE, "Частые вопросы", "Ответы по сводке: цены, даты, состав тура.")
    return html.replace("<footer>", ld + faq + _nav("ru") + "<footer>", 1)


PAGES = {
    "abroad": (DOCS / "flight-hotel-abroad/index.html", enhance_abroad),
    "us": (DOCS / "flight-hotel-us/index.html", enhance_us),
    "package": (DOCS / "nezabyvaemoe-puteshestvie/index.html", enhance_package),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page", choices=[*PAGES, "all"], default="all")
    args = parser.parse_args()
    names = list(PAGES) if args.page == "all" else [args.page]
    for name in names:
        path, func = PAGES[name]
        if not path.exists():
            print(f"{name}: нет файла {path}")
            continue
        before = path.read_text(encoding="utf-8")
        after = func(before)
        if after == before:
            print(f"{name}: без изменений")
            continue
        path.write_text(after, encoding="utf-8")
        print(f"{name}: SEO добавлено ({len(after)//1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
