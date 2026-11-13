#!/usr/bin/env python3
"""Добавляет кликабельные ссылки на Travelata в опубликованную страницу /flight-hotel/.

Страница статическая (сборка travelata-api/scripts/build_summary.py), поэтому ссылки
вставляются пост-обработкой HTML: страна/город/отель/цена становятся ссылками на поиск
Travelata с теми же фильтрами, что и снимок (17.11–17.12.2026, 5–9 ночей, 2 взрослых).

Использование:
    python scripts/add_flight_hotel_links.py [--page docs/flight-hotel/index.html] \
        [--data ../travelata-api/data/csv]
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT.parent / "travelata-api" / "data" / "csv"

BASE = "https://travelata.ru/search"
WINDOW = {
    "dateFrom": "17.11.2026",
    "dateTo": "17.12.2026",
    "nightFrom": "5",
    "nightTo": "9",
    "adults": "2",
    "hotelClass": "all",
    "meal": "all",
}
DEFAULT_CITY = "2"  # Москва

CSS = """
.table-wrap a { color: inherit; text-decoration: underline; text-decoration-color: rgba(124,58,237,.4); text-underline-offset: 2px; }
.table-wrap a:hover { color: #7c3aed; text-decoration-color: #7c3aed; }
.table-wrap tbody tr[data-href] { cursor: pointer; }
.table-wrap tbody tr[data-href]:hover td { background: rgba(124,58,237,.06); }
.cta { margin: 20px 0 4px; }
.cta a { display: inline-block; padding: 11px 20px; border-radius: 999px; color: #fff; font-weight: 700;
         text-decoration: none; background: linear-gradient(90deg,#6366f1,#ec4899);
         box-shadow: 0 8px 22px rgba(124,58,237,.28); }
.cta a:hover { filter: brightness(1.06); }
.toc a.ext { background: linear-gradient(90deg,#6366f1,#ec4899); color: #fff; border-color: transparent; }
.tap-hint { margin: 10px 0 0; font-size: 13px; color: #6b7280; }
"""

ROW_JS = """
<script>
document.querySelectorAll('tr[data-href]').forEach(function (tr) {
  tr.addEventListener('click', function (ev) {
    if (ev.target.closest('a')) return;
    window.open(tr.getAttribute('data-href'), '_blank', 'noopener');
  });
});
</script>
"""


def search_url(from_city: str | None = None, to_country: str | None = None) -> str:
    params: list[tuple[str, str]] = []
    if from_city:
        params.append(("fromCity", from_city))
    if to_country:
        params.append(("toCountry", to_country))
    params.extend(WINDOW.items())
    query = urllib.parse.urlencode(params).replace("&", "&amp;")
    return f"{BASE}#?{query}"


def link(markup: str, href: str) -> str:
    return f'<a href="{href}" target="_blank" rel="noopener sponsored">{markup}</a>'


def load_map(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as fh:
        return {row["name"].strip(): row["id"] for row in csv.DictReader(fh)}


def cell_text(markup: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", markup)).strip()


def wrap_cell(row: str, index: int, href: str) -> str:
    """Оборачивает внутренности <td> с номером index в ссылку (по одному разу)."""
    pattern = re.compile(r"<td([^>]*)>(.*?)</td>", re.S)
    matches = list(pattern.finditer(row))
    if index >= len(matches):
        return row
    m = matches[index]
    if f'href="{href}"' in m.group(2):
        return row
    new_cell = f"<td{m.group(1)}>{link(m.group(2), href)}</td>"
    return row[: m.start()] + new_cell + row[m.end():]


def process_table(block: str, cities: dict[str, str], countries: dict[str, str],
                  cells: dict[int, str], mode: str) -> tuple[str, dict[str, int]]:
    """mode: 'country' — ссылка по стране из ячейки-ключа; 'offer' — по городу и стране; 'city'.

    Кликабельной делается вся строка целиком (все ячейки + JS-обработчик на tr),
    чтобы на мобильном попадание пальцем в любое место строки открывало Travelata.
    """
    stats = {"linked": 0, "skipped": 0}

    def on_row(m: re.Match[str]) -> str:
        row = m.group(0)
        if "<td" not in row:
            return row
        values = [cell_text(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if mode == "country":
            href = search_url(DEFAULT_CITY, countries.get(values[0]))
            if not countries.get(values[0]):
                stats["skipped"] += 1
                return row
        elif mode == "city":
            city_id = cities.get(values[0])
            if not city_id:
                stats["skipped"] += 1
                return row
            href = search_url(city_id)
        else:  # offer
            city_id = cities.get(values[9].replace("✈", "").strip()) or DEFAULT_CITY
            country_id = countries.get(values[3])
            if not country_id:
                stats["skipped"] += 1
                return row
            href = search_url(city_id, country_id)
        for idx in range(len(values)):
            row = wrap_cell(row, idx, href)
        row = re.sub(r"<tr([^>]*)>", lambda mm: f'<tr{mm.group(1)} data-href="{href}">', row, count=1)
        stats["linked"] += 1
        return row

    return re.sub(r"<tr>.*?</tr>", on_row, block, flags=re.S), stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", default=str(ROOT / "docs" / "flight-hotel" / "index.html"))
    parser.add_argument("--data", default=str(DEFAULT_DATA))
    args = parser.parse_args(argv)

    page_path = Path(args.page)
    data_dir = Path(args.data)
    cities = load_map(data_dir / "departureCities.csv")
    countries = load_map(data_dir / "countries.csv")

    html = page_path.read_text(encoding="utf-8")
    if "travelata.ru/search#?" in html:
        print("ссылки уже есть — выхожу", file=sys.stderr)
        return 0

    tables = list(re.finditer(r"<table>.*?</table>", html, re.S))
    if len(tables) != 4:
        print(f"ожидал 4 таблицы, нашёл {len(tables)}", file=sys.stderr)
        return 1

    specs = [
        (0, {0, 6}, "country"),   # направления: страна + самый дешёвый отель
        (1, {0}, "city"),         # города вылета
        (2, {1, 4}, "offer"),     # топ-20: цена + отель
        (3, {0}, "country"),      # отельная база: страна
    ]
    out = html
    total = {"linked": 0, "skipped": 0}
    for idx, cells, mode in reversed(specs):
        m = tables[idx]
        block, stats = process_table(m.group(0), cities, countries, cells, mode)
        out = out[: m.start()] + block + out[m.end():]
        total["linked"] += stats["linked"]
        total["skipped"] += stats["skipped"]

    # CTA после hero-блока + стили
    cta = ('<div class="cta"><a href="' + search_url(DEFAULT_CITY) +
           '" target="_blank" rel="noopener sponsored">Смотреть туры на Travelata →</a></div>')
    hero_end = out.find("</div>\n<div class=\"kpis\">")
    if hero_end != -1:
        out = out[: hero_end + len("</div>")] + "\n" + cta + out[hero_end + len("</div>"):]

    # внешняя ссылка в навигации + подсказка, что строки кликабельны
    nav_start = out.find('<nav class="toc"')
    nav_end = out.find("</nav>", nav_start)
    if nav_start != -1 and nav_end != -1:
        ext = ('  <a class="ext" href="' + search_url(DEFAULT_CITY) +
               '" target="_blank" rel="noopener sponsored">🔎 Туры на Travelata ↗</a>\n')
        out = out[:nav_end] + ext + out[nav_end:]
        out = out.replace(
            "</nav>",
            '</nav>\n<p class="tap-hint">Нажми на любую строку таблицы или цену — откроются живые туры на Travelata.</p>',
            1,
        )

    out = out.replace("</style>", CSS + "</style>", 1)
    out = out.replace("</body>", ROW_JS + "</body>", 1)

    page_path.write_text(out, encoding="utf-8")
    print(f"строк со ссылками: {total['linked']}, пропущено: {total['skipped']}")
    print(f"файл: {page_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
