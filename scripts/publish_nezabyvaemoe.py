#!/usr/bin/env python3
"""Публикация «Незабываемое путешествие» из свежей сборки travelata-api.

Конвейер:
  1. берёт ``index.html`` из отчёта ``travelata-api/reports/flight-hotel-<date>/``
     (сборка: ``travelata-api/scripts/build_summary.py --fresh``);
  2. добавляет кликабельные ссылки Travelata (``scripts/add_landing_links.py``);
  3. вставляет промо-блоки партнёров (``scripts/add_travel_promos.py``);
  4. переименовывает страницу в «Незабываемое путешествие» и правит canonical/OG;
  5. пишет результат в ``docs/nezabyvaemoe-puteshestvie/index.html``.

Запуск (из content-factory)::

    content-factory/.venv/bin/python scripts/publish_nezabyvaemoe.py            # последний отчёт
    content-factory/.venv/bin/python scripts/publish_nezabyvaemoe.py --report ../travelata-api/reports/flight-hotel-2026-11-15

Публикация на surge — пушем в main: workflow ``deploy-surge`` публикует папку страницы.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT.parent / "travelata-api" / "reports"
DEFAULT_OUT = ROOT / "docs" / "nezabyvaemoe-puteshestvie" / "index.html"
SITE_URL = "https://nezabyvaemoe.surge.sh/"
OG_IMAGE = SITE_URL + "preview-social.png"

TITLE = "Незабываемое путешествие — Travelata"
OG_TITLE = "Незабываемое путешествие: пакетные туры Travelata"
TW_TITLE = "Незабываемое путешествие: пакетные туры Travelata"
H1 = '<h1><span class="grad-text">Незабываемое путешествие</span></h1>'


def latest_report() -> Path:
    dirs = sorted(REPORTS.glob("flight-hotel-*"))
    if not dirs:
        raise SystemExit("нет отчётов travelata-api/reports/flight-hotel-*")
    return dirs[-1] / "index.html"


def branding(html: str) -> str:
    html = re.sub(r"<title>.*?</title>", f"<title>{TITLE}</title>", html, count=1)
    html = re.sub(r'(<meta property="og:title" content=")[^"]*(")', lambda m: m.group(1) + OG_TITLE + m.group(2), html, count=1)
    html = re.sub(r'(<meta name="twitter:title" content=")[^"]*(")', lambda m: m.group(1) + TW_TITLE + m.group(2), html, count=1)
    html = re.sub(r'<h1>.*?</h1>', H1, html, count=1, flags=re.S)
    # canonical + OG/twitter на surge-домен
    html = re.sub(r'<link rel="canonical" href="[^"]*">\s*', "", html)
    if '<link rel="canonical"' not in html:
        html = html.replace('<meta name="theme-color"', f'<link rel="canonical" href="{SITE_URL}">\n<meta name="theme-color"', 1)
    html = re.sub(r'(<meta property="og:url" content=")[^"]*(")', lambda m: m.group(1) + SITE_URL + m.group(2), html, count=1)
    html = re.sub(r'(<meta property="og:image" content=")[^"]*(")', lambda m: m.group(1) + OG_IMAGE + m.group(2), html, count=1)
    html = re.sub(r'(<meta name="twitter:image" content=")[^"]*(")', lambda m: m.group(1) + OG_IMAGE + m.group(2), html, count=1)
    return html


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", help="path to report index.html (default: latest)")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    src = Path(args.report) if args.report else latest_report()
    out = Path(args.out)
    if not src.is_file():
        raise SystemExit(f"нет файла отчёта: {src}")
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, out)
    print(f"copy: {src} -> {out}")

    py = sys.executable
    for cmd in (
        [py, str(ROOT / "scripts" / "add_landing_links.py"), "--page", str(out)],
        [py, str(ROOT / "scripts" / "add_travel_promos.py")],
    ):
        res = subprocess.run(cmd, cwd=ROOT)
        if res.returncode != 0:
            raise SystemExit(f"шаг упал: {' '.join(cmd)} (code {res.returncode})")

    html = out.read_text(encoding="utf-8")
    html = branding(html)
    out.write_text(html, encoding="utf-8")

    m = re.search(r"🗓️</span>\s*(\d{4}-\d{2}-\d{2})\s*—\s*(\d{4}-\d{2}-\d{2})", html)
    window = f"{m.group(1)} — {m.group(2)}" if m else "?"
    dates = re.findall(r"\b\d{2}\.\d{2}\.\d{4}\b", html)[:2]
    print(f"OK: {out} | заезды: {window} | дата снимка: {dates[0] if dates else '?'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
