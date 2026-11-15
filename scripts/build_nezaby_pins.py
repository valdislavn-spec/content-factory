#!/usr/bin/env python3
"""Пины Pinterest для лендинга «Незабываемое путешествие» (nezabyvaemoe.surge.sh).

Берёт живые цифры из свежего отчёта travelata-api и рендерит 5 пинов 1000x1500
через брендовый движок content_factory.brand.design (фото-фон + скрим + QR).

Запуск (из content-factory, нужен DSH-python с рабочим Pillow):

    PYTHONPATH=$PWD/.render-libs \
      ~/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3 \
      scripts/build_nezaby_pins.py

Пишет:
    docs/nezabyvaemoe-puteshestvie/pins/pin-XX-*.png   (+ meta.json)
    docs/nezabyvaemoe-puteshestvie/pins/pinterest-import.csv
    docs/nezabyvaemoe-puteshestvie/pins/telegram-posts.md
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.brand.design import (  # noqa: E402
    PIN_SIZE,
    PinContent,
    board_for_niche,
    build_pinterest_payload,
    format_attribution,
    keywords_for,
    render_pin,
)

REPORTS = ROOT.parent / "travelata-api" / "reports"
SITE = "https://nezabyvaemoe.surge.sh"
OUT = ROOT / "docs" / "nezabyvaemoe-puteshestvie" / "pins"
PHOTOS = ROOT / "docs" / "assets" / "photos"
DISCLOSURE = "Реклама · партнёрская ссылка"
BOARD = "Пакетные туры | Travelata"
SITE_LABEL = "nezabyvaemoe.surge.sh"


def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def source_link(source: str, medium: str) -> str:
    return f"{SITE}/?utm_source={source}&utm_medium={medium}&utm_campaign=nezabyvaemoe"


def latest_report() -> Path:
    dirs = sorted(REPORTS.glob("flight-hotel-*"))
    if not dirs:
        raise SystemExit("нет отчётов travelata-api/reports/flight-hotel-*")
    return dirs[-1]


def load_stats(report: Path) -> dict:
    return json.loads((report / "summary.json").read_text(encoding="utf-8"))["stats"]


def rub(value: int) -> str:
    return f"{value:,}".replace(",", " ") + " ₽"


def pins_for(stats: dict) -> list[dict]:
    off = stats["offers"]
    by_country = {row["name"]: row["minPrice"] for row in off["byCountry"]}
    window_from, window_to = stats["checkinFrom"], stats["checkinTo"]
    window = f"{window_from[8:10]}.{window_from[5:7]}–{window_to[8:10]}.{window_to[5:7]}.{window_to[:4]}"
    total = off["total"]
    min_price = off["minPrice"]
    ru = by_country.get("Россия", min_price)
    tr = by_country.get("Турция")
    ae = by_country.get("ОАЭ")
    ab = by_country.get("Абхазия")

    def money(value: int | None) -> str:
        return rub(value) if value else "—"

    return [
        {
            "slug": "pin-01-price",
            "photo": "flight",
            "tag": f"ОТ {rub(min_price)} НА ДВОИХ",
            "headline": "ПЕРЕЛЁТ\nИ ОТЕЛЬ",
            "promise": f"от {rub(min_price)} на двоих · {total} {plural(total, 'пакет', 'пакета', 'пакетов')}",
            "cta": "Смотреть цены",
            "accent": "#f97316",
            "title": f"Пакетные туры: перелёт + отель от {rub(min_price)} на двоих",
            "description": (
                f"Живые цены пакетных туров Travelata: {total} предложений по {len(off['byCountry'])} "
                f"направлениям, заезды {window}, 5–9 ночей. Россия от {rub(ru)}, Абхазия от {money(ab)}, "
                f"Турция от {money(tr)}, ОАЭ от {money(ae)}. У каждого отеля — карточка на Travelata."
            ),
            "keywords": "пакетные туры, перелёт и отель, дешёвые туры, туры на двоих, отдых зимой, travelata",
        },
        {
            "slug": "pin-02-directions",
            "photo": "europe",
            "tag": "13 НАПРАВЛЕНИЙ",
            "headline": "КУДА УЛЕТЕТЬ\nЗИМОЙ",
            "promise": f"Россия {rub(ru)} · Абхазия {money(ab)} · Турция {money(tr)}",
            "cta": "Открыть сводку",
            "accent": "#4f46e5",
            "title": "Куда лететь зимой: 13 направлений с ценами пакетных туров",
            "description": (
                f"Минимальные цены пакетов на двоих: Россия от {rub(ru)}, Абхазия от {money(ab)}, "
                f"Турция от {money(tr)}, ОАЭ от {money(ae)}. Заезды {window}, перелёт и отель в одной цене."
            ),
            "keywords": "куда лететь зимой, направления, туры, Турция, ОАЭ, Абхазия, цены на туры",
        },
        {
            "slug": "pin-03-top20",
            "photo": "dubai",
            "tag": "ТОП-20",
            "headline": "САМЫЕ ДЕШЁВЫЕ\nПАКЕТЫ",
            "promise": f"Топ-20 предложений от {rub(min_price)}",
            "cta": "Смотреть тур",
            "accent": "#db2777",
            "title": "Топ-20 самых дешёвых пакетных туров: перелёт + отель",
            "description": (
                f"Рейтинг 20 самых дешёвых пакетов из {total} предложений: перелёт, отель и итоговая цена "
                f"на 2 взрослых. Заезды {window}, 5–9 ночей, вылет из 6 городов."
            ),
            "keywords": "дешёвые туры, топ пакетов, горящие туры, туры 2026, отель и перелёт",
        },
        {
            "slug": "pin-04-hotel",
            "photo": "bali",
            "tag": "ОТЕЛЬ В ЦЕНЕ",
            "headline": "ОТЕЛЬ +\nПЕРЕЛЁТ",
            "promise": "5–9 ночей · вылет из 6 городов · на двоих",
            "cta": "Подобрать тур",
            "accent": "#06b6d4",
            "title": "Отель и перелёт в одной цене: пакетные туры на ноябрь–декабрь",
            "description": (
                f"Пакет Travelata — это отель и авиабилет в одной цене. {total} живых предложений, "
                f"5–9 ночей, заезды {window}, 2 взрослых. У каждого отеля кликабельная карточка."
            ),
            "keywords": "отель и перелёт, пакетный тур, тур на двоих, ноябрь, декабрь, travelata",
        },
        {
            "slug": "pin-05-window",
            "photo": "lisbon",
            "tag": "ЗАЕЗДЫ " + window.split("–")[0],
            "headline": "ЗИМА БЕЗ\nПЕРЕПЛАТ",
            "promise": f"Окно заездов {window}, цены каждую минуту",
            "cta": "Проверить цены",
            "accent": "#10b981",
            "title": f"Пакетные туры на {window}: живые цены Travelata",
            "description": (
                f"Сводка цен на пакетные туры с заездами {window}: {total} предложений, "
                f"перелёт + отель, 5–9 ночей, Россия от {rub(ru)}. Данные обновляются из API Travelata."
            ),
            "keywords": "туры ноябрь декабрь, цены на туры, пакетные туры, travelata, зимний отдых",
        },
    ]


def telegram_posts(stats: dict, link: str, pins: list[dict]) -> str:
    off = stats["offers"]
    by_country = sorted(off["byCountry"], key=lambda row: row["minPrice"])
    lines = [f"• {row['name']} — от {rub(row['minPrice'])}" for row in by_country[:5]]
    window = f"{stats['checkinFrom'][8:10]}.{stats['checkinFrom'][5:7]}–{stats['checkinTo'][8:10]}.{stats['checkinTo'][5:7]}.{stats['checkinTo'][:4]}"
    return f"""# Telegram-посты для лендинга «Незабываемое путешествие»

Ссылки уже с UTM: `utm_source=telegram`, `utm_medium=channel`. Не забудьте пометку
«Реклама» / «Партнёрская ссылка», если этого требует площадка.

## Пост 1 — короткий анонс (для профильных каналов)

🌍 **Перелёт + отель дешевле, чем по отдельности**

{off['total']} живых пакетов по {len(off['byCountry'])} направлениям, заезды {window}, 5–9 ночей на двоих:

{chr(10).join(lines)}

У каждого отеля — карточка на Travelata: даты, питание, цена «всё включено» в пакете.

👉 {link}

## Пост 2 — «самый дешёвый пакет недели»

🔥 **Самый дешёвый пакет: {rub(off['minPrice'])} на двоих**

Например: Россия, 9 ночей, перелёт и отель в одной цене. Плюс ещё {off['total'] - 1} вариантов — Турция, ОАЭ, Египет, Абхазия, Кипр.

Сводка с проверкой по каждой строке:
👉 {link}

## Пост 3 — под Pinterest-пины (англ. аудитория, если нужно)

🇷🇺 **Russia package tours from {rub(off['minPrice'])} for two**

Flights + hotel in one price, {off['total']} live offers, {len(off['byCountry'])} destinations, 5–9 nights.
Full price board (updates from Travelata API):
👉 {link}
"""


def main() -> int:
    report = latest_report()
    stats = load_stats(report)
    OUT.mkdir(parents=True, exist_ok=True)
    credits = {}
    credits_path = PHOTOS / "credits.json"
    if credits_path.exists():
        credits = json.loads(credits_path.read_text(encoding="utf-8"))
    link = source_link("pinterest", "organic")
    pins = pins_for(stats)
    rows = []
    meta = []
    for pin in pins:
        photo_path = PHOTOS / f"{pin['photo']}.jpg"
        if not photo_path.exists():
            print(f"photo missing: {photo_path}", file=sys.stderr)
            return 2
        content = PinContent(
            niche="travel",
            headline=pin["headline"],
            subtitle=pin["promise"],
            cta=pin["cta"],
            link=link,
            tag=pin["tag"],
            disclosure=DISCLOSURE,
            attribution=format_attribution(credits.get(pin["photo"]) or {}),
            title=pin["title"],
            description=pin["description"],
            accent=pin["accent"],
            site=SITE_LABEL,
        )
        rendered = render_pin(
            content,
            size=PIN_SIZE,
            variants=("photo",),
            photo_path=photo_path,
            qr_data=link,
            font_dir=ROOT / "assets" / "fonts",
        )["photo"]
        image_path = OUT / f"{pin['slug']}.png"
        rendered.save(image_path)
        image_url = f"{SITE}/pins/{image_path.name}"
        payload = build_pinterest_payload(
            content,
            image_url=image_url,
            board_id="<BOARD_ID>",
            disclosure=DISCLOSURE,
            include_link=True,
        )
        payload.update(
            {
                "board": BOARD,
                "title": pin["title"],
                "description": pin["description"],
                "link": link,
                "alt_text": pin["title"],
                "keywords": pin["keywords"],
            }
        )
        meta.append({"slug": pin["slug"], "file": str(image_path.relative_to(ROOT)), "image_url": image_url, "payload": payload})
        rows.append(
            {
                "Title": pin["title"],
                "Media URL": image_url,
                "Pinterest board": BOARD,
                "Thumbnail": "",
                "Description": pin["description"],
                "Link": link,
                "Publish date": "",
                "Keywords": pin["keywords"],
            }
        )
        print(f"pin: {image_path.name} ({image_path.stat().st_size // 1024} KB)")

    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (OUT / "pinterest-import.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["Title", "Media URL", "Pinterest board", "Thumbnail", "Description", "Link", "Publish date", "Keywords"])
        writer.writeheader()
        writer.writerows(rows)
    (OUT / "telegram-posts.md").write_text(
        telegram_posts(stats, source_link("telegram", "channel"), pins), encoding="utf-8"
    )
    print(f"OK: {len(pins)} pins -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
