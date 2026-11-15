#!/usr/bin/env python3
"""Дополнительные SEO-страницы: месяцы сезона, сравнения пар направлений, таблица цен.

Данные берутся из DESTINATIONS (build_destination_pages), без выдуманных цифр:
все цены — минимальные из сводки, даты — сезон 17.11–17.12.2026.

  .venv/bin/python scripts/build_extra_pages.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

CF = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CF / "scripts"))

from build_destination_pages import (  # noqa: E402
    ABROAD, CSS, DATES, DESTINATIONS, GH, SUBSCRIBE_TEMPLATE, UPDATED, esc,
)

DOCS = CF / "docs"
BY_SLUG = {d["slug"]: d for d in DESTINATIONS}
BY_NAME = {d["name"]: d for d in DESTINATIONS}

MONTHS = [
    ("noyabr-2026", "ноябрь 2026", "в ноябре 2026"),
    ("dekabr-2026", "декабрь 2026", "в декабре 2026"),
    ("yanvar-2027", "январь 2027", "в январе 2027"),
    ("fevral-2027", "февраль 2027", "в феврале 2027"),
]

PAIRS = [
    ("turciya", "egipet", "Турция или Египет", "море и всё включено против Красного моря и дайвинга"),
    ("tailand", "maldivy", "Таиланд или Мальдивы", "острова и развлечения против вилл над водой"),
    ("oae", "egipet", "ОАЭ или Египет", "шопинг и города против кораллов и бюджетного моря"),
    ("kipr", "greciya", "Кипр или Греция", "короткий перелёт против островов и памятников"),
    ("italiya", "ispaniya", "Италия или Испания", "города и кухня против солнца и пляжей"),
    ("vietnam", "tailand", "Вьетнам или Таиланд", "тише и дешевле против инфраструктуры Пхукета"),
    ("abkhaziya", "turciya", "Абхазия или Турция", "минимальная цена против сервиса и всё включено"),
]


def _price(d: dict) -> int:
    return int(d["price"].replace(" ", ""))


EXTRA_CSS = (".cmp{width:100%;border-collapse:collapse;margin:18px 0;font-size:15px}"
             ".cmp th,.cmp td{padding:11px 12px;border-bottom:1px solid rgba(148,163,255,.18);"
             "text-align:left;vertical-align:top}"
             ".cmp th{color:#9fb0d9;font-weight:700;font-size:13px;text-transform:uppercase;letter-spacing:.04em}"
             ".cmp td{color:#dfe6ff}")


def _page(title: str, desc: str, url: str, h1: str, lead: str, body: str, graph: dict,
          crumb: list[tuple[str, str]]) -> str:
    sub_block = SUBSCRIBE_TEMPLATE.replace("__SLUG__", url.rstrip("/").split("/")[-1] + "-extra")
    navs = "".join(f'<a href="{u}">{esc(n)}</a>' for n, u in crumb)
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
<meta property="og:image" content="{GH}/destinations/og/destinations.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{GH}/destinations/og/destinations.png">
<style>{CSS}{EXTRA_CSS}</style>
<script type="application/ld+json">{json.dumps(graph, ensure_ascii=False)}</script>
</head><body><div class="wrap">
<p class="crumb">{navs}</p>
<h1>{esc(h1)}</h1>
<p class="lead">{esc(lead)}</p>
{body}
{sub_block}
<nav><a href="{GH}/destinations/">Все направления</a><a href="{GH}/seasons/">Подборки</a><a href="{ABROAD}">Сводка цен</a></nav>
<footer>Данные: Travelata · сводка {UPDATED} · цены за двоих, перелёт + отель · не оферта.</footer>
</div></body></html>
"""


def _graph(url: str, name: str, items: list[dict], faq: list[tuple[str, str]]) -> dict:
    graph = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "@id": url + "#page", "url": url, "inLanguage": "ru", "name": name},
        {"@type": "BreadcrumbList", "@id": url + "#crumb", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Главная", "item": GH + "/"},
            {"@type": "ListItem", "position": 2, "name": "Подборки", "item": GH + "/seasons/"},
            {"@type": "ListItem", "position": 3, "name": name, "item": url}]},
        {"@type": "ItemList", "@id": url + "#list", "itemListElement": [
            {"@type": "ListItem", "position": i, "name": d["name"],
             "url": f"{GH}/destinations/{d['slug']}/"} for i, d in enumerate(items, 1)]}]}
    if faq:
        graph["@graph"].append({"@type": "FAQPage", "@id": url + "#faq", "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]})
    return graph


def _cards(items: list[dict]) -> str:
    return "".join(
        f'<a class="card" href="{GH}/destinations/{d["slug"]}/"><b>{d["name"]}</b>'
        f'<span>от {d["price"]} ₽ · {esc(d["nights"])}</span></a>' for d in items)


def build_month(slug: str, label: str, prep: str) -> str:
    url = f"{GH}/months/{slug}/"
    items = sorted(DESTINATIONS, key=_price)
    cheapest = items[0]
    faq = [("В какие даты действуют цены?",
            f"Цены — минимальные из сводки Travelata на {UPDATED}. Заезды в текущем сезоне: {DATES}. "
            f"На конкретные даты {prep} проверяйте наличие в сводке."),
           ("Сколько стоит самый дешёвый тур?",
            f"Минимальная цена сезона — {cheapest['price']} ₽ за двоих ({cheapest['name']}), перелёт + отель.")]
    title = f"Туры {prep}: 12 стран с ценами за двоих — сезон 2026/2027"
    desc = (f"Цены на туры {prep}: от {cheapest['price']} ₽ за двоих ({cheapest['name']}) до "
            f"{items[-1]['price']} ₽ ({items[-1]['name']}). Перелёт + отель, 12 направлений, сводка {UPDATED}.")
    lead = (f"Подборка на {label}: минимальные цены за двоих по 12 странам. "
            f"Это ориентир по сезону {DATES} — на конкретные даты {prep} наличие уточняйте в сводке.")
    body = f'<div class="grid">{_cards(items)}</div>'
    return _page(title, desc, url, f"Туры {prep}: 12 стран с ценами",
                 lead, body, _graph(url, f"Туры {prep}", items, faq),
                 [("Главная", GH + "/"), ("Подборки", GH + "/seasons/"), (f"Туры {prep}", url)])


def build_pair(a: dict, b: dict, name: str, essence: str) -> str:
    slug = f"{a['slug']}-ili-{b['slug']}"
    url = f"{GH}/compare/{slug}/"
    cheaper, dearer = sorted([a, b], key=_price)
    diff = _price(dearer) - _price(cheaper)
    faq = [(f"{a['name']} или {b['name']} — что дешевле?",
            f"В сводке от {UPDATED} дешевле {cheaper['name']}: {cheaper['price']} ₽ против "
            f"{dearer['price']} ₽ за двоих (разница {diff:,} ₽).".replace(",", " ")),
           (f"Сколько лететь и что входит?",
            "Обе цены — пакет «перелёт + отель» на двоих, заезды " + DATES +
            ". Состав пакета и отель уточняются на странице предложения."),
           ("Что выбрать, если важен бюджет?",
            f"{cheaper['name']} — минимальная цена сезона среди этих двух направлений. "
            f"{dearer['name']} дороже на {diff:,} ₽, но даёт другой формат отдыха.".replace(",", " "))]
    title = f"{name}: сравнение цен за двоих — что дешевле в 2026/2027"
    desc = (f"{a['name']} от {a['price']} ₽ или {b['name']} от {b['price']} ₽ за двоих. "
            f"Сравнение по цене, ночам и формату отдыха: {essence}.")
    lead = (f"Сравниваем два направления из сводки: {a['name']} и {b['name']}. "
            f"Цены — минимальные за двоих в пакете «перелёт + отель», заезды {DATES}.")
    rows = "".join(
        f"<tr><td>{esc(d['name'])}</td><td>{esc(d['price'])} ₽</td><td>{esc(d['nights'])}</td>"
        f"<td>{esc(d['blurb'][:120])}</td></tr>" for d in (cheaper, dearer))
    body = (f'<table class="cmp"><thead><tr><th>Направление</th><th>Цена за двоих</th>'
            f'<th>Ночей</th><th>Что внутри</th></tr></thead><tbody>{rows}</tbody></table>'
            f'<p class="lead">Разница в цене: <b>{diff:,} ₽</b> в пользу {esc(cheaper["name"])}.</p>'.replace(",", " ")
            + f'<div class="grid">{_cards([cheaper, dearer])}</div>')
    return _page(title, desc, url, name, lead, body,
                 _graph(url, name, [cheaper, dearer], faq),
                 [("Главная", GH + "/"), ("Подборки", GH + "/seasons/"), (name, url)])


def build_price_table() -> str:
    url = f"{GH}/prices/"
    items = sorted(DESTINATIONS, key=_price)
    faq = [("Откуда цены?", f"Из сводки Travelata на {UPDATED}: минимальные цены за двоих, пакет «перелёт + отель»."),
           ("Что дешевле всего?", f"Самый дешёвый тур сезона — {items[0]['name']} от {items[0]['price']} ₽ за двоих.")]
    rows = "".join(
        f'<tr><td><a href="{GH}/destinations/{d["slug"]}/">{esc(d["name"])}</a></td>'
        f'<td>{esc(d["price"])} ₽</td><td>{esc(d["nights"])}</td></tr>' for d in items)
    title = "Таблица цен на туры за двоих: 12 стран, сезон 2026/2027"
    desc = (f"Цены за двоих из сводки Travelata на {UPDATED}: {items[0]['name']} от {items[0]['price']} ₽ — "
            f"{items[-1]['name']} от {items[-1]['price']} ₽. 12 направлений, перелёт + отель.")
    body = (f'<table class="cmp"><thead><tr><th>Направление</th><th>Цена за двоих</th><th>Ночей</th></tr></thead>'
            f'<tbody>{rows}</tbody></table><div class="grid">{_cards(items[:6])}</div>')
    return _page(title, desc, url, "Цены на туры: вся таблица", 
                 "Полная сводка минимальных цен за двоих: перелёт + отель, 12 стран, заезды " + DATES + ".",
                 body, _graph(url, "Таблица цен на туры", items, faq),
                 [("Главная", GH + "/"), ("Подборки", GH + "/seasons/"), ("Цены", url)])


def build_index(kind: str, title: str, lead: str) -> str:
    url = f"{GH}/{kind}/"
    if kind == "months":
        cards = "".join(
            f'<a class="card" href="{GH}/months/{slug}/"><b>Туры {prep}</b><span>12 стран, от 18 473 ₽</span></a>'
            for slug, _label, prep in MONTHS)
    else:
        cards = "".join(
            f'<a class="card" href="{GH}/compare/{a}-ili-{b}/"><b>{name}</b><span>сравнение цен</span></a>'
            for a, b, name, _e in PAIRS)
    body = (f'<div class="grid">{cards}</div>'
            f'<p class="lead"><a class="btn" href="{GH}/prices/">Вся таблица цен →</a></p>')
    url2 = url
    graph = _graph(url2, title, list(DESTINATIONS), [])
    return _page(title, lead, url2, title, lead, body, graph,
                 [("Главная", GH + "/"), ("Подборки", GH + "/seasons/"), (title, url2)])


def main() -> int:
    created = []
    for slug, label, prep in MONTHS:
        target = DOCS / "months" / slug / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(build_month(slug, label, prep), encoding="utf-8")
        created.append(f"{GH}/months/{slug}/")
    for a_slug, b_slug, name, essence in PAIRS:
        target = DOCS / "compare" / f"{a_slug}-ili-{b_slug}" / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(build_pair(BY_SLUG[a_slug], BY_SLUG[b_slug], name, essence), encoding="utf-8")
        created.append(f"{GH}/compare/{a_slug}-ili-{b_slug}/")
    for kind, title, lead in [
            ("months", "Туры по месяцам: цены за двоих, сезон 2026/2027",
             "Цены по месяцам сезона: ноябрь 2026 — февраль 2027. 12 направлений, перелёт + отель."),
            ("compare", "Сравнение направлений: что дешевле и чем отличаются",
             "Парные сравнения популярных направлений по минимальным ценам за двоих из сводки.")]:
        target = DOCS / kind / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(build_index(kind, title, lead), encoding="utf-8")
        created.append(f"{GH}/{kind}/")

    target = DOCS / "prices" / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_price_table(), encoding="utf-8")
    created.append(GH + "/prices/")

    # sitemap
    sitemap = DOCS / "sitemap.xml"
    xml = sitemap.read_text(encoding="utf-8")
    extra = []
    for loc in created:
        if f"<loc>{loc}</loc>" not in xml:
            extra.append(f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>2026-11-15</lastmod>\n"
                         f"    <changefreq>weekly</changefreq>\n    <priority>0.7</priority>\n  </url>")
    if extra:
        sitemap.write_text(xml.replace("</urlset>", "\n".join(extra) + "\n</urlset>"), encoding="utf-8")
    print(f"создано страниц: {len(created)} | в sitemap добавлено: {len(extra)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
