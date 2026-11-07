#!/usr/bin/env python3
"""Генерация логотипов и обложек каналов контент-фабрики.

Логотип — 512x512 PNG для аватара Telegram (безопасно для круглой обрезки).
Обложка — 1280x720 PNG с названием и описанием канала.

Запуск:  ./.venv/bin/python scripts/make_logos.py
Выход:   assets/logos/<channel>.png, assets/covers/<channel>.png
"""
from __future__ import annotations

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
LOGO_DIR = ROOT / "assets" / "logos"
COVER_DIR = ROOT / "assets" / "covers"

FONT_BLACK = "/System/Library/Fonts/Supplemental/Arial Black.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_ROUND = "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"

# id канала -> параметры оформления
CHANNELS = {
    "ai-news": dict(
        wordmark="AI", subtitle="NEWS", accent=(79, 195, 247),
        c1=(8, 20, 42), c2=(18, 84, 168), icon="ai",
        title="AI News", tagline="Models, products, policy and the companies building them",
    ),
    "tech-ai-es": dict(
        wordmark="IA", subtitle="NOTICIAS", accent=(129, 199, 255),
        c1=(16, 19, 62), c2=(64, 74, 168), icon="ai",
        title="Tecnología e IA", tagline="Modelos, productos y política de la inteligencia artificial",
    ),
    "crypto-news": dict(
        wordmark="CRYPTO", subtitle="BLOCKCHAIN", accent=(255, 193, 7),
        c1=(30, 18, 6), c2=(176, 88, 8), icon="crypto",
        title="Crypto & Blockchain", tagline="Bitcoin, Ethereum, markets, regulation and blockchain",
    ),
    "crypto-es": dict(
        wordmark="CRIPTO", subtitle="BLOCKCHAIN", accent=(255, 213, 79),
        c1=(34, 20, 8), c2=(196, 104, 12), icon="crypto",
        title="Cripto y Blockchain", tagline="Bitcoin, Ethereum, mercados, regulación y blockchain",
    ),
    "sport-news": dict(
        wordmark="SPORTS", subtitle="US NEWS", accent=(255, 209, 102),
        c1=(14, 20, 28), c2=(168, 28, 42), icon="sport",
        title="US Sports News", tagline="NFL, NBA, MLB, NHL and college sports",
    ),
    "futbol-es": dict(
        wordmark="FÚTBOL", subtitle="EN ESPAÑOL", accent=(255, 209, 102),
        c1=(6, 34, 24), c2=(26, 122, 74), icon="sport",
        title="Fútbol en Español", tagline="LaLiga, Liga MX, Argentina, MLS y Champions",
    ),
}


# ---------------------------------------------------------------------------
# утилиты
# ---------------------------------------------------------------------------
def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _gradient(size, c1, c2, angle=0.55):
    """Диагональный градиент c1→c2 (RGB)."""
    w, h = size
    img = Image.new("RGB", (w, h), c2)
    px = img.load()
    for y in range(h):
        for x in range(w):
            t = (x / w) * angle + (y / h) * (1 - angle)
            px[x, y] = _mix(c1, c2, max(0.0, min(1.0, t)))
    return img


def _vignette(img, strength=0.55):
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((-w * 0.25, -h * 0.25, w * 1.25, h * 1.25), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(max(w, h) // 8))
    dark = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(img, Image.blend(img, dark, strength), mask)


def _glow(img, center, radius, color, alpha=90):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse(
        (center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius),
        fill=color + (alpha,),
    )
    layer = layer.filter(ImageFilter.GaussianBlur(radius // 2))
    img.alpha_composite(layer) if img.mode == "RGBA" else img.paste(
        Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"), (0, 0)
    )
    return img


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:  # noqa: BLE001 - fallback, если шрифта нет
        return ImageFont.load_default()


def _text_fit(draw, text, path, max_size, max_width, min_size=22):
    size = max_size
    while size > min_size:
        font = _font(path, size)
        w = draw.textbbox((0, 0), text, font=font)[2]
        if w <= max_width:
            return font
        size -= 2
    return _font(path, min_size)


def _tracked_text(draw, xy, text, font, fill, tracking=0):
    """Текст с разрядкой (letter-spacing); возвращает ширину."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textbbox((0, 0), ch, font=font)[2] + tracking
    return x - xy[0]


def _tracked_width(draw, text, font, tracking=0):
    return sum(draw.textbbox((0, 0), ch, font=font)[2] + tracking for ch in text) - tracking


# ---------------------------------------------------------------------------
# иконки
# ---------------------------------------------------------------------------
def _icon_ai(draw, cx, cy, r, accent):
    nodes = {
        "in": [(-0.62, -0.42), (-0.62, 0.0), (-0.62, 0.42)],
        "mid": [(-0.05, -0.62), (-0.05, -0.21), (-0.05, 0.21), (-0.05, 0.62)],
        "out": [(0.62, -0.42), (0.62, 0.0), (0.62, 0.42)],
    }
    pts = {k: [(cx + x * r, cy + y * r) for x, y in v] for k, v in nodes.items()}
    for a in pts["in"]:
        for b in pts["mid"]:
            draw.line([a, b], fill=accent + (70,), width=max(2, int(r * 0.025)))
    for a in pts["mid"]:
        for b in pts["out"]:
            draw.line([a, b], fill=accent + (110,), width=max(2, int(r * 0.03)))
    for layer, radius in (("in", 0.10), ("mid", 0.12), ("out", 0.10)):
        for x, y in pts[layer]:
            rr = int(r * radius)
            draw.ellipse((x - rr, y - rr, x + rr, y + rr), fill=(255, 255, 255, 240))
            draw.ellipse((x - rr, y - rr, x + rr, y + rr), outline=accent + (255,), width=2)


def _icon_crypto(draw, cx, cy, r, accent):
    # монета
    rr = int(r * 0.52)
    draw.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=(255, 255, 255, 240), width=int(r * 0.075))
    # знак ₿: буква B с двумя вертикальными штрихами сверху (символ биткоина)
    fb = _font(FONT_BLACK, int(r * 0.62))
    box = draw.textbbox((0, 0), "B", font=fb)
    tw, th = box[2] - box[0], box[3] - box[1]
    tx = cx - tw / 2 - box[0]
    ty = cy - th / 2 - box[1] + r * 0.03
    draw.text((tx, ty), "B", font=fb, fill=(255, 255, 255, 248))
    bar = max(3, int(r * 0.055))
    left = tx + box[0]
    for fx in (0.28, 0.46):
        x = left + tw * fx
        draw.line([(x, ty - th * 0.26), (x, ty + th * 0.42)], fill=(255, 255, 255, 245), width=bar)
    # блоки цепочки справа-снизу
    bs = int(r * 0.15)
    for bx, by in [(0.82, 0.50), (1.0, 0.16)]:
        x, y = cx + bx * r, cy + by * r
        draw.rounded_rectangle((x - bs, y - bs, x + bs, y + bs), radius=max(2, bs // 3),
                               outline=accent + (240,), width=max(2, int(r * 0.025)))
        draw.line([(cx + rr * 0.72, cy + rr * 0.52), (x, y)], fill=accent + (110,), width=max(2, int(r * 0.02)))


def _icon_sport(draw, cx, cy, r, accent):
    # мяч
    rr = int(r * 0.72)
    draw.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=(255, 255, 255, 240), width=int(r * 0.055))
    # центральный пятиугольник + лучи
    pent = [(cx + math.cos(math.radians(a)) * r * 0.30,
             cy + math.sin(math.radians(a)) * r * 0.30) for a in range(-90, 270, 72)]
    draw.polygon(pent, fill=(255, 255, 255, 240))
    for a in range(-90, 270, 72):
        x0 = cx + math.cos(math.radians(a)) * r * 0.30
        y0 = cy + math.sin(math.radians(a)) * r * 0.30
        x1 = cx + math.cos(math.radians(a)) * r * 0.68
        y1 = cy + math.sin(math.radians(a)) * r * 0.68
        draw.line([(x0, y0), (x1, y1)], fill=(255, 255, 255, 220), width=int(r * 0.045))
        # маленькие пятиугольники на «швах»
        px, py = cx + math.cos(math.radians(a)) * r * 0.80, cy + math.sin(math.radians(a)) * r * 0.80
        pr = r * 0.10
        draw.polygon([(px + math.cos(math.radians(a + k * 72)) * pr,
                       py + math.sin(math.radians(a + k * 72)) * pr) for k in range(5)],
                     fill=accent + (235,))
    # траектория движения
    draw.arc((cx - r * 1.05, cy - r * 0.25, cx + r * 0.55, cy + r * 1.15), 200, 340,
             fill=accent + (170,), width=max(3, int(r * 0.035)))


ICONS = {"ai": _icon_ai, "crypto": _icon_crypto, "sport": _icon_sport}


# ---------------------------------------------------------------------------
# сборка
# ---------------------------------------------------------------------------
def make_logo(channel_id: str, spec: dict, size: int = 512) -> Image.Image:
    base = _gradient((size, size), spec["c1"], spec["c2"])
    base = _vignette(base, 0.5)
    img = base.convert("RGBA")

    # подсветка за иконкой
    img = _glow(img, (size / 2, size * 0.38), int(size * 0.32), spec["accent"], 70)

    draw = ImageDraw.Draw(img)
    ICONS[spec["icon"]](draw, size / 2, size * 0.375, size * 0.215, spec["accent"])

    # крупная надпись: вписываем по ширине и высоте
    word_font = _text_fit(draw, spec["wordmark"], FONT_BLACK, int(size * 0.20), int(size * 0.62), int(size * 0.10))
    wb = draw.textbbox((0, 0), spec["wordmark"], font=word_font)
    ww, wh = wb[2] - wb[0], wb[3] - wb[1]
    if wh > size * 0.135:  # слишком высокая — чуть уменьшаем
        word_font = _font(FONT_BLACK, max(int(size * 0.09), int(word_font.size * size * 0.135 / wh)))
        wb = draw.textbbox((0, 0), spec["wordmark"], font=word_font)
        ww, wh = wb[2] - wb[0], wb[3] - wb[1]
    wx = (size - ww) / 2 - wb[0]
    wy = size * 0.665 - wb[1]
    draw.text((wx + 2, wy + 3), spec["wordmark"], font=word_font, fill=(0, 0, 0, 130))
    draw.text((wx, wy), spec["wordmark"], font=word_font, fill=(255, 255, 255, 250))
    word_bottom = wy + wb[3]

    # подпись под названием с разрядкой
    sub_font = _font(FONT_BOLD, int(size * 0.040))
    tracking = int(size * 0.010)
    sw = _tracked_width(draw, spec["subtitle"], sub_font, tracking)
    sy = word_bottom + size * 0.030
    if sy + size * 0.052 > size * 0.945:
        sy = size * 0.945 - size * 0.052
    _tracked_text(draw, ((size - sw) / 2, sy), spec["subtitle"], sub_font,
                  spec["accent"] + (252,), tracking)

    # аккуратное кольцо
    pad = int(size * 0.050)
    draw.ellipse((pad, pad, size - pad, size - pad), outline=(255, 255, 255, 58), width=3)
    draw.arc((pad, pad, size - pad, size - pad), -62, 62, fill=spec["accent"] + (150,), width=3)
    return img.convert("RGB")


def make_cover(channel_id: str, spec: dict, size=(1280, 720)) -> Image.Image:
    w, h = size
    base = _gradient(size, spec["c1"], spec["c2"], angle=0.62)
    base = _vignette(base, 0.42)
    img = base.convert("RGBA")

    # сетка точек
    deco = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dd = ImageDraw.Draw(deco)
    for x in range(60, w, 48):
        for y in range(40, h, 48):
            dd.ellipse((x, y, x + 2, y + 2), fill=(255, 255, 255, 16))
    img = Image.alpha_composite(img, deco)

    # иконка слева
    img = _glow(img, (330, 360), 250, spec["accent"], 70)
    draw = ImageDraw.Draw(img)
    ICONS[spec["icon"]](draw, 330, 360, 190, spec["accent"])

    # текст справа
    x0 = 640
    title_font = _text_fit(draw, spec["title"], FONT_BLACK, 104, w - x0 - 90)
    draw.text((x0 + 3, h * 0.30 + 3), spec["title"], font=title_font, fill=(0, 0, 0, 120))
    draw.text((x0, h * 0.30), spec["title"], font=title_font, fill=(255, 255, 255, 252))

    # акцентная линия
    draw.rounded_rectangle((x0, h * 0.30 + (draw.textbbox((0, 0), spec["title"], font=title_font)[3]) + 26,
                            x0 + 120, h * 0.30 + (draw.textbbox((0, 0), spec["title"], font=title_font)[3]) + 34),
                           radius=4, fill=spec["accent"] + (255,))

    tag_font = _text_fit(draw, spec["tagline"], FONT_BOLD, 34, w - x0 - 90, 24)
    draw.text((x0, h * 0.70), spec["tagline"], font=tag_font, fill=(255, 255, 255, 200))
    return img.convert("RGB")


def main() -> int:
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    for channel_id, spec in CHANNELS.items():
        logo = make_logo(channel_id, spec)
        logo.save(LOGO_DIR / f"{channel_id}.png")
        cover = make_cover(channel_id, spec)
        cover.save(COVER_DIR / f"{channel_id}.png")
        print("saved:", LOGO_DIR / f"{channel_id}.png", "|", COVER_DIR / f"{channel_id}.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
