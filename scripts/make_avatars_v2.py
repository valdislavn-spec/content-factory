#!/usr/bin/env python3
"""Аватары каналов v2 — 512×512, читаемые в круге Telegram.

    ./.venv/bin/python scripts/make_avatars_v2.py
    ./.venv/bin/python scripts/make_avatars_v2.py --preview

Пишет assets/avatars/<channel>.png. Стиль: тёмный фон, крупный знак,
подпись темы и языковой чип EN/ES. Контент держится внутри круга.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "avatars"
S = 512
BLACK = "/System/Library/Fonts/Supplemental/Arial Black.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

CHANNELS = {
    "crypto-news": dict(glyph="BTC", caption="CRYPTO", lang="EN", accent=(245, 165, 36)),
    "crypto-es": dict(glyph="BTC", caption="CRIPTO", lang="ES", accent=(245, 165, 36)),
    "ai-news": dict(glyph="AI", caption="NEWS", lang="EN", accent=(139, 124, 255)),
    "tech-ai-es": dict(glyph="IA", caption="NOTICIAS", lang="ES", accent=(139, 124, 255)),
    "sport-news": dict(glyph="US", caption="SPORTS", lang="EN", accent=(47, 209, 139)),
    "futbol-es": dict(glyph="FÚT", caption="BOL", lang="ES", accent=(47, 209, 139)),
    "signals": dict(glyph="", caption="SIGNALS", lang="EN", accent=(34, 211, 238)),
}


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def background(accent) -> Image.Image:
    img = Image.new("RGB", (S, S), (7, 11, 20))
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    d.ellipse([S * 0.05, -S * 0.25, S * 0.95, S * 0.62], fill=accent + (70,))
    glow = glow.filter(ImageFilter.GaussianBlur(S // 6))
    img = Image.alpha_composite(img.convert("RGBA"), glow)
    # тёмная вуаль снизу — чтобы подпись читалась
    veil = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(veil).rectangle([0, S * 0.55, S, S], fill=(7, 11, 20, 150))
    img = Image.alpha_composite(img, veil)
    return img


def bolt(draw: ImageDraw.ImageDraw, accent) -> None:
    cx, cy, w, h = S / 2, S * 0.42, S * 0.20, S * 0.30
    points = [
        (cx + w * 0.15, cy - h / 2), (cx - w / 2, cy + h * 0.08),
        (cx - w * 0.08, cy + h * 0.08), (cx - w * 0.18, cy + h / 2),
        (cx + w / 2, cy - h * 0.10), (cx + w * 0.05, cy - h * 0.10),
    ]
    draw.polygon(points, fill=accent)


def make(channel_id: str, spec: dict) -> Image.Image:
    accent = spec["accent"]
    img = background(accent)
    draw = ImageDraw.Draw(img)

    if spec["glyph"]:
        f = font(BLACK, 190 if len(spec["glyph"]) <= 2 else 132)
        box = draw.textbbox((0, 0), spec["glyph"], font=f)
        w, h = box[2] - box[0], box[3] - box[1]
        draw.text(((S - w) / 2 - box[0], S * 0.40 - h / 2 - box[1]), spec["glyph"], font=f, fill=(255, 255, 255))
    else:
        bolt(draw, accent)

    cap = spec["caption"]
    fc = font(BOLD, 40)
    while draw.textlength(cap, font=fc) > S * 0.62 and fc.size > 20:
        fc = font(BOLD, fc.size - 2)
    cw = draw.textlength(cap, font=fc)
    draw.text(((S - cw) / 2, S * 0.64), cap, font=fc, fill=(214, 224, 244))

    # языковой чип
    fl = font(BOLD, 30)
    label = spec["lang"]
    tw = draw.textlength(label, font=fl)
    pad_x, pad_y = 16, 8
    x0, y0 = (S - tw) / 2 - pad_x, S * 0.755
    chip_bg = tuple(int(7 + (accent[i] - 7) * 0.22) for i in range(3))
    draw.rounded_rectangle([x0, y0, x0 + tw + pad_x * 2, y0 + 46], radius=23,
                           fill=chip_bg, outline=accent, width=2)
    draw.text((x0 + pad_x, y0 + pad_y - 2), label, font=fl, fill=(255, 255, 255))
    return img.convert("RGB")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true", help="собрать лист предпросмотра с круглой обрезкой")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    for channel_id, spec in CHANNELS.items():
        img = make(channel_id, spec)
        img.save(OUT / f"{channel_id}.png")
        made.append((channel_id, img))
        print("saved:", (OUT / f"{channel_id}.png").relative_to(ROOT))

    if args.preview:
        cols, cell = 4, 220
        rows = (len(made) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell, rows * (cell + 24)), (4, 6, 12))
        draw = ImageDraw.Draw(sheet)
        for index, (channel_id, img) in enumerate(made):
            thumb = img.resize((cell - 20, cell - 20), Image.LANCZOS)
            mask = Image.new("L", thumb.size, 0)
            ImageDraw.Draw(mask).ellipse([0, 0, thumb.size[0] - 1, thumb.size[1] - 1], fill=255)
            x, y = (index % cols) * cell + 10, (index // cols) * (cell + 24) + 10
            sheet.paste(thumb, (x, y), mask)
            draw.text((x, y + cell - 14), channel_id, font=font(BOLD, 13), fill=(150, 165, 190))
        sheet.save("/tmp/avatars-preview.png")
        print("preview: /tmp/avatars-preview.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
