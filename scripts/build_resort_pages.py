#!/usr/bin/env python3
"""Страницы курортов: город/регион внутри страны + сезон.

Цены берутся из сводки по стране (DESTINATIONS) с явной пометкой, что это минимальная
цена по стране; текст по курортам — ручной, без выдуманных цифр по конкретному отелю.

  .venv/bin/python scripts/build_resort_pages.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

CF = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CF / "scripts"))

from build_destination_pages import (  # noqa: E402
    ABROAD, CSS, DATES, DESTINATIONS, GH, SUBSCRIBE_TEMPLATE, UPDATED, esc,
)

DOCS = CF / "docs"
BY_SLUG = {d["slug"]: d for d in DESTINATIONS}

RESORTS = [
    {"slug": "antalya", "name": "Анталия", "country": "turciya", "sea": "Средиземное море",
     "intro": "Крупнейший курортный регион Турции: длинная береговая линия, отели «всё включено», "
              "аквапарки и большой выбор пляжей — от Коньяалты до Белека.",
     "for": "Семьи с детьми, пары, первый пакетный тур",
     "season": "В декабре море прохладное, зато цены минимальные и работают крытые бассейны и спа.",
     "spots": ["Белек", "Коньяалты", "Сиде", "Аланья"]},
    {"slug": "bodrum", "name": "Бодрум", "country": "turciya", "sea": "Эгейское море",
     "intro": "Эгейское побережье Турции: белые дома, марины, бутик-отели и более спокойный, "
              "«европейский» ритм по сравнению с Анталией.",
     "for": "Пары, любители яхт и размеренного отдыха",
     "season": "Зимой курорт затихает: часть отелей закрыта, зато цены и виды без толп.",
     "spots": ["Ялыкавак", "Гюмбет", "Тюркбюкю"]},
    {"slug": "hurgada", "name": "Хургада", "country": "egipet", "sea": "Красное море",
     "intro": "Основной пляжный курорт Египта: коралловые рифы прямо у берега, отели all inclusive "
              "и самый короткий перелёт к тёплому морю зимой.",
     "for": "Дайверы, семьи, те, кому нужно море в декабре",
     "season": "Вода в декабре +22…+24 °C — купаться комфортно, воздух +23…+26 °C.",
     "spots": ["Макади", "Сахль Хашиш", "Эль-Гуна"]},
    {"slug": "sharm", "name": "Шарм-эль-Шейх", "country": "egipet", "sea": "Красное море",
     "intro": "Юг Синая: рифы Рас-Мохаммеда, бухты с прозрачной водой и отели с собственными "
              "пляжами — классика зимнего Египта.",
     "for": "Снорклинг, дайвинг, спокойный пляжный отдых",
     "season": "Зимой вода теплее, чем в Хургаде за счёт глубины бухт; ветер — норма для Синая.",
     "spots": ["Наама Бей", "Шарм-эль-Майя", "Рас-Ум-Сид"]},
    {"slug": "dubai", "name": "Дубай", "country": "oae", "sea": "Персидский залив",
     "intro": "Город-курорт: пляжи Джумейры, аквапарки, торговые центры и самая высокая башня мира — "
              "поездка без языкового барьера и с коротким перелётом.",
     "for": "Шопинг, семьи, те, кто не любит «только пляж»",
     "season": "Декабрь — лучший месяц: +24…+27 °C, вода тёплая, вечером комфортно гулять.",
     "spots": ["Джумейра", "Марина", "Пальма Джумейра"]},
    {"slug": "phuket", "name": "Пхукет", "country": "tailand", "sea": "Андаманское море",
     "intro": "Главный остров Таиланда: десятки пляжей на любой вкус, ночная жизнь Патонга и "
              "островные экскурсии к Пхи-Пхи и Симиланам.",
     "for": "Пляжи + экскурсии, компании, пары",
     "season": "Декабрь — высокий сезон: сухо, море спокойное, но цены выше среднего.",
     "spots": ["Патонг", "Ката", "Карон", "Най Харн"]},
    {"slug": "pattaya", "name": "Паттайя", "country": "tailand", "sea": "Сиамский залив",
     "intro": "Бюджетный и оживлённый курорт рядом с Бангкоком: доступные отели, русскоязычная "
              "инфраструктура и много развлечений.",
     "for": "Бюджетный отдых, компании, длинные поездки",
     "season": "Зимой сухой сезон, море спокойное; вечером — прогулки по набережной.",
     "spots": ["Джомтьен", "Праттамнак", "Наклуа"]},
    {"slug": "limassol", "name": "Лимассол", "country": "kipr", "sea": "Средиземное море",
     "intro": "Второй по величине город Кипра: набережная, марина, пляжи с «Голубым флагом» и "
              "короткий перелёт из России.",
     "for": "Спокойный отдых, семьи, зимние прогулки",
     "season": "В декабре +17…+20 °C: купаются не все, зато экскурсии и прогулки комфортны.",
     "spots": ["Айя-Напа", "Пафос", "Протарас"]},
    {"slug": "krit", "name": "Крит", "country": "greciya", "sea": "Средиземное море",
     "intro": "Самый большой греческий остров: пляжи с розовым песком, ущелья, критская кухня и "
              "античные памятники в получасе езды от курортов.",
     "for": "Пляжи + история, гастрономия, пары",
     "season": "Зимой часть отелей закрыта, зато цены ниже и нет жары для экскурсий.",
     "spots": ["Ханья", "Ретимно", "Ираклион", "Элунда"]},
    {"slug": "bali", "name": "Бали", "country": "indoneziya", "sea": "Индийский океан",
     "intro": "Остров с другой атмосферой: рисовые террасы, храмы, сёрф-споты и виллы с бассейнами — "
              "поездка не только за пляжем.",
     "for": "Сёрфинг, виллы, длинные поездки, удалённая работа",
     "season": "Декабрь — сезон дождей: короткие ливни, высокая влажность, но зелень и цены ниже.",
     "spots": ["Убуд", "Чангу", "Семиньяк", "Нуса-Дуа"]},
]


def _graph(url: str, name: str, country: dict, faq: list[tuple[str, str]]) -> dict:
    return {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "@id": url + "#page", "url": url, "inLanguage": "ru", "name": name},
        {"@type": "TouristDestination", "@id": url + "#dest", "name": name,
         "touristType": "Пляжный отдых", "address": {"@type": "PostalAddress", "addressCountry": country["name"]}},
        {"@type": "BreadcrumbList", "@id": url + "#crumb", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Главная", "item": GH + "/"},
            {"@type": "ListItem", "position": 2, "name": "Курорты", "item": GH + "/resorts/"},
            {"@type": "ListItem", "position": 3, "name": name, "item": url}]},
        {"@type": "FAQPage", "@id": url + "#faq", "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}]}


def build_resort(r: dict) -> str:
    country = BY_SLUG[r["country"]]
    url = f"{GH}/resorts/{r['slug']}/"
    title = f"{r['name']}: туры в декабре 2026 — цены за двоих, сезон и курорты"
    desc = (f"{r['name']} ({country['name']}): чем заняться зимой, какие пляжи и курорты рядом, "
            f"ориентир по цене — от {country['price']} ₽ за двоих по стране в сводке {UPDATED}.")
    lead = (f"{r['name']}, {country['name']}: перелёт + отель в пакете, сезон {DATES}. "
            f"Минимальная цена по стране в сводке — {country['price']} ₽ за двоих; "
            f"цена по конкретному отелю в {r['name']} зависит от дат и категории.")
    faq = [
        (f"Сколько стоит тур в {r['name']} на двоих?",
         f"В сводке Travelata минимальная цена по {country['name']} — {country['price']} ₽ за двоих "
         f"({country['nights']}), перелёт + отель. Цена именно по {r['name']} зависит от отеля и дат: "
         f"смотрите предложения на странице страны."),
        (f"Когда лучше ехать в {r['name']}?",
         f"Сезон сводки: {DATES}. {r['season']}"),
        (f"Кому подходит {r['name']}?",
         f"{r['for']}. Рядом: {', '.join(r['spots'])}."),
    ]
    tags = "".join(f'<span class="tag">{esc(t)}</span>' for t in [r["sea"], r["for"], *r["spots"][:3]])
    spots = "".join(f'<a class="part" href="{GH}/destinations/{country["slug"]}/">{esc(s)}</a>'
                    for s in r["spots"])
    sub_block = SUBSCRIBE_TEMPLATE.replace("__SLUG__", "resort-" + r["slug"])
    body = f"""
<div class="price"><b>{esc(country['price'])} ₽</b><span>за двоих · ориентир по стране</span></div>
<div class="tags">{tags}</div>
<p class="lead">{esc(r['intro'])}</p>
<p><a class="btn" href="{GH}/destinations/{country['slug']}/">Смотреть предложения в {esc(country['name'])} →</a></p>
<p class="note">Цена — минимальная по {esc(country['name'])} из сводки {UPDATED}; по конкретному отелю
в {esc(r['name'])} стоимость выше и зависит от дат.</p>
<h2>Курорты рядом</h2>
<div class="part">{spots}</div>
<h2>Сезон и погода</h2>
<p>{esc(r['season'])}</p>
<h2>Кому подходит</h2>
<p>{esc(r['for'])}</p>
<h2>Сравнить с другими направлениями</h2>
<div class="grid">
<a class="card" href="{GH}/destinations/{country['slug']}/"><b>{esc(country['name'])}</b><span>все курорты и цены</span></a>
<a class="card" href="{GH}/prices/"><b>Таблица цен</b><span>12 стран отсортированы по цене</span></a>
<a class="card" href="{GH}/compare/"><b>Сравнения</b><span>Турция vs Египет и другие пары</span></a>
<a class="card" href="{GH}/months/{'dekabr-2026' if True else ''}/"><b>Туры в декабре</b><span>все направления</span></a>
</div>
{sub_block}
"""
    navs = (f'<a href="{GH}/">Главная</a> → <a href="{GH}/resorts/">Курорты</a> → {esc(r["name"])}')
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="alternate" hreflang="ru" href="{url}">
<meta property="og:type" content="article">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{GH}/destinations/og/destinations.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{GH}/destinations/og/destinations.png">
<style>{CSS}</style>
<script type="application/ld+json">{json.dumps(_graph(url, r["name"], country, faq), ensure_ascii=False)}</script>
</head><body><div class="wrap">
<p class="crumb">{navs}</p>
<h1>{esc(r['name'])}: туры в декабре 2026</h1>
{body}
<nav><a href="{GH}/destinations/">Все направления</a><a href="{GH}/resorts/">Курорты</a>
<a href="{GH}/seasons/">Подборки</a><a href="{ABROAD}">Сводка цен</a></nav>
<footer>Данные: Travelata · сводка {UPDATED} · цены за двоих, перелёт + отель · не оферта.</footer>
</div></body></html>
"""


def build_hub() -> str:
    url = GH + "/resorts/"
    cards = "".join(
        f'<a class="card" href="{GH}/resorts/{r["slug"]}/"><b>{esc(r["name"])}</b>'
        f'<span>{esc(BY_SLUG[r["country"]]["name"])} · от {esc(BY_SLUG[r["country"]]["price"])} ₽</span></a>'
        for r in RESORTS)
    lead = "Курорты и регионы из сводки: что посмотреть зимой, когда ехать и сколько стоит перелёт + отель."
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "@id": url + "#page", "url": url, "inLanguage": "ru",
         "name": "Курорты зимой 2026–2027"},
        {"@type": "BreadcrumbList", "@id": url + "#crumb", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Главная", "item": GH + "/"},
            {"@type": "ListItem", "position": 2, "name": "Курорты", "item": url}]},
        {"@type": "ItemList", "@id": url + "#list", "itemListElement": [
            {"@type": "ListItem", "position": i, "name": r["name"],
             "url": f"{GH}/resorts/{r['slug']}/"} for i, r in enumerate(RESORTS, 1)]}]}
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Курорты зимой 2026–2027: Анталия, Хургада, Дубай, Пхукет — цены и сезон</title>
<meta name="description" content="10 курортов с описанием сезона и ценами за двоих: Анталия, Бодрум, Хургада, Шарм-эль-Шейх, Дубай, Пхукет, Паттайя, Лимассол, Крит, Бали.">
<link rel="canonical" href="{url}">
<meta name="robots" content="index,follow,max-image-preview:large">
<style>{CSS}</style>
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
</head><body><div class="wrap">
<p class="crumb"><a href="{GH}/">Главная</a> → Курорты</p>
<h1>Курорты: куда поехать зимой</h1>
<p class="lead">{lead}</p>
<div class="grid">{cards}</div>
<nav><a href="{GH}/destinations/">Все направления</a><a href="{GH}/seasons/">Подборки</a>
<a href="{GH}/prices/">Таблица цен</a><a href="{ABROAD}">Сводка цен</a></nav>
<footer>Данные: Travelata · сводка {UPDATED} · цены за двоих.</footer>
</div></body></html>
"""


def main() -> int:
    created = []
    for r in RESORTS:
        target = DOCS / "resorts" / r["slug"] / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(build_resort(r), encoding="utf-8")
        created.append(f"{GH}/resorts/{r['slug']}/")
    hub = DOCS / "resorts" / "index.html"
    hub.write_text(build_hub(), encoding="utf-8")
    created.append(GH + "/resorts/")

    sitemap = DOCS / "sitemap.xml"
    xml = sitemap.read_text(encoding="utf-8")
    extra = []
    for loc in created:
        if f"<loc>{loc}</loc>" not in xml:
            extra.append(f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>2026-11-15</lastmod>\n"
                         f"    <changefreq>weekly</changefreq>\n    <priority>0.7</priority>\n  </url>")
    if extra:
        sitemap.write_text(xml.replace("</urlset>", "\n".join(extra) + "\n</urlset>"), encoding="utf-8")
    print(f"создано страниц: {len(created)} | в sitemap: {len(extra)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
