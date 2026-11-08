#!/usr/bin/env python3
"""Render Pinterest-style Telegram channel cards (1000x1500 PNG + JSON).

Usage:
    python scripts/generate_channel_cards.py
    python scripts/generate_channel_cards.py --out docs/assets/channel-cards
    python scripts/generate_channel_cards.py --only crypto-news,ai-news

Writes one PNG per channel, a manifest with ready captions for every platform
and a per-card Pinterest payload JSON. No network required.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory.channel_cards import (  # noqa: E402
    CARDS,
    card_manifest,
    get_card,
    render_card,
    travel_offer,
)

DEFAULT_OUT = ROOT / "docs" / "assets" / "channel-cards"
DEFAULT_PUBLIC_BASE = "https://valdislavn-spec.github.io/content-factory"


def _pinterest_payload(row: dict, index: int) -> dict:
    card = get_card(row["channel_id"])
    travel = travel_offer(index)
    return {
        "channel_id": card.id,
        "language": card.language,
        "niche": {
            "crypto-news": "crypto",
            "ai-news": "ai",
            "sport-news": "sports",
            "crypto-es": "crypto",
            "tech-ai-es": "ai",
            "futbol-es": "sports",
        }.get(card.id, "telegram"),
        "affiliate": True,
        "disclosure": "Ad · travel partner",
        "pin": {
            "board_id": "<BOARD_ID>",
            "title": row["title"][:100],
            "description": (row["description"] + " " + row["captions"]["pinterest"])[:500],
            "alt_text": row["alt_text"][:500],
            "link": card.telegram_url,
            "media_source": {"source_type": "image_url", "url": row["image_url"]},
        },
        "travel": travel,
    }


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Сгенерировать карточки Telegram-каналов")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Каталог для PNG/JSON")
    parser.add_argument("--public-base", default=DEFAULT_PUBLIC_BASE, help="Базовый URL GitHub Pages")
    parser.add_argument("--only", default="", help="Список channel_id через запятую")
    parser.add_argument("--no-json", action="store_true", help="Только PNG, без манифеста")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    out_dir = Path(args.out)
    out_dir = out_dir if out_dir.is_absolute() else ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    channel_ids = [item.strip() for item in str(args.only or "").split(",") if item.strip()]
    unknown = [channel_id for channel_id in channel_ids if channel_id not in CARDS]
    if unknown:
        print("Неизвестные каналы: {}".format(", ".join(unknown)), file=sys.stderr)
        return 2

    try:
        from PIL import Image  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        print("Pillow недоступен: {}".format(exc), file=sys.stderr)
        return 2

    ids = channel_ids or list(CARDS)
    written = []
    for index, channel_id in enumerate(ids):
        card = get_card(channel_id)
        travel = travel_offer(index)
        image = render_card(card, travel=travel)
        path = out_dir / card.filename
        image.save(path, "PNG", optimize=True)
        written.append(path)
        print("  ✓ {} ({}) → {}".format(channel_id, card.language, path.relative_to(ROOT)))

    if args.no_json:
        return 0

    rows = card_manifest(
        public_base=args.public_base,
        channel_ids=ids,
        start_index=0,
    )
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "cards": rows},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for index, row in enumerate(rows):
        payload = _pinterest_payload(row, index)
        (out_dir / (row["channel_id"] + ".json")).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print("Манифест: {}".format(manifest_path))
    print("Карточек: {}".format(len(rows)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
