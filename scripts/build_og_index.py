#!/usr/bin/env python3
"""OG-картинка главной (1200×630) в стиле лендинга.

    ./.venv/bin/python scripts/build_og_index.py

Пишет docs/assets/og/index.png — превью ссылки в Telegram/X/Slack.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "assets" / "og" / "index.png"

W, H = 1200, 630
BG = (6, 10, 19)
TEXT = (233, 238, 251)
MUTED = (148, 163, 192)
BLUE = (111, 155, 255)
VIOLET = (127, 116, 255)
GREEN = (47, 209, 139)

BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
REG = "/System/Library/Fonts/Supplemental/Arial.ttf"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def glow(size, center, radius, color, alpha) -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x, y = center
    draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=color + (alpha,))
    return layer.filter(ImageFilter.GaussianBlur(radius // 2))


def main() -> int:
    img = Image.new("RGB", (W, H), BG)
    img = Image.alpha_composite(img.convert("RGBA"), glow((W, H), (180, -60), 520, BLUE, 90))
    img = Image.alpha_composite(img, glow((W, H), (1100, 40), 460, VIOLET, 80))
    img = Image.alpha_composite(img, glow((W, H), (620, 700), 420, GREEN, 45))
    draw = ImageDraw.Draw(img)

    # бренд-марка
    mark = Image.new("RGBA", (72, 72), (0, 0, 0, 0))
    md = ImageDraw.Draw(mark)
    for y in range(72):
        for x in range(72):
            t = (x / 72 + y / 72) / 2
            md.point((x, y), (int(111 + (127 - 111) * t), int(155 + (116 - 155) * t), 255, 255))
    mask = Image.new("L", (72, 72), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, 71, 71], radius=20, fill=255)
    mark.putalpha(mask)
    md = ImageDraw.Draw(mark)
    cf = font(BOLD, 30)
    box = md.textbbox((0, 0), "CF", font=cf)
    md.text(((72 - (box[2] - box[0])) / 2 - box[0], (72 - (box[3] - box[1])) / 2 - box[1] - 2),
            "CF", font=cf, fill=(8, 16, 31, 255))
    img.alpha_composite(mark, (80, 76))

    draw.text((168, 96), "CONTENT FACTORY", font=font(BOLD, 22), fill=TEXT)

    chip = font(BOLD, 17)
    label = "6 CHANNELS · EN + ES"
    box = draw.textbbox((0, 0), label, font=chip)
    cw = box[2] - box[0]
    draw.rounded_rectangle([W - 80 - cw - 34, 88, W - 80, 132], radius=22,
                           outline=(148, 163, 192, 90), width=1)
    draw.text((W - 80 - cw - 17, 100), label, font=chip, fill=MUTED)

    # заголовок
    head = font(BOLD, 62)
    draw.text((80, 236), "Daily crypto, AI & sports news", font=head, fill=TEXT)
    draw.text((80, 312), "— sourced, not spun.", font=head, fill=BLUE)

    sub = font(REG, 26)
    draw.text((80, 424), "Six Telegram channels in English and Spanish.", font=sub, fill=MUTED)
    draw.text((80, 462), "CoinDesk · TechCrunch · ESPN · 15+ posts a day", font=sub, fill=(120, 134, 160))

    draw.line([80, 540, 200, 540], fill=GREEN, width=3)
    draw.text((80, 556), "valdislavn-spec.github.io/content-factory", font=font(REG, 19), fill=(140, 160, 195))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(OUT, "PNG", optimize=True)
    print("wrote", OUT.relative_to(ROOT), f"{OUT.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
