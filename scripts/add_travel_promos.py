#!/usr/bin/env python3
"""Промо-блоки партнёров на travel-лендингах (скидки/акции других партнёрок).

Страницы: docs/flight-hotel/index.html и docs/flight-hotel-abroad/index.html.
Ссылки — Travelpayouts короткие (config/affiliate_links.yaml + seo_en из
travel-affiliate/config/links.generated.json), поэтому клики засчитываются.

Запуск:
    content-factory/.venv/bin/python scripts/add_travel_promos.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINKS_YAML = ROOT / "config" / "affiliate_links.yaml"
GENERATED = ROOT.parent / "travel-affiliate" / "config" / "links.generated.json"

PAGES = {
    "flight-hotel": ROOT / "docs" / "flight-hotel" / "index.html",
    "flight-hotel-abroad": ROOT / "docs" / "flight-hotel-abroad" / "index.html",
}

CSS = """
/* promo-partners */
.promo-sec{max-width:1080px;margin:28px auto 0;padding:0 22px}
.promo-sec h2{font-size:22px;margin:0 0 6px}
.promo-lead{margin:0 0 14px;font-size:13.5px;opacity:.75}
.promo-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.promo-card{display:flex;flex-direction:column;gap:4px;padding:15px 16px;border-radius:16px;
  border:1px solid rgba(124,58,237,.3);background:rgba(124,58,237,.07);text-decoration:none;
  color:inherit;transition:transform .15s,border-color .15s}
.promo-card:hover{transform:translateY(-2px);border-color:rgba(124,58,237,.6)}
.promo-ico{font-size:21px;line-height:1.1}
.promo-t{font-weight:800;font-size:15px}
.promo-d{font-size:12.5px;opacity:.75}
.promo-cta{margin-top:6px;font-size:12.5px;font-weight:700;color:#7c3aed}
.promo-note{margin:10px 0 0;font-size:11.5px;opacity:.6}
.promo-pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin:14px 0 0}
.promo-mini{border-left:3px solid rgba(124,58,237,.6);padding:4px 0 4px 12px;font-size:13px;opacity:.9}
.promo-mini b{font-weight:800}
"""

#: карточки: ключ → (эмодзи, название, описание, текст кнопки)
CARDS = {
    "aviasales": ("✈️", "Aviasales", "Акции на перелёты и сравнение цен", "Смотреть билеты →"),
    "kiwitaxi": ("🚕", "Kiwitaxi", "Трансфер из аэропорта по фиксированной цене", "Заказать трансфер →"),
    "gettransfer": ("🚐", "GetTransfer", "Индивидуальный трансфер, встреча с табличкой", "Выбрать трансфер →"),
    "saily": ("📶", "Saily", "eSIM: интернет за границей без роуминга", "Подключить eSIM →"),
    "airalo": ("📱", "Airalo", "eSIM для 200+ стран, пакеты со скидкой", "Выбрать тариф →"),
    "tiqets": ("🎟", "Tiqets", "Билеты в музеи и парки без очереди", "Смотреть билеты →"),
    "klook": ("🎡", "Klook", "Экскурсии, туры и билеты со скидками", "Смотреть акции →"),
    "wegotrip": ("🎧", "WeGoTrip", "Аудиогиды и экскурсии по городам", "Выбрать экскурсию →"),
    "localrent": ("🚗", "Localrent", "Аренда авто у местных прокатчиков", "Найти авто →"),
    "kiwi": ("🚆", "Kiwi.com", "Поезда и автобусы между городами", "Смотреть маршруты →"),
    "radicalstorage": ("🧳", "RadicalStorage", "Хранение багажа в центре города", "Найти камеру →"),
    "economybookings": ("🚙", "Economybookings", "Аренда авто с бесплатной отменой", "Сравнить цены →"),
}

NOTE = ("Партнёрские ссылки: мы можем получить комиссию — цена для вас не меняется. "
        "Акции, скидки и условия — на сайте партнёра.")


def load_links() -> dict[str, str]:
    links: dict[str, str] = {}
    if GENERATED.exists():
        data = json.loads(GENERATED.read_text(encoding="utf-8"))
        for name, item in (data.get("channels", {}).get("seo_en", {}).get("programs") or {}).items():
            if item.get("url"):
                links[name] = item["url"]
    if LINKS_YAML.exists():
        try:
            import yaml
            cfg = yaml.safe_load(LINKS_YAML.read_text(encoding="utf-8")) or {}
            for name, item in (cfg.get("programs") or {}).items():
                url = (item or {}).get("partner_url")
                if url:
                    links.setdefault(name, str(url))
        except Exception as error:  # noqa: BLE001
            print("affiliate_links.yaml:", error)
    return links


def card(key: str, links: dict[str, str]) -> str:
    if key not in links:
        raise SystemExit(f"нет партнёрской ссылки для {key}")
    ico, title, desc, cta = CARDS[key]
    return (f'<a class="promo-card" href="{links[key]}" target="_blank" rel="noopener sponsored">'
            f'<span class="promo-ico">{ico}</span><span class="promo-t">{title}</span>'
            f'<span class="promo-d">{desc}</span><span class="promo-cta">{cta}</span></a>')


def section(anchor: str, title: str, lead: str, keys: list[str], links: dict[str, str],
            extra: str = "") -> str:
    cards = "".join(card(k, links) for k in keys)
    return (f'\n<section class="promo-sec" data-promo="{anchor}"><!-- promo-partners -->\n'
            f'<h2>{title}</h2>\n<p class="promo-lead">{lead}</p>\n'
            f'<div class="promo-grid">{cards}</div>{extra}\n'
            f'<p class="promo-note">{NOTE}</p>\n</section>\n')


def mini(links: dict[str, str], emoji: str, title: str, text: str, pairs: list[tuple[str, str]]) -> str:
    refs = " · ".join(
        f'<a href="{links[k]}" target="_blank" rel="noopener sponsored">{label}</a>' for k, label in pairs)
    return f'<div class="promo-mini">{emoji} <b>{title}</b> — {text} {refs}</div>'


def inject_flight_hotel(html: str, links: dict[str, str]) -> str:
    html = html.replace("</style>", CSS + "</style>", 1)
    # 1) промо к самому дешёвому пакету (сразу после CTA в герое)
    cheap = section(
        "cheap", "🎁 Промо к самому дешёвому пакету",
        "Пакет уже включает перелёт и отель, а акции партнёров помогают добрать поездку дешевле: "
        "билеты, трансфер, eSIM и билеты в музеи.",
        ["aviasales", "kiwitaxi", "saily", "tiqets"], links)
    cta = re.search(r'<div class="cta">.*?</div>', html, re.S)
    if cta:
        html = html[:cta.end()] + cheap + html[cta.end():]

    # 2) блок выводов: экономия на самом дорогом направлении
    expensive = section(
        "expensive", "💰 Как сэкономить на самом дорогом направлении",
        "Италия дороже всех в сводке — вот где ещё можно срезать цену: музеи без очереди, "
        "экскурсии, авто и поезда.",
        ["tiqets", "wegotrip", "localrent", "kiwi"], links,
        extra='<div class="promo-pair">' + mini(
            links, "🥇", "Дешевле всего — Россия",
            "трансфер, eSIM и экскурсии по акциям:",
            [("kiwitaxi", "Kiwitaxi"), ("saily", "Saily"), ("tiqets", "Tiqets")]) + mini(
            links, "💎", "Дороже всего — Италия",
            "музеи, авто и поезда дешевле:",
            [("tiqets", "Tiqets"), ("localrent", "Localrent"), ("kiwi", "Kiwi")]) + "</div>")
    idx = html.find('<section class="section" id="insights">')
    if idx != -1:
        end = html.find("</section>", idx) + len("</section>")
        html = html[:end] + expensive + html[end:]

    return html


def inject_abroad(html: str, links: dict[str, str]) -> str:
    html = html.replace("</style>", CSS + "</style>", 1)
    # промо-блок перед футером
    abroad = section(
        "partners", "🎁 Промо и акции партнёров",
        "Перелёт, трансферы, экскурсии, авто и eSIM со скидками — добираем поездку дешевле.",
        ["aviasales", "kiwitaxi", "tiqets", "klook", "localrent", "airalo"], links,
        extra='<div class="promo-pair">' + mini(
            links, "🥇", "Дешевле всего — Абхазия (от 18 473 ₽)",
            "трансфер и экскурсии по акциям:",
            [("kiwitaxi", "Kiwitaxi"), ("tiqets", "Tiqets")]) + mini(
            links, "💎", "Дороже всего — Италия (от 240 442 ₽)",
            "музеи, авто и поезда дешевле:",
            [("tiqets", "Tiqets"), ("localrent", "Localrent"), ("kiwi", "Kiwi")]) + "</div>")
    html = html.replace("<footer>", abroad + "<footer>", 1)
    return html


def main() -> int:
    links = load_links()
    handlers = {"flight-hotel": inject_flight_hotel, "flight-hotel-abroad": inject_abroad}
    for name, path in PAGES.items():
        if not path.exists():
            print(f"{name}: нет файла {path}")
            continue
        before = path.read_text(encoding="utf-8")
        if "<!-- promo-partners -->" in before:
            print(f"{name}: промо уже есть — пропуск")
            continue
        after = handlers[name](before, links)
        if after == before:
            print(f"{name}: промо уже есть — пропуск")
            continue
        path.write_text(after, encoding="utf-8")
        n = after.count("promo-card")
        print(f"{name}: добавлено карточек {n - before.count('promo-card')}, файл {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
