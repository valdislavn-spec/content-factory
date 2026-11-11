#!/usr/bin/env python3
"""Generate advert/affiliate Pinterest pins (1000x1500) + JSON payloads.

Usage:
    python scripts/generate_pins.py --out docs/assets/pins/2026-11-08
    python scripts/generate_pins.py --no-ai          # gradient backgrounds only

Backgrounds come from the Hugging Face Inference API when HUGGINGFACE_API_KEY
is set (FLUX.1-schnell by default); otherwise a branded gradient is used.
Each pin gets a JSON sidecar with a ready ``POST /v5/pins`` payload.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.integrations.pins import (  # noqa: E402
    DEFAULT_HF_MODEL,
    DISCLOSURE,
    hf_background,
    load_specs,
    render_pin,
)


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
    font_dir = ROOT / "assets" / "fonts"
    hf_token = os.environ.get("HUGGINGFACE_API_KEY") or os.environ.get("HF_TOKEN") or ""
    board_id = os.environ.get("PINTEREST_BOARD_ID", "")
    index = []

    for number, spec in enumerate(specs, start=1):
        link = spec.link.strip() or hub_url
        disclosure = spec.disclosure
        if not spec.link.strip():
            disclosure = str(defaults.get("disclosure_guide") or "Save this guide")
        spec.disclosure = disclosure
        image_bytes = None
        if not args.no_ai and hf_token and spec.image_prompt:
            image_bytes = hf_background(spec.image_prompt, token=hf_token)
            print("  background: %s" % ("Hugging Face" if image_bytes else "photo (stock) fallback"))
        image = render_pin(spec, font_dir, image_bytes=image_bytes)
        filename = "%02d-%s.png" % (number, slugify(spec.headline))
        image_path = out_dir / filename
        image.save(image_path, "PNG", optimize=True)

        try:
            relative = image_path.resolve().relative_to((ROOT / "docs").resolve()).as_posix()
        except ValueError:
            relative = image_path.name
        image_url = "%s/%s" % (public_base, relative)
        payload = spec.pinterest_payload(board_id or "<BOARD_ID>", image_url)
        if not spec.link.strip():
            payload.pop("link", None)
            payload["description"] = payload["description"][: 450]
        meta = {
            "image_url": image_url,
            "file": str(image_path),
            "niche": spec.niche,
            "affiliate": bool(spec.link.strip()),
            "disclosure": disclosure,
            "pin": payload,
        }
        json_path = out_dir / (filename.replace(".png", ".json"))
        json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        index.append(meta)
        print("pin %d: %s (%d KB) -> %s" % (number, filename, image_path.stat().st_size // 1024, image_url))

    (out_dir / "index.json").write_text(
        json.dumps({"date": day, "hub": hub_url, "pins": index}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("done: %d pins in %s" % (len(index), out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
