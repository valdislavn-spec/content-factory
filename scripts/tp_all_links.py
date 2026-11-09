#!/usr/bin/env python3
"""Travelpayouts: партнёрские ссылки для ВСЕХ подключённых программ (API).

    python scripts/tp_all_links.py              # показать таблицу
    python scripts/tp_all_links.py --write      # обновить config/affiliate_links.yaml
    python scripts/tp_all_links.py --json out.json

Требует в .env: TRAVELPAYOUTS_API_TOKEN, TRAVELPAYOUTS_MARKER,
TRAVELPAYOUTS_TRS (проект: 597635 — Telegram, 597672 — сайт).
API: POST https://api.travelpayouts.com/links/v1/create (до 10 ссылок/запрос).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.utils import load_dotenv  # noqa: E402

import yaml  # noqa: E402

API = "https://api.travelpayouts.com/links/v1/create"
BATCH = 10

# Программы Travelpayouts: слаг -> полный URL бренда (API требует长 ссылки).
BRANDS = {
    "aviasales": "https://www.aviasales.com/",
    "hotellook": "https://www.hotellook.com/",
    "booking": "https://www.booking.com/",
    "getyourguide": "https://www.getyourguide.com/",
    "tiqets": "https://www.tiqets.com/",
    "klook": "https://www.klook.com/",
    "saily": "https://saily.com/",
    "airalo": "https://www.airalo.com/",
    "yesim": "https://yesim.app/",
    "kiwitaxi": "https://kiwitaxi.com/",
    "compensair": "https://compensair.com/",
    "airhelp": "https://www.airhelp.com/",
    "trip": "https://www.trip.com/",
    "agoda": "https://www.agoda.com/",
    "expedia": "https://www.expedia.com/",
    "hotels": "https://www.hotels.com/",
    "discovercars": "https://www.discovercars.com/",
    "rentalcars": "https://www.rentalcars.com/",
    "omio": "https://www.omio.com/",
    "12go": "https://12go.asia/",
    "welcomepickups": "https://www.welcomepickups.com/",
    "wegotrip": "https://wegotrip.com/",
    "musement": "https://www.musement.com/",
    "viator": "https://www.viator.com/",
    "cheapoair": "https://www.cheapoair.com/",
}


def _settings() -> tuple[str, str, str]:
    load_dotenv(str(ROOT / ".env"))
    token = os.environ.get("TRAVELPAYOUTS_API_TOKEN", "").strip()
    marker = os.environ.get("TRAVELPAYOUTS_MARKER", "").strip()
    trs = os.environ.get("TRAVELPAYOUTS_TRS", "").strip()
    if not trs:
        trs = "597672"
    if not (token and marker):
        raise SystemExit("нет TRAVELPAYOUTS_API_TOKEN / TRAVELPAYOUTS_MARKER в .env")
    return token, marker, trs


def convert(token: str, marker: str, trs: str, items: list[dict]) -> list[dict]:
    payload = json.dumps({
        "trs": int(trs),
        "marker": int(marker),
        "shorten": True,
        "links": items,
    }).encode()
    request = urllib.request.Request(
        API,
        data=payload,
        method="POST",
        headers={
            "X-Access-Token": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "content-factory-tp/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as error:
        raise SystemExit("HTTP %s: %s" % (error.code, error.read()[:300]))
    return list((data.get("result") or {}).get("links") or [])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="записать config/affiliate_links.yaml")
    parser.add_argument("--json", dest="json_path", default="")
    args = parser.parse_args()

    token, marker, trs = _settings()
    items = [{"url": url, "sub_id": "cf_" + slug} for slug, url in BRANDS.items()]
    results: list[dict] = []
    for start in range(0, len(items), BATCH):
        chunk = items[start:start + BATCH]
        converted = convert(token, marker, trs, chunk)
        for item, result in zip(chunk, converted):
            code = str(result.get("code") or "")
            results.append({
                "program": next((slug for slug, url in BRANDS.items() if url == item["url"]), ""),
                "url": item["url"],
                "code": code,
                "partner_url": result.get("partner_url") or "",
                "message": result.get("message") or "",
            })

    ok = [r for r in results if r["code"] == "success" and r["partner_url"]]
    failed = [r for r in results if r not in ok]
    print("Маркер: %s | trs: %s | успешно: %d | недоступно: %d" % (marker, trs, len(ok), len(failed)))
    for r in results:
        mark = "✅" if r in ok else "—"
        print("%s %-13s %s %s" % (mark, r["program"], r["partner_url"] or r["message"], ""))
    if failed:
        print("\nНе подключены/не поддержаны:", ", ".join(r["program"] for r in failed))

    if args.write and ok:
        path = ROOT / "config" / "affiliate_links.yaml"
        data = {
            "marker": marker,
            "trs": int(trs),
            "generated_by": "scripts/tp_all_links.py",
            "programs": {
                r["program"]: {"brand_url": r["url"], "partner_url": r["partner_url"]}
                for r in ok
            },
        }
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print("\nзаписано:", path)

    if args.json_path:
        Path(args.json_path).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        print("JSON:", args.json_path)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
