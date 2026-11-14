#!/usr/bin/env python3
"""Сверка лендинга с конфигом каналов.

Лендинг (`docs/index.html`) — витрина сети. Число карточек, ссылки, названия
и подписи «N каналов» должны совпадать с `config/channel_links.yaml` и
`config/channels.{en,es}.yaml`. Иначе на сайте появляется «6 каналов», когда
их пять (или наоборот) — ровно та рассинхронизация, которую ловит этот скрипт.

    python scripts/check_landing_channels.py            # проверка, код 0/1
    python scripts/check_landing_channels.py --json     # машинный вывод
"""
from __future__ import annotations

import argparse
import html as H
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

LANDING = ROOT / "docs" / "index.html"


def load_channels() -> List[Dict[str, str]]:
    """Каналы витрины: id, title, ссылка — из конфигов."""
    links = yaml.safe_load((ROOT / "config" / "channel_links.yaml").read_text(encoding="utf-8")) or {}
    out: List[Dict[str, str]] = []
    for name in ("channels.en.yaml", "channels.es.yaml"):
        data = yaml.safe_load((ROOT / "config" / name).read_text(encoding="utf-8")) or {}
        for channel in data.get("channels") or []:
            if not isinstance(channel, dict):
                continue
            channel_id = str(channel.get("id") or "")
            url = str(links.get(channel_id) or "").strip()
            if not channel_id or not url:
                continue
            out.append({
                "id": channel_id,
                "title": str(channel.get("title") or "").strip(),
                "url": url,
            })

    # Каналы вне новостных конфигов (например, signals): название берём из
    # реестра оформления, ссылку — из channel_links.yaml.
    branding_path = ROOT / "config" / "channel_branding.yaml"
    if branding_path.exists():
        branding = yaml.safe_load(branding_path.read_text(encoding="utf-8")) or {}
        known = {c["id"] for c in out}
        for entry in branding.get("channels") or []:
            if not isinstance(entry, dict):
                continue
            channel_id = str(entry.get("id") or "")
            url = str(links.get(channel_id) or "").strip()
            if not channel_id or channel_id in known or not url:
                continue
            out.append({
                "id": channel_id,
                "title": str(entry.get("title") or "").strip(),
                "url": url,
            })
    return out


def parse_landing(html: str) -> List[Dict[str, str]]:
    cards: List[Dict[str, str]] = []
    for match in re.finditer(r'<a class="chan"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        url, body = match.group(1), match.group(2)
        name = re.search(r'<span class="chan-name">(.*?)</span>', body, re.S)
        cards.append({
            "url": url,
            "title": H.unescape(re.sub(r"<[^>]+>", "", name.group(1))).strip() if name else "",
        })
    return cards


def declared_counts(html: str) -> Dict[str, int]:
    """Числа, которые страница утверждает о сети."""
    def num(pattern: str) -> int:
        found = re.search(pattern, html)
        return int(found.group(1)) if found else -1

    return {
        "eyebrow": num(r"Telegram network · (\d+) channels"),
        "hero_stat": num(r"<b>(\d+)</b> channels"),
        "footer": num(r"English &amp; Spanish · (\d+) channels"),
        "json_items": num(r'"numberOfItems": (\d+)'),
    }


def check() -> Dict[str, Any]:
    html = LANDING.read_text(encoding="utf-8")
    expected = load_channels()
    cards = parse_landing(html)
    problems: List[str] = []

    if len(cards) != len(expected):
        problems.append(f"карточек на странице {len(cards)}, каналов в конфиге {len(expected)}")

    want_urls = [c["url"] for c in expected]
    got_urls = [c["url"] for c in cards]
    for url in want_urls:
        if url not in got_urls:
            problems.append(f"канал из конфига отсутствует на странице: {url}")
    for url in got_urls:
        if url not in want_urls:
            problems.append(f"на странице есть канал вне конфига: {url}")

    titles = {c["url"]: c["title"] for c in expected}
    for card in cards:
        want = titles.get(card["url"])
        if want and card["title"] and card["title"] != want:
            problems.append(f"название расходится: страница «{card['title']}», конфиг «{want}»")

    total = len(expected)
    for label, value in declared_counts(html).items():
        if value != total:
            problems.append(f"подпись «{label}» = {value}, а каналов {total}")

    return {"ok": not problems, "channels": total, "cards": len(cards), "problems": problems}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Сверка лендинга с конфигом каналов")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = check()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"каналов в конфиге: {result['channels']} · карточек на странице: {result['cards']}")
        for problem in result["problems"]:
            print("  ✗", problem)
        print("OK" if result["ok"] else "РАСХОЖДЕНИЕ")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
