#!/usr/bin/env python3
"""Programmatic SEO: страницы направлений /destinations/<slug>/ + хаб /destinations/.

Данные (цены, ночи, даты) — из сводки docs/flight-hotel-abroad (13.11.2026).
Страницы статические, с JSON-LD (WebPage + BreadcrumbList + Product/Offer + FAQPage),
canonical, robots, перелинковкой между направлениями и партнёрскими CTA.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT = DOCS / "destinations"
GH = "https://valdislavn-spec.github.io/content-factory"
ABROAD = GH + "/flight-hotel-abroad/"
DATES = "17.11–17.12.2026"
UPDATED = "13.11.2026"

PARTNERS = {
    "tiqets": ("Музеи и экскурсии", "https://tiqets.tpk.ro/ufgJDVmO"),
    "kiwitaxi": ("Трансфер из аэропорта", "https://kiwitaxi.tpk.ro/xmQYmqIl"),
    "saily": ("eSIM для интернета", "https://saily.tpk.ro/QSNyiXp7"),
    "localrent": ("Аренда авто", "https://localrent.tpk.ro/edD3Ejwe"),
    "aviasales": ("Билеты Aviasales", "https://aviasales.tpk.ro/2ZW95Xpf"),
}

DESTINATIONS = [
    {"slug": "turciya", "phrase": "в Турцию", "name": "Турция", "price": "41 754", "nights": "5–9 ночей",
     "blurb": "Самое популярное зарубежное направление сезона: море, отели «всё включено» и большой выбор курортов — от Анталии до Бодрума.",
     "highlights": ["Отели «всё включено»", "Перелёт + отель в пакете", "Море и бассейны", "Подходит для семьи"],
     "faq": [("Сколько стоит тур в Турцию на двоих?", "Минимальная цена в сводке на 13.11.2026 — 41 754 ₽ за двоих, перелёт + отель.")]},
    {"slug": "egipet", "phrase": "в Египет", "name": "Египет", "price": "74 015", "nights": "5–9 ночей",
     "blurb": "Зимой в Египте тепло: Красное море, кораллы, дайвинг и отели с питанием по системе «всё включено».",
     "highlights": ["Красное море и рифы", "Дайвинг и снорклинг", "Тепло в декабре", "Отели all inclusive"],
     "faq": [("Сколько стоит тур в Египет на двоих?", "Минимальная цена в сводке на 13.11.2026 — 74 015 ₽ за двоих, перелёт + отель.")]},
    {"slug": "oae", "phrase": "в ОАЭ", "name": "ОАЭ", "price": "66 704", "nights": "5–9 ночей",
     "blurb": "Дубай и другие эмираты: пляжи, торговые центры, парки развлечений и короткий перелёт.",
     "highlights": ["Пляжи и аквапарки", "Шопинг", "Современные отели", "Тепло зимой"],
     "faq": [("Сколько стоит тур в ОАЭ на двоих?", "Минимальная цена в сводке на 13.11.2026 — 66 704 ₽ за двоих, перелёт + отель.")]},
    {"slug": "tailand", "phrase": "в Таиланд", "name": "Таиланд", "price": "98 739", "nights": "5–9 ночей",
     "blurb": "Пхукет, Паттайя и острова: тёплое море, уличная еда и большой выбор отелей на любой бюджет.",
     "highlights": ["Пхукет и Паттайя", "Острова и экскурсии", "Тёплое море", "Разные бюджеты"],
     "faq": [("Сколько стоит тур в Таиланд на двоих?", "Минимальная цена в сводке на 13.11.2026 — 98 739 ₽ за двоих, перелёт + отель.")]},
    {"slug": "maldivy", "phrase": "на Мальдивы", "name": "Мальдивы", "price": "155 760", "nights": "5–9 ночей",
     "blurb": "Атоллы и виллы над водой — самое дорогое пляжное направление в сводке, но с большим разбросом цен по отелям.",
     "highlights": ["Виллы над водой", "Прозрачная вода", "Снорклинг", "Медовый месяц"],
     "faq": [("Сколько стоит тур на Мальдивы на двоих?", "Минимальная цена в сводке на 13.11.2026 — 155 760 ₽ за двоих, перелёт + отель.")]},
    {"slug": "kipr", "phrase": "на Кипр", "name": "Кипр", "price": "69 302", "nights": "5–9 ночей",
     "blurb": "Средиземное море и короткий перелёт: подходит для спокойного отдыха и поездок с детьми.",
     "highlights": ["Средиземное море", "Короткий перелёт", "Пляжи", "Спокойный отдых"],
     "faq": [("Сколько стоит тур на Кипр на двоих?", "Минимальная цена в сводке на 13.11.2026 — 69 302 ₽ за двоих, перелёт + отель.")]},
    {"slug": "greciya", "phrase": "в Грецию", "name": "Греция", "price": "89 757", "nights": "5–9 ночей",
     "blurb": "Материковая Греция и острова: море, античные памятники и европейский сервис.",
     "highlights": ["Острова", "Древние памятники", "Средиземное море", "Городские прогулки"],
     "faq": [("Сколько стоит тур в Грецию на двоих?", "Минимальная цена в сводке на 13.11.2026 — 89 757 ₽ за двоих, перелёт + отель.")]},
    {"slug": "vietnam", "phrase": "во Вьетнам", "name": "Вьетнам", "price": "120 509", "nights": "5–9 ночей",
     "blurb": "Нячанг и Фукуок: длинные пляжи, местная кухня и недорогая жизнь на месте.",
     "highlights": ["Длинные пляжи", "Нячанг и Фукуок", "Недорогая еда", "Экскурсии"],
     "faq": [("Сколько стоит тур во Вьетнам на двоих?", "Минимальная цена в сводке на 13.11.2026 — 120 509 ₽ за двоих, перелёт + отель.")]},
    {"slug": "indoneziya", "phrase": "на Бали", "name": "Индонезия", "price": "124 999", "nights": "5–9 ночей",
     "blurb": "Бали: рисёвые террасы, океан, сёрф и отели на любой вкус — от гестхаусов до вилл.",
     "highlights": ["Бали", "Сёрф и океан", "Рисёвые террасы", "Виллы"],
     "faq": [("Сколько стоит тур на Бали на двоих?", "Минимальная цена в сводке на 13.11.2026 — 124 999 ₽ за двоих, перелёт + отель.")]},
    {"slug": "ispaniya", "phrase": "в Испанию", "name": "Испания", "price": "171 488", "nights": "5–9 ночей",
     "blurb": "Барселона, Валенсия и побережье: архитектура, море и европейская кухня. Одно из самых дорогих направлений сводки.",
     "highlights": ["Барселона", "Побережье", "Архитектура", "Европейская кухня"],
     "faq": [("Сколько стоит тур в Испанию на двоих?", "Минимальная цена в сводке на 13.11.2026 — 171 488 ₽ за двоих, перелёт + отель.")]},
    {"slug": "italiya", "phrase": "в Италию", "name": "Италия", "price": "240 442", "nights": "5–9 ночей",
     "blurb": "Самое дорогое направление в сводке: Рим, музеи, кухня и возможность сэкономить на билетах и аренде авто.",
     "highlights": ["Рим и Колизей", "Музеи", "Кухня", "Поезда между городами"],
     "faq": [("Сколько стоит тур в Италию на двоих?", "Минимальная цена в сводке на 13.11.2026 — 240 442 ₽ за двоих, перелёт + отель.")]},
    {"slug": "abkhaziya", "phrase": "в Абхазию", "name": "Абхазия", "price": "18 473", "nights": "5 ночей",
     "blurb": "Самое дешёвое зарубежное направление в сводке: близко, недорого, горы и море рядом.",
     "highlights": ["Самая низкая цена", "Горы и море", "Короткая дорога", "Без перелёта в пакете"],
     "faq": [("Сколько стоит тур в Абхазию на двоих?", "Минимальная цена в сводке на 13.11.2026 — 18 473 ₽ за двоих, 5 ночей.")]},
]

FAQ_COMMON = [
    ("Что входит в пакетный тур?", "Перелёт и проживание в отеле. Трансфер, питание и страховка зависят от отеля и тарифа — они указаны в карточке предложения."),
    ("На сколько ночей рассчитаны предложения?", "От 5 до 9 ночей в зависимости от отеля и даты заезда."),
    ("Какие даты заездов?", f"Сводка собрана на {DATES}, данные обновлены {UPDATED}."),
    ("Как забронировать?", "Нажмите кнопку «Смотреть предложения» — откроется сводка Travelata с датами, отелями и ценами. Бронирование и оплата — на стороне партнёра."),
]

CSS = """
*{box-sizing:border-box}body{margin:0;background:#070b18;color:#eef2ff;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;line-height:1.5}
.wrap{max-width:900px;margin:0 auto;padding:28px 20px 70px}
a{color:#a5b4fc}
.crumb{font-size:13.5px;color:#8b98bf;margin:0 0 18px}
.crumb a{color:#8b98bf;text-decoration:none}
h1{font-size:44px;line-height:1.05;margin:0 0 10px;letter-spacing:-.02em}
h2{font-size:26px;margin:38px 0 14px}
.lead{font-size:17.5px;color:#b9c3e6;margin:0 0 22px}
.price{display:flex;align-items:baseline;gap:12px;margin:0 0 8px}
.price b{font-size:44px;color:#fde68a;font-weight:900}
.price span{font-size:16px;color:#c7d2fe}
.tags{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0 24px}
.tag{font-size:13px;padding:5px 11px;border-radius:999px;background:rgba(148,163,255,.12);color:#c7d2fe}
.btn{display:inline-block;padding:16px 26px;border-radius:14px;background:linear-gradient(92deg,#7c3aed,#db2777);color:#fff;font-weight:800;text-decoration:none;font-size:17px}
.note{font-size:13.5px;color:#8b98bf;margin:14px 0 0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}
.card{display:block;padding:16px 18px;border-radius:14px;background:rgba(255,255,255,.04);border:1px solid rgba(148,163,255,.18);text-decoration:none;color:#eef2ff}
.card b{display:block;font-size:17px;margin-bottom:4px}
.card span{font-size:13.5px;color:#fde68a}
.part{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-top:14px}
.part a{display:block;padding:14px 16px;border-radius:12px;background:rgba(124,58,237,.12);border:1px solid rgba(124,58,237,.35);text-decoration:none;color:#eef2ff;font-size:15px}
details{background:rgba(255,255,255,.04);border:1px solid rgba(148,163,255,.2);border-radius:14px;padding:16px 20px;margin:0 0 12px}
summary{cursor:pointer;font-size:17px;font-weight:700}
details p{margin:12px 0 0;color:#b9c3e6;font-size:15.5px}
footer{margin-top:44px;padding-top:20px;border-top:1px solid rgba(148,163,255,.15);font-size:13px;color:#8b98bf}
nav{margin:26px 0;font-size:14px;line-height:2}nav a{margin-right:16px;text-decoration:none;color:#a5b4fc}
"""


def esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def graph(d: dict, url: str) -> str:
    faq_items = [{"q": q, "a": a} for q, a in d["faq"] + FAQ_COMMON]
    data = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "@id": url + "#page", "url": url, "inLanguage": "ru",
         "name": f"Тур в {d['name']} — цены на {DATES}",
         "isPartOf": {"@type": "WebSite", "@id": GH + "/#website", "name": "Travelata — сводки цен", "url": GH + "/"}},
        {"@type": "BreadcrumbList", "@id": url + "#breadcrumb", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Главная", "item": GH + "/"},
            {"@type": "ListItem", "position": 2, "name": "Направления", "item": GH + "/destinations/"},
            {"@type": "ListItem", "position": 3, "name": d["name"], "item": url}]},
        {"@type": "Product", "@id": url + "#offer", "name": f"Пакетный тур: {d['name']}",
         "description": d["blurb"], "url": url,
         "offers": {"@type": "Offer", "price": d["price"].replace(" ", ""), "priceCurrency": "RUB",
                    "availability": "https://schema.org/InStock", "url": ABROAD}},
        {"@type": "FAQPage", "@id": url + "#faq", "inLanguage": "ru", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q in faq_items for q, a in [(q["q"], q["a"])]]},
    ]}
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + "</script>"


def page(d: dict) -> str:
    url = f"{GH}/destinations/{d['slug']}/"
    title = f"Тур {d['phrase']} {DATES.split('–')[0].strip()} — от {d['price']} ₽ за двоих"
    desc = (f"Пакетный тур {d['phrase']}: перелёт + отель, от {d['price']} ₽ за двоих, "
            f"{d['nights']}, заезды {DATES}. Цены и отели в сводке Travelata.")[:165]
    faq_html = "".join(
        f"<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>"
        for q, a in d["faq"] + FAQ_COMMON)
    partners = "".join(
        f'<a href="{u}" rel="sponsored nofollow noopener" target="_blank">{t}</a>'
        for t, u in PARTNERS.values())
    others = "".join(
        f'<a class="card" href="{GH}/destinations/{o["slug"]}/"><b>{o["name"]}</b><span>от {o["price"]} ₽</span></a>'
        for o in DESTINATIONS if o["slug"] != d["slug"])
    tags = "".join(f'<span class="tag">{esc(t)}</span>' for t in d["highlights"])
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="alternate" hreflang="ru" href="{url}">
<link rel="alternate" hreflang="x-default" href="{url}">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}">
<style>{CSS}</style>
{graph(d, url)}
</head><body><div class="wrap">
<p class="crumb"><a href="{GH}/">Главная</a> → <a href="{GH}/destinations/">Направления</a> → {esc(d['name'])}</p>
<h1>Тур {esc(d['phrase'])} — от {d['price']} ₽ за двоих</h1>
<div class="price"><b>от {d['price']} ₽</b><span>перелёт + отель · {esc(d['nights'])} · на 2 взрослых</span></div>
<p class="lead">{esc(d['blurb'])}</p>
<div class="tags">{tags}</div>
<p><a class="btn" href="{ABROAD}">Смотреть предложения →</a></p>
<p class="note">Цены — минимальные из сводки Travelata на {UPDATED}. Даты заездов: {DATES}. Цена фиксируется при бронировании.</p>

<h2>Партнёры для поездки</h2>
<div class="part">{partners}</div>
<p class="note">Партнёрские ссылки: мы можем получить комиссию, цена для вас не меняется.</p>

<h2>Частые вопросы</h2>
{faq_html}

<h2>Другие направления</h2>
<div class="grid">{others}</div>

<nav><a href="{GH}/flight-hotel-abroad/">Все 12 стран со ценами</a><a href="{GH}/destinations/">Хаб направлений</a><a href="{GH}/travel/">Гайды</a></nav>
<footer>Данные: Travelata, сводка обновлена {UPDATED} · цены за двоих · не является офертой.</footer>
</div></body></html>
"""


def hub() -> str:
    url = GH + "/destinations/"
    items = "".join(
        f'<a class="card" href="{GH}/destinations/{d["slug"]}/"><b>{d["name"]}</b><span>от {d["price"]} ₽ · {esc(d["nights"])}</span></a>'
        for d in sorted(DESTINATIONS, key=lambda x: int(x["price"].replace(" ", ""))))
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "@id": url + "#page", "url": url, "inLanguage": "ru",
         "name": "Направления: пакетные туры из сводки Travelata 2026"},
        {"@type": "BreadcrumbList", "@id": url + "#breadcrumb", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Главная", "item": GH + "/"},
            {"@type": "ListItem", "position": 2, "name": "Направления", "item": url}]},
        {"@type": "ItemList", "@id": url + "#list", "itemListElement": [
            {"@type": "ListItem", "position": i, "name": d["name"], "url": f"{GH}/destinations/{d['slug']}/"}
            for i, d in enumerate(sorted(DESTINATIONS, key=lambda x: int(x["price"].replace(" ", ""))), 1)]}]}
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Направления 2026: 12 стран с ценами от 18 473 ₽ за двоих</title>
<meta name="description" content="Все направления сводки Travelata: Абхазия, Турция, ОАЭ, Египет, Кипр, Греция, Таиланд, Вьетнам, Индонезия, Мальдивы, Испания, Италия — минимальные цены за двоих и даты заездов.">
<link rel="canonical" href="{url}">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="alternate" hreflang="ru" href="{url}">
<link rel="alternate" hreflang="x-default" href="{url}">
<style>{CSS}</style>
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
</head><body><div class="wrap">
<p class="crumb"><a href="{GH}/">Главная</a> → Направления</p>
<h1>Направления: 12 стран с ценами</h1>
<p class="lead">Одна сводка — все зарубежные направления сезона. Цены за двоих, перелёт + отель, заезды {DATES}. Обновлено {UPDATED}.</p>
<div class="grid">{items}</div>
<nav><a href="{ABROAD}">Полная сводка цен</a><a href="{GH}/travel/">Гайды</a></nav>
<footer>Данные: Travelata · цены за двоих · не является офертой.</footer>
</div></body></html>
"""


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for d in DESTINATIONS:
        path = OUT / d["slug"] / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(page(d), encoding="utf-8")
    (OUT / "index.html").write_text(hub(), encoding="utf-8")

    sitemap = DOCS / "sitemap.xml"
    xml = sitemap.read_text(encoding="utf-8")
    entries = []
    for d in DESTINATIONS:
        loc = f"{GH}/destinations/{d['slug']}/"
        if f"<loc>{loc}</loc>" not in xml:
            entries.append(f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>2026-11-15</lastmod>\n"
                           f"    <changefreq>weekly</changefreq>\n    <priority>0.8</priority>\n  </url>")
    hub_loc = GH + "/destinations/"
    if f"<loc>{hub_loc}</loc>" not in xml:
        entries.append(f"  <url>\n    <loc>{hub_loc}</loc>\n    <lastmod>2026-11-15</lastmod>\n"
                       f"    <changefreq>weekly</changefreq>\n    <priority>0.85</priority>\n  </url>")
    if entries:
        xml = xml.replace("</urlset>", "\n".join(entries) + "\n</urlset>")
        sitemap.write_text(xml, encoding="utf-8")
    print(f"сгенерировано страниц: {len(DESTINATIONS)} + хаб; добавлено в sitemap: {len(entries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
