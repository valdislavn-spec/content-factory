#!/usr/bin/env python3
"""Pinterest-style pin images (1000x1500) with QR code + short affiliate URL baked in.

Usage:
    .venv/bin/python scripts/build_qr_pins.py --out docs/assets/pins/qr
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import segno

ROOT = Path(__file__).resolve().parents[1]
W, H = 1000, 1500

PINS = [
    {
        "slug": "bali-budget-qr",
        "niche": "TRAVEL DEAL",
        "headline": "Bali on a budget",
        "subtitle": "Rice terraces, surf and $3 meals — 7-day plan under $500",
        "cta": "Scan or visit is.gd/BaliTrip",
        "url": "https://is.gd/BaliTrip",
        "accent": (46, 204, 149),
    },
    {
        "slug": "dubai-weekend-qr",
        "niche": "TRAVEL DEAL",
        "headline": "Dubai weekend",
        "subtitle": "Desert dunes, skyline views, duty-free — 3 days, one carry-on",
        "cta": "Scan or visit is.gd/DubaiTrip",
        "url": "https://is.gd/DubaiTrip",
        "accent": (240, 180, 60),
    },
    {
        "slug": "winter-sun-qr",
        "niche": "WINTER SUN",
        "headline": "3 winter escapes",
        "subtitle": "Lisbon 15°C · Dubai 25°C · Bali 30°C — cheap flights from $199",
        "cta": "Scan or visit is.gd/Flights",
        "url": "https://is.gd/Flights",
        "accent": (64, 156, 255),
    },
    {
        "slug": "europe-under-300-qr",
        "niche": "BUDGET TRIP",
        "headline": "Europe under $300",
        "subtitle": "3-night city break: cheapest months, carry-on and booking window",
        "cta": "Scan or visit is.gd/EuropeTrip",
        "url": "https://is.gd/EuropeTrip",
        "accent": (196, 92, 120),
    },
]


def gradient(accent: tuple[int, int, int]) -> Image.Image:
    base = Image.new("RGB", (W, H))
    px = base.load()
    dark = (11, 18, 32)
    for y in range(H):
        t = y / H
        for x in range(0, W, 1):
            # horizontal accent glow on the left + vertical darkening
            gx = max(0.0, 1.0 - abs(x - W * 0.18) / (W * 0.55))
            r = int(dark[0] + (accent[0] - dark[0]) * 0.28 * gx * (1 - t) + 18 * (1 - t))
            g = int(dark[1] + (accent[1] - dark[1]) * 0.30 * gx * (1 - t) + 14 * (1 - t))
            b = int(dark[2] + (accent[2] - dark[2]) * 0.34 * gx * (1 - t) + 10 * (1 - t))
            px[x, y] = (min(r, 255), min(g, 255), min(b, 255))
    # subtle bottom vignette
    grad = Image.new("L", (1, H))
    for y in range(H):
        grad.putpixel((0, y), int(120 * (y / H)))
    grad = grad.resize((W, H))
    black = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.composite(black, base, grad.point(lambda v: v // 2))


def wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        probe = (cur + " " + w).strip()
        if draw.textlength(probe, font=font) <= max_w:
            cur = probe
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def render(pin: dict, out_dir: Path) -> Path:
    accent = pin["accent"]
    img = gradient(accent)
    draw = ImageDraw.Draw(img)
    fonts = ROOT / "assets" / "fonts"
    inter = str(fonts / "Inter.ttf")
    playfair = str(fonts / "PlayfairDisplay.ttf")
    kicker = ImageFont.truetype(inter, 34)
    head = ImageFont.truetype(playfair, 92)
    sub = ImageFont.truetype(inter, 40)
    cta = ImageFont.truetype(inter, 34)
    small = ImageFont.truetype(inter, 26)

    draw.text((64, 96), pin["niche"], font=kicker, fill=accent)
    y = 170
    for line in wrap(draw, pin["headline"], head, W - 128)[:3]:
        draw.text((64, y), line, font=head, fill=(255, 255, 255))
        y += 104
    draw.rectangle((64, y + 14, 64 + 170, y + 22), fill=accent)
    y += 62
    for line in wrap(draw, pin["subtitle"], sub, W - 128)[:3]:
        draw.text((64, y), line, font=sub, fill=(214, 224, 240))
        y += 50

    # QR block bottom-left
    qr = segno.make(pin["url"], error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=10, border=2, dark="#0b1220", light="#ffffff")
    buf.seek(0)
    qr_img = Image.open(buf).convert("RGB")
    qr_size = 330
    qr_img = qr_img.resize((qr_size, qr_size))
    qx, qy = 64, H - qr_size - 150
    pad = 18
    draw.rounded_rectangle((qx - pad, qy - pad, qx + qr_size + pad, qy + qr_size + pad), radius=26, fill=(255, 255, 255))
    img.paste(qr_img, (qx, qy))

    # CTA to the right of QR
    tx = qx + qr_size + pad * 2 + 34
    draw.text((tx, qy + 6), "SCAN", font=kicker, fill=accent)
    draw.text((tx, qy + 52), "or visit", font=sub, fill=(230, 236, 245))
    cta_text = pin["cta"].replace("Scan or visit ", "")
    draw.text((tx, qy + 108), cta_text, font=cta, fill=(255, 255, 255))

    # disclosure bottom
    draw.text((64, H - 92), "Ad · affiliate link · prices change", font=small, fill=(150, 162, 180))
    draw.text((64, H - 60), "valdislavn-spec.github.io/content-factory", font=small, fill=(120, 132, 150))

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{pin['slug']}.png"
    img.save(path, "PNG")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "assets" / "pins" / "qr"))
    args = ap.parse_args()
    out = Path(args.out)
    meta = []
    for pin in PINS:
        p = render(pin, out)
        print("pin:", p)
        meta.append({"slug": pin["slug"], "file": str(p), "url": pin["url"], "headline": pin["headline"]})
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print("meta:", out / "meta.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
