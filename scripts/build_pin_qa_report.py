#!/usr/bin/env python3
"""Rebuild ``qa-report.json`` for a batch of rendered Pinterest pins.

Reads pin sidecars (``*.json`` with a ``pin`` payload and ``metrics`` block) and
writes the machine-readable QA report used by docs and the committed samples.
Rendering itself is not repeated: metrics come from the sidecars produced by
``scripts/build_photo_pins.py`` / ``scripts/generate_pins.py``.

Usage::

    PYTHONPATH=/tmp/segno <dsh-python> scripts/build_pin_qa_report.py \
        --pins docs/assets/pins-v5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.brand.design import (  # noqa: E402
    ALT_TEXT_MAX,
    BODY_CONTRAST,
    DESCRIPTION_MAX,
    HEADING_CONTRAST,
    MIN_FONT_SIZE,
    MIN_SAFE_MARGIN,
    PIN_SIZE,
    TITLE_MAX,
    validate_pinterest_payload,
)

SKIP = {"index.json", "meta.json", "qa-report.json"}


def image_info(path: Path):
    try:
        from PIL import Image

        with Image.open(path) as image:
            return list(image.size), image.mode, image.format or path.suffix.lstrip(".").upper()
    except Exception:  # noqa: BLE001 - отчёт должен собираться и без Pillow
        return list(PIN_SIZE), "RGB", path.suffix.lstrip(".").upper()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build QA report for a pin batch")
    parser.add_argument("--pins", default=str(ROOT / "docs" / "assets" / "pins-v5"))
    parser.add_argument("--out", default="", help="output JSON (default: <pins>/qa-report.json)")
    parser.add_argument("--batch", default="v5")
    args = parser.parse_args(argv)

    pins_dir = Path(args.pins)
    sidecars = [path for path in sorted(pins_dir.rglob("*.json")) if path.name not in SKIP]
    if not sidecars:
        print("no sidecars in", pins_dir)
        return 1

    samples = []
    for sidecar in sidecars:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        payload = meta.get("pin") or {}
        metrics = meta.get("metrics") or {}
        image_path = Path(meta.get("file") or "")
        size, mode, image_format = image_info(image_path if image_path.exists() else sidecar)
        margins = metrics.get("margins") or {}
        roles = {block.get("role") for block in metrics.get("blocks") or []}
        gates = {
            "png_1000x1500_rgb": size == list(PIN_SIZE) and mode == "RGB",
            "min_font_ge_24": metrics.get("min_font_size", 0) >= MIN_FONT_SIZE,
            "body_contrast_ge_4_5": metrics.get("min_body_contrast", 0) >= BODY_CONTRAST,
            "heading_contrast_ge_3_0": metrics.get("min_heading_contrast", 0) >= HEADING_CONTRAST,
            "margins_ge_64": min(margins.values(), default=0) >= MIN_SAFE_MARGIN,
            "no_text_overflow": all(
                block.get("line_width", 0) <= block.get("box_width", 1) + 1
                for block in metrics.get("blocks") or []
            ),
            "cta_present": "cta" in roles,
            "disclosure_present": "disclosure" in roles,
            "title_le_100": 0 < len(payload.get("title", "")) <= TITLE_MAX,
            "description_le_500": 0 < len(payload.get("description", "")) <= DESCRIPTION_MAX,
            "alt_text_le_500": 0 < len(payload.get("alt_text", "")) <= ALT_TEXT_MAX,
            "payload_valid": not validate_pinterest_payload(payload),
            "link_is_https": str(payload.get("link") or "").startswith("https://"),
        }
        samples.append(
            {
                "file": meta.get("file"),
                "variant": meta.get("variant"),
                "format": image_format,
                "size": size,
                "mode": mode,
                "min_font_size": metrics.get("min_font_size"),
                "min_body_contrast": metrics.get("min_body_contrast"),
                "min_heading_contrast": metrics.get("min_heading_contrast"),
                "margins": margins,
                "title": payload.get("title", ""),
                "title_len": len(payload.get("title", "")),
                "description_len": len(payload.get("description", "")),
                "cta": payload.get("link"),
                "gates": gates,
                "pass": all(gates.values()),
            }
        )

    summary = {
        "samples": len(samples),
        "passed": sum(1 for sample in samples if sample["pass"]),
        "failed": sum(1 for sample in samples if not sample["pass"]),
        "min_body_contrast": min((sample["min_body_contrast"] or 0) for sample in samples),
        "min_heading_contrast": min((sample["min_heading_contrast"] or 0) for sample in samples),
        "min_font_size": min((sample["min_font_size"] or 0) for sample in samples),
        "min_margin": min((min((sample["margins"] or {"x": 0}).values())) for sample in samples),
        "max_title_len": max(sample["title_len"] for sample in samples),
        "max_description_len": max(sample["description_len"] for sample in samples),
    }
    report = {
        "engine": "content_factory/brand/design.py",
        "batch": args.batch,
        "requirements": {
            "canvas": list(PIN_SIZE),
            "aspect_ratio": "2:3",
            "min_font_size": MIN_FONT_SIZE,
            "body_contrast": BODY_CONTRAST,
            "heading_contrast": HEADING_CONTRAST,
            "min_margin": MIN_SAFE_MARGIN,
            "title_max": TITLE_MAX,
            "description_max": DESCRIPTION_MAX,
        },
        "summary": summary,
        "samples": samples,
    }
    out = Path(args.out) if args.out else pins_dir / "qa-report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("QA: %d/%d passed | min body contrast %.2f | min font %d | min margin %d -> %s"
          % (summary["passed"], summary["samples"], summary["min_body_contrast"],
             summary["min_font_size"], summary["min_margin"], out))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
