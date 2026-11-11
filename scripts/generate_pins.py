#!/usr/bin/env python3
"""Generate Pinterest pins (1000x1500) + JSON payloads with the brand design engine.

Usage:
    python scripts/generate_pins.py --out docs/assets/pins/2026-11-08
    python scripts/generate_pins.py --out docs/assets/pins-v5/gradient --limit 2 --no-ai
    python scripts/generate_pins.py --no-ai          # gradient backgrounds only

Backgrounds come from the Hugging Face Inference API when HUGGINGFACE_API_KEY
is set (FLUX.1-schnell by default); otherwise the branded multi-stop gradient is
used.  All rendering goes through ``content_factory/brand/design.py``, which
enforces the overflow-safe layout (safe margins, auto-fit text, no clipping),
WCAG contrast gates and Pinterest payload limits (title <= 100 chars,
description <= 500 chars including CTA + disclosure).

Each pin gets a JSON sidecar with a ready ``POST /v5/pins`` payload plus the
measured layout metrics (contrast, min font size, margins) for QA.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.brand.design import (  # noqa: E402
    DISCLOSURE_AFFILIATE,
    DISCLOSURE_GUIDE,
    PIN_SIZE,
    PinContent,
    board_for_niche,
    build_pinterest_payload,
    keywords_for,
    render_pin,
)
from content_factory.integrations.pins import hf_background, load_specs  # noqa: E402


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return slug[:60] or "pin"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate Pinterest pins")
    parser.add_argument("--config", default=str(ROOT / "config" / "pins.yaml"))
    parser.add_argument("--out", required=True, help="output directory (PNG + JSON)")
    parser.add_argument("--limit", type=int, default=0, help="max pins (0 = all)")
    parser.add_argument("--no-ai", action="store_true", help="skip Hugging Face backgrounds")
    parser.add_argument("--date", default="", help="date folder suffix, default: today (UTC)")
    parser.add_argument("--rotate", type=int, default=0,
                        help="generate N pins rotating through the config by day (avoids duplicate pins)")
    args = parser.parse_args(argv)

    import yaml

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    hub_url = str(config.get("hub_url") or "https://valdislavn-spec.github.io/content-factory/")
    public_base = str(config.get("public_base") or hub_url).rstrip("/")
    defaults = config.get("defaults") or {}
    specs = load_specs(args.config)
    if args.limit:
        specs = specs[: args.limit]
    if not specs:
        print("no pins configured")
        return 1

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    day = args.date or now.strftime("%Y-%m-%d")
    if args.rotate:
        offset = now.timetuple().tm_yday
        specs = [specs[(offset + k) % len(specs)] for k in range(max(1, args.rotate))]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    hub_token = os.environ.get("HUGGINGFACE_API_KEY") or os.environ.get("HF_TOKEN") or ""
    board_id = os.environ.get("PINTEREST_BOARD_ID", "")
    index = []

    try:
        import PIL  # noqa: F401
    except ImportError:
        print(
            "Pillow is required to render pins.\n"
            'Use the DSH python: PYTHONPATH=/tmp/segno <dsh-python> scripts/generate_pins.py ...',
            file=sys.stderr,
        )
        return 2

    for number, spec in enumerate(specs, start=1):
        affiliate = bool(str(spec.link or "").strip())
        disclosure = (
            str(spec.disclosure or "").strip()
            or (DISCLOSURE_AFFILIATE if affiliate else str(defaults.get("disclosure_guide") or DISCLOSURE_GUIDE))
        )
        if not affiliate:
            disclosure = str(defaults.get("disclosure_guide") or DISCLOSURE_GUIDE)
        content = replace(PinContent.from_object(spec), disclosure=disclosure, link=str(spec.link or "").strip())
        image_bytes = None
        if not args.no_ai and hub_token and spec.image_prompt:
            image_bytes = hf_background(spec.image_prompt, token=hub_token)
            print("  background: %s" % ("Hugging Face" if image_bytes else "gradient fallback"))
        variant = "photo" if image_bytes else "gradient"
        try:
            rendered = render_pin(
                content,
                size=PIN_SIZE,
                variants=(variant,),
                photo_bytes=image_bytes,
                font_dir=ROOT / "assets" / "fonts",
            )[variant]
        except Exception as error:  # noqa: BLE001
            print("pin %d failed quality gates: %s" % (number, error), file=sys.stderr)
            return 3

        filename = "%02d-%s.png" % (number, slugify(spec.headline))
        image_path = out_dir / filename
        rendered.save(image_path)
        try:
            relative = image_path.resolve().relative_to((ROOT / "docs").resolve()).as_posix()
        except ValueError:
            relative = image_path.name
        image_url = "%s/%s" % (public_base, relative)
        payload = build_pinterest_payload(
            content,
            image_url=image_url,
            board_id=board_id or "<BOARD_ID>",
            disclosure=disclosure,
            include_link=affiliate,
        )
        board = board_for_niche(spec.niche)
        keywords = keywords_for(spec.niche, payload["title"], payload["description"])
        meta = {
            "image_url": image_url,
            "file": str(image_path),
            "niche": spec.niche,
            "affiliate": affiliate,
            "disclosure": disclosure,
            "board": board,
            "keywords": list(keywords),
            "variant": variant,
            "pin": payload,
            "metrics": rendered.metrics.to_dict(),
        }
        json_path = out_dir / (filename.replace(".png", ".json"))
        json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        index.append(meta)
        print(
            "pin %d: %s (%d KB) variant=%s minfont=%d body_contrast=%.2f -> %s"
            % (
                number,
                filename,
                image_path.stat().st_size // 1024,
                variant,
                rendered.metrics.min_font_size,
                rendered.metrics.min_body_contrast,
                image_url,
            )
        )

    (out_dir / "index.json").write_text(
        json.dumps({"date": day, "hub": hub_url, "engine": "brand.design", "pins": index}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("done: %d pins in %s" % (len(index), out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
