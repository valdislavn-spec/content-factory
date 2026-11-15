#!/usr/bin/env python3
"""Брендированные HTML-письма (RU/EN) для travel-дайджеста.

Собирает письмо из данных сводки: hero + таблица цен по странам + промо партнёров + CTA
с трекинг-ссылками + подвал с отпиской. Используется scripts/send_digest.py.

    .venv/bin/python scripts/brand_email.py --lang ru --out /tmp/digest-ru.html
"""
from __future__ import annotations

import argparse
import hashlib
import html as html_mod
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACKER = os.environ.get("LINK_TRACKER_BASE", "https://links-tracker.valdislav-n.workers.dev")

DATASET = [
    ("Абхазия", "18 473", "5 ночей", "самое дешёвое"),
    ("Турция", "41 754", "5–9 ночей", "всё включено"),
    ("ОАЭ", "66 704", "5–9 ночей", "пляжи и шопинг"),
    ("Кипр", "69 302", "5 ночей", "короткий перелёт"),
    ("Египет", "74 015", "5–9 ночей", "тепло и дайвинг"),
    ("Греция", "89 757", "5 ночей", "острова"),
    ("Таиланд", "98 739", "5–9 ночей", "Пхукет и Паттайя"),
    ("Мальдивы", "155 760", "5–9 ночей", "виллы над водой"),
]
DATASET_EN = [
    ("Abkhazia", "18 473", "5 nights", "cheapest"),
    ("Turkey", "41 754", "5–9 nights", "all inclusive"),
    ("UAE", "66 704", "5–9 nights", "beach & shopping"),
    ("Cyprus", "69 302", "5 nights", "short flight"),
    ("Egypt", "74 015", "5–9 nights", "warm sea"),
    ("Greece", "89 757", "5 nights", "islands"),
    ("Thailand", "98 739", "5–9 nights", "Phuket, Pattaya"),
    ("Maldives", "155 760", "5–9 nights", "overwater villas"),
]

PARTNERS = [
    ("Музеи и экскурсии — Tiqets, −5%", "https://tiqets.tpk.ro/ufgJDVmO"),
    ("Трансфер из аэропорта — Kiwitaxi", "https://kiwitaxi.tpk.ro/xmQYmqIl"),
    ("eSIM для интернета — Saily", "https://saily.tpk.ro/QSNyiXp7"),
    ("Аренда авто — Localrent", "https://localrent.tpk.ro/edD3Ejwe"),
]
PARTNERS_EN = [
    ("Museums & experiences — Tiqets, 5% off", "https://tiqets.tpk.ro/ufgJDVmO"),
    ("Airport transfers — Kiwitaxi", "https://kiwitaxi.tpk.ro/xmQYmqIl"),
    ("Travel eSIM — Saily", "https://saily.tpk.ro/QSNyiXp7"),
    ("Car rental — Localrent", "https://localrent.tpk.ro/edD3Ejwe"),
]


def esc(text: str) -> str:
    return html_mod.escape(str(text))


def unsubscribe_url(email: str) -> str:
    secret = ""
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("LINK_TRACKER_ADMIN_TOKEN="):
            secret = line.split("=", 1)[1].strip()
    token = hashlib.sha256(f"{email.lower()}|{secret}".encode()).hexdigest()[:32]
    return f"{TRACKER}/unsubscribe?e={email}&t={token}"


def build(lang: str = "ru", email: str = "user@example.com") -> str:
    ru = lang == "ru"
    rows = DATASET if ru else DATASET_EN
    partners = PARTNERS if ru else PARTNERS_EN
    hub = TRACKER + "/r/tr-mail-hub"
    abroad = TRACKER + "/r/tr-mail-abroad"
    us = TRACKER + "/r/tr-mail-us"
    unsub = unsubscribe_url(email)

    subject = ("Куда поехать в декабре: 12 стран, от 18 473 ₽ за двоих"
               if ru else "Where to go in December: 12 countries from 18 473 ₽ per couple")
    rows_html = "".join(
        f'<tr>'
        f'<td style="padding:14px 0;border-bottom:1px solid #223052;font-size:16px;color:#eef3f8;font-weight:600">{esc(name)}</td>'
        f'<td style="padding:14px 0;border-bottom:1px solid #223052;font-size:13px;color:#94a3c6">{esc(note)}</td>'
        f'<td style="padding:14px 0;border-bottom:1px solid #223052;font-size:13px;color:#94a3c6;white-space:nowrap">{esc(nights)}</td>'
        f'<td style="padding:14px 0 14px 12px;border-bottom:1px solid #223052;font-size:18px;color:#fde68a;font-weight:800;text-align:right;white-space:nowrap">от {esc(price)} ₽</td>'
        f'</tr>'
        for name, price, nights, note in rows)

    partners_html = "".join(
        f'<tr><td style="padding:10px 0;border-bottom:1px dashed #223052">'
        f'<a href="{url}" style="color:#8fb8ff;text-decoration:none;font-size:15px">{esc(title)}</a></td></tr>'
        for title, url in partners)

    title = "Куда поехать в декабре" if ru else "Where to go in December"
    lead = ("12 зарубежных направлений с минимальными ценами за двоих: перелёт + отель, "
            "заезды 17.11–17.12.2026. Свежая сводка — раз в неделю." if ru else
            "12 destinations with the lowest price per couple: flight + hotel, "
            "17 Nov – 17 Dec 2026. Fresh digest once a week.")
    cta = "Смотреть все направления" if ru else "See all destinations"
    promo_title = "Промо партнёров" if ru else "Partner offers"
    footer_note = ("Вы получили это письмо, потому что подписались на сводку Travelata. "
                   "Отписаться можно одной кнопкой ниже." if ru else
                   "You're receiving this because you subscribed to the Travelata digest. "
                   "Unsubscribe with one click below.")
    unsub_text = "Отписаться" if ru else "Unsubscribe"
    brand = "Незабываемое путешествие · Travelata" if ru else "Travelata · travel deals"
    hero_price = "от 18 473 ₽" if ru else "from 18 473 ₽"

    return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(subject)}</title></head>
<body style="margin:0;padding:0;background:#070b18;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{esc(subject)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#070b18;padding:26px 12px">
<tr><td align="center">
<table role="presentation" width="620" cellpadding="0" cellspacing="0" border="0"
 style="width:620px;max-width:620px;background:#0b1226;border-radius:18px;overflow:hidden;border:1px solid #223052">
  <tr><td style="padding:26px 30px 8px 30px;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif">
    <div style="font-size:14px;color:#8fb8ff;font-weight:800;letter-spacing:.02em">{esc(brand)}</div>
    <div style="font-size:30px;line-height:1.15;color:#ffffff;font-weight:900;margin-top:14px">{esc(title)}</div>
    <div style="font-size:38px;color:#fde68a;font-weight:900;margin-top:10px">{esc(hero_price)} <span style="font-size:15px;color:#c7d2fe;font-weight:600">/ {('за двоих' if ru else 'per couple')}</span></div>
    <p style="font-size:15px;line-height:1.55;color:#b9c3e6;margin:14px 0 0">{esc(lead)}</p>
  </td></tr>
  <tr><td style="padding:8px 30px 0 30px;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{rows_html}</table>
  </td></tr>
  <tr><td style="padding:24px 30px 0 30px" align="center">
    <a href="{hub}" style="display:inline-block;background:#7c3aed;background-image:linear-gradient(92deg,#7c3aed,#db2777);
      color:#ffffff;text-decoration:none;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;
      font-size:17px;font-weight:800;padding:16px 30px;border-radius:14px">{esc(cta)} →</a>
  </td></tr>
  <tr><td style="padding:26px 30px 0 30px;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif">
    <div style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#a5b4fc;font-weight:800">{esc(promo_title)}</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:8px">{partners_html}</table>
  </td></tr>
  <tr><td style="padding:24px 30px 0 30px;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif">
    <a href="{abroad}" style="color:#8fb8ff;text-decoration:none;font-size:15px">{'Полная сводка зарубежных туров' if ru else 'Full tours abroad digest'} →</a><br>
    <a href="{us}" style="color:#8fb8ff;text-decoration:none;font-size:15px">{'US travel deals (EN)' if ru else 'US travel deals'} →</a>
  </td></tr>
  <tr><td style="padding:26px 30px 30px 30px;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;border-top:1px solid #223052">
    <p style="font-size:12.5px;line-height:1.6;color:#7b88ab;margin:18px 0 0">{esc(footer_note)}</p>
    <p style="font-size:12.5px;margin:10px 0 0"><a href="{unsub}" style="color:#a5b4fc">{esc(unsub_text)}</a>
      &nbsp;·&nbsp; <a href="https://valdislavn-spec.github.io/content-factory/privacy-digest.html" style="color:#a5b4fc">Privacy</a></p>
    <p style="font-size:11.5px;color:#5d6a8c;margin:12px 0 0">Данные: Travelata, сводка 13.11.2026 · цены за двоих · партнёрские ссылки</p>
  </td></tr>
</table>
</td></tr></table>
</body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", choices=["ru", "en"], default="ru")
    parser.add_argument("--email", default="user@example.com")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    html = build(args.lang, args.email)
    if args.out:
        Path(args.out).write_text(html, encoding="utf-8")
        print(f"written {args.out} ({len(html)//1024} KB)")
    else:
        print(html[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
