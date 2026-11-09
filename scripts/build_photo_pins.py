#!/usr/bin/env python3
"""Photo pins v4 (Pinterest 2026 best practices): real Commons photo background,
dark overlay for contrast, <=6-word headline in the top third, keyword pill,
QR + CTA + Ad footer, mandatory photo attribution for CC BY / CC BY-SA.
"""
from __future__ import annotations
import argparse, io, json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import segno

ROOT = Path(__file__).resolve().parents[1]
W, H = 1000, 1500
INK, CREAM = (16, 16, 18), (247, 242, 233)

PINS = [
 {"slug":"bali-budget-qr","photo":"bali","tag":"BUDGET","headline":"BALI ON\nA BUDGET","promise":"7 days of rice terraces, surf and $3 meals","cta":"Find flights","url":"https://is.gd/BaliTrip","accent":(80,220,170)},
 {"slug":"dubai-weekend-qr","photo":"dubai","tag":"WEEKEND","headline":"DUBAI IN\n3 DAYS","promise":"Desert dunes, skyline and duty-free — one carry-on","cta":"Find flights","url":"https://is.gd/DubaiTrip","accent":(255,196,92)},
 {"slug":"winter-sun-qr","photo":"lisbon","tag":"WINTER SUN","headline":"3 WINTER\nESCAPES","promise":"Lisbon 15°C · Dubai 25°C · Bali 30°C","cta":"Find flights","url":"https://is.gd/Flights","accent":(120,196,255)},
 {"slug":"europe-under-300-qr","photo":"europe","tag":"BUDGET","headline":"EUROPE\nUNDER $300","promise":"A 3-night city break: cheapest months and booking windows","cta":"Find flights","url":"https://is.gd/EuropeTrip","accent":(255,140,160)},
 {"slug":"travel-esim-qr","photo":"esim","tag":"TRAVEL ESSENTIAL","headline":"TRAVEL eSIM\nTHAT WORKS","promise":"Install before you fly — data in 200+ countries","cta":"Get eSIM","url":"https://is.gd/ESimDeal","accent":(168,150,255)},
 {"slug":"car-rental-qr","photo":"car","tag":"TRAVEL ESSENTIAL","headline":"CAR RENTAL\nNO SURPRISES","promise":"Local renters, clear fuel policy, excess cover","cta":"Rent a car","url":"https://is.gd/CarRental","accent":(255,160,110)},
 {"slug":"flight-compensation-qr","photo":"flight","tag":"TRAVEL MONEY","headline":"FLIGHT\nDELAYED?","promise":"You may be owed up to €600 — check in 2 minutes","cta":"Check my flight","url":"https://is.gd/Compensair","accent":(120,240,220)},
]

def cover(img: Image.Image) -> Image.Image:
    iw, ih = img.size
    scale = max(W / iw, H / ih)
    img = img.resize((int(iw * scale) + 1, int(ih * scale) + 1))
    iw, ih = img.size
    left, top = (iw - W) // 2, (ih - H) // 2
    return img.crop((left, top, left + W, top + H))

def overlay(img: Image.Image) -> Image.Image:
    grad = Image.new("L", (1, H))
    for y in range(H):
        t = y / H
        # тёмный верх для заголовка, тёмный низ для QR, чуть светлее середина
        v = 165 - int(80 * (1 - abs(t - 0.45) * 2)) if 0.15 < t < 0.75 else 150
        grad.putpixel((0, y), max(70, min(190, v)))
    grad = grad.resize((W, H))
    black = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.composite(black, img, grad)

def wrap(draw, text, font, max_w):
    out = []
    for raw in text.split("\n"):
        words, cur = raw.split(), ""
        for w in words:
            probe = (cur + " " + w).strip()
            if draw.textlength(probe, font=font) <= max_w: cur = probe
            else:
                if cur: out.append(cur)
                cur = w
        if cur: out.append(cur)
    return out

def render(pin, photos_dir: Path, credits: dict, out_dir: Path) -> Path:
    img = Image.open(photos_dir / f"{pin['photo']}.jpg").convert("RGB")
    img = overlay(cover(img))
    draw = ImageDraw.Draw(img)
    fonts = ROOT / "assets" / "fonts"
    inter, playfair = str(fonts / "Inter.ttf"), str(fonts / "PlayfairDisplay.ttf")
    tagf = ImageFont.truetype(inter, 22); head = ImageFont.truetype(playfair, 124)
    prom = ImageFont.truetype(inter, 34); cta = ImageFont.truetype(inter, 30)
    tiny = ImageFont.truetype(inter, 20)
    accent = pin["accent"]
    # keyword pill top-right
    tw = draw.textlength(pin["tag"], font=tagf)
    draw.rounded_rectangle((W - 64 - tw - 44, 64, W - 64, 112), radius=24, fill=(0, 0, 0, 255), outline=accent, width=2)
    draw.text((W - 64 - tw - 22, 78), pin["tag"], font=tagf, fill=CREAM)
    # headline top third
    y = 236
    for line in wrap(draw, pin["headline"], head, W - 128)[:3]:
        draw.text((64, y), line, font=head, fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
        y += 126
    y += 24
    draw.rectangle((64, y, 64 + 132, y + 10), fill=accent); y += 44
    for line in wrap(draw, pin["promise"], prom, W - 128)[:2]:
        draw.text((64, y), line, font=prom, fill=(240, 244, 250), stroke_width=2, stroke_fill=(0, 0, 0))
        y += 44
    # QR bottom-left
    buf = io.BytesIO()
    segno.make(pin["url"], error="m").save(buf, kind="png", scale=10, border=2, dark="#101012", light="#ffffff")
    buf.seek(0)
    qr = Image.open(buf).convert("RGB").resize((186, 186))
    draw.rounded_rectangle((50, 1200, 50 + 186 + 28, 1200 + 186 + 28), radius=22, fill=(255, 255, 255))
    img.paste(qr, (64, 1214))
    # CTA pill
    text = pin["cta"] + "  \u2192"
    cw = draw.textlength(text, font=cta)
    draw.rounded_rectangle((300, 1300, 300 + cw + 56, 1376), radius=38, fill=(0, 0, 0, 255), outline=accent, width=2)
    draw.text((328, 1320), text, font=cta, fill=CREAM)
    # footer: ad + attribution
    draw.text((64, 1440), "Ad", font=tiny, fill=(200, 206, 216))
    credit = credits.get(pin["photo"], {})
    if credit:
        author = (credit.get("author") or "Wikimedia Commons").split(",")[0][:40]
        line = f"Photo: {author} / {credit.get('license','CC')} · Wikimedia Commons"
        draw.text((64, 1468), line, font=tiny, fill=(160, 168, 182))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{pin['slug']}.png"
    img.save(path, "PNG")
    return path

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos", default="docs/assets/photos")
    ap.add_argument("--out", default="docs/assets/pins/photo")
    args = ap.parse_args()
    photos = Path(args.photos); out = Path(args.out)
    credits = json.loads((photos / "credits.json").read_text()) if (photos / "credits.json").exists() else {}
    meta = []
    for pin in PINS:
        p = render(pin, photos, credits, out)
        print("pin:", p)
        meta.append({"slug": pin["slug"], "file": str(p), "url": pin["url"]})
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
