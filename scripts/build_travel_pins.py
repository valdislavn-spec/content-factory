#!/usr/bin/env python3
"""Пины для Pinterest из travel-гидов: 3 варианта на страницу.

    ./.venv/bin/python scripts/build_travel_pins.py
    ./.venv/bin/python scripts/build_travel_pins.py --out docs/assets/pins-travel

Пишет PNG 1000×1500 + pins.csv (title, description, link, board) — готово
к загрузке в Pinterest. Фото берутся из docs/assets/photos, текст — из самих
страниц, чтобы пин и лендинг не расходились.
"""
from __future__ import annotations

import argparse
import csv
import html as html_lib
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
GUIDES = DOCS / "travel"
PHOTOS = DOCS / "assets" / "photos"
FONT_DIR = ROOT / "assets" / "fonts"

W, H = 1000, 1500
BASE = (7, 11, 20)

# страница → фото и доска Pinterest
# Фото ставим только там, где оно про этот же сюжет. Иначе — типографический
# пин: чужая фотография (Дубай под Алматы, Лиссабон под Рим) вводит в заблуждение.
PAGES = {
    "europe-under-300": ("europe", "Travel on a budget"),
    "bali-budget": ("bali", "Travel on a budget"),
    "rome-48-hours": (None, "City breaks"),
    "travel-esim": ("esim", "Travel tips"),
    "car-rental-europe": ("car", "Travel tips"),
    "airport-transfer-guide": ("flight", "Travel tips"),
    "luggage-storage-guide": (None, "Travel tips"),
    "skip-the-line-tickets-guide": (None, "City breaks"),
    "almaty-48-hours": (None, "City breaks"),
    "minsk-weekend": (None, "City breaks"),
}

VARIANTS = [
    ("bottom", (245, 165, 36), "bottom"),
    ("center", (47, 209, 139), "center"),
    ("top", (139, 124, 255), "top"),
]


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONT_DIR / name
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def page_text(slug: str) -> tuple[str, str]:
    """Заголовок и описание из самой страницы."""
    source = (GUIDES / f"{slug}.html").read_text(encoding="utf-8")
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", source, re.S)
    desc = re.search(r'<meta name="description" content="([^"]*)"', source)
    title = html_lib.unescape(re.sub(r"<[^>]+>", "", h1.group(1))).strip() if h1 else slug
    description = html_lib.unescape(desc.group(1)).strip() if desc else title
    return title, description


def wrap(draw, text: str, font_obj, max_width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        candidate = (current + " " + word).strip()
        if draw.textlength(candidate, font=font_obj) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def fit_headline(draw, text: str, max_width: int, max_lines: int = 4):
    size = 108
    while size >= 56:
        candidate = font("PlayfairDisplay.ttf", size)
        lines = wrap(draw, text, candidate, max_width)
        if len(lines) <= max_lines:
            return candidate, lines, size
        size -= 6
    candidate = font("PlayfairDisplay.ttf", 54)
    return candidate, wrap(draw, text, candidate, max_width)[:max_lines], 54


def cover(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGB")
    scale = max(W / image.width, H / image.height)
    resized = image.resize((int(image.width * scale) + 1, int(image.height * scale) + 1), Image.LANCZOS)
    left = (resized.width - W) // 2
    top = (resized.height - H) // 3
    return resized.crop((left, top, left + W, top + H))


def scrim(position: str, accent: tuple[int, int, int]) -> Image.Image:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    if position == "bottom":
        for y in range(H):
            t = max(0.0, (y - H * 0.35) / (H * 0.65))
            draw.line([(0, y), (W, y)], fill=BASE + (int(252 * t ** 1.25),))
    elif position == "top":
        for y in range(H):
            t = max(0.0, (H * 0.65 - y) / (H * 0.65))
            draw.line([(0, y), (W, y)], fill=BASE + (int(252 * t ** 1.25),))
    else:
        draw.rectangle([0, 0, W, H], fill=BASE + (150,))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((-260, H - 520, 420, H + 120), fill=accent + (60,))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    return Image.alpha_composite(layer, glow)


def typographic(accent, position: str) -> Image.Image:
    """Фон без фото: тёмный градиент + мягкое свечение акцента."""
    image = Image.new("RGBA", (W, H), BASE + (255,))
    draw = ImageDraw.Draw(image)
    for y in range(H):
        t = y / H
        draw.line([(0, y), (W, y)], fill=(int(BASE[0] + accent[0] * 0.10 * t),
                                          int(BASE[1] + accent[1] * 0.10 * t),
                                          int(BASE[2] + accent[2] * 0.10 * t), 255))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((-200, -180, W + 200, 620), fill=accent + (55,))
    glow = glow.filter(ImageFilter.GaussianBlur(150))
    return Image.alpha_composite(image, glow)


def render(slug: str, title: str, description: str, photo, accent, position: str) -> Image.Image:
    if photo:
        image = cover(PHOTOS / f"{photo}.jpg").convert("RGBA")
        image = Image.alpha_composite(image, scrim(position, accent))
    else:
        image = typographic(accent, position)
        rings = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ring_draw = ImageDraw.Draw(rings)
        for radius in (420, 300, 190):
            ring_draw.ellipse((W - radius - 40, -radius + 120, W + radius - 40, radius + 120),
                              outline=accent + (42,), width=3)
        image = Image.alpha_composite(image, rings)
    draw = ImageDraw.Draw(image)

    margin = 72
    pill_font = font("Inter.ttf", 24)
    label = "TRAVEL GUIDE"
    tw = draw.textlength(label, font=pill_font)
    draw.rounded_rectangle([margin, 64, margin + tw + 44, 112], radius=24,
                           fill=(7, 11, 20, 170), outline=accent, width=2)
    draw.text((margin + 22, 76), label, font=pill_font, fill=(235, 241, 252))

    head_font, head_lines, size = fit_headline(draw, title, W - margin * 2)
    line_h = int(size * 1.12)
    body_font = font("Inter.ttf", 30)
    body_all = wrap(draw, description, body_font, W - margin * 2)
    body_lines = body_all[:2]
    if len(body_all) > 2:
        last = body_lines[-1]
        while last and draw.textlength(last + "…", font=body_font) > W - margin * 2:
            last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
        body_lines[-1] = last.rstrip(" ,;:.") + "…"
    block_h = len(head_lines) * line_h + 18 + len(body_lines) * 42 + 46 + 70

    y = {"bottom": H - block_h - 120, "center": (H - block_h) // 2, "top": 190}[position]
    for line in head_lines:
        draw.text((margin + 2, y + 3), line, font=head_font, fill=(0, 0, 0, 120))
        draw.text((margin, y), line, font=head_font, fill=(255, 255, 255))
        y += line_h
    y += 18
    for line in body_lines:
        draw.text((margin, y), line, font=body_font, fill=(226, 233, 246))
        y += 42

    y += 30
    draw.rounded_rectangle([margin, y, margin + 78, y + 6], radius=3, fill=accent)
    y += 40
    small = font("Inter.ttf", 22)
    draw.text((margin, y), "valdislavn-spec.github.io", font=small, fill=(190, 203, 224))
    draw.text((W - margin - 130, y - 4), "Save  →", font=font("Inter.ttf", 24), fill=accent)
    return image.convert("RGB")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DOCS / "assets" / "pins-travel"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for slug, (photo, board) in PAGES.items():
        title, description = page_text(slug)
        link = f"https://valdislavn-spec.github.io/content-factory/travel/{slug}.html"
        for name, accent, position in VARIANTS:
            filename = f"{slug}-{name}.jpg"
            layout = position if photo else "bottom"
            render(slug, title, description, photo, accent, layout).save(
                out / filename, "JPEG", quality=88, optimize=True, progressive=True
            )
            rows.append({
                "file": filename,
                "title": f"{title} | Travel guide",
                "description": description[:480],
                "link": link,
                "board": board,
            })
        print("✓", slug, "→ 3 варианта")

    with (out / "pins.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file", "title", "description", "link", "board"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nвсего пинов: {len(rows)} · CSV: {out / 'pins.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
