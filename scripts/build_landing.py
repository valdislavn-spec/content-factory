#!/usr/bin/env python3
"""Сгенерировать лендинг для живых каналов (EN/ES) — под GitHub Pages.

Только US/LatAm-каналы: `load_network_channels` берёт основной файл (EN) и
`config/channels.es.yaml`; RU-каналы из `channels.yaml` не участвуют.

    ./.venv/bin/python scripts/build_landing.py \
        --out exports/landing \
        --base-url https://<user>.github.io/<repo>

Затем залейте `exports/landing/` в GitHub Pages и пингуйте IndexNow:
    ./.venv/bin/python scripts/indexnow_ping.py --out exports/landing --host <user>.github.io
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.config import Settings, load_network_channels  # noqa: E402
from content_factory.integrations.landing import build_landing, public_url  # noqa: E402


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Лендинг каналов для GitHub Pages")
    parser.add_argument("--out", default="exports/landing", help="Каталог для статических файлов")
    parser.add_argument("--base-url", default="", help="Базовый URL лендинга (для sitemap)")
    parser.add_argument("--site", default="Content Factory", help="Заголовок index.html")
    parser.add_argument(
        "--measurement-id",
        default="",
        help="GA4 Measurement ID (G-...); по умолчанию GA4_MEASUREMENT_ID",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    settings = Settings.load()
    channels = load_network_channels(settings)  # EN + ES, без RU
    if not channels:
        print("Нет каналов сети (EN/ES) — проверьте config/channels.en.yaml и channels.es.yaml")
        return 2
    out = Path(args.out)
    if not out.is_absolute():
        out = Path(settings.root) / out
    result = build_landing(
        channels,
        out,
        base_url=args.base_url,
        site=args.site,
        measurement_id=args.measurement_id,
    )
    print(f"Лендинг: {len(result['pages'])} страниц каналов + index.html + sitemap.xml")
    print(f"Каталог: {out}")
    for channel in channels:
        print(f"  • {channel.id:12} {channel.title} → {public_url(channel) or '(нет ссылки)'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
