"""Pinterest pin factory: 1000x1500 advert pins with headline, CTA and affiliate link.

Design goals for effective pins:
- 2:3 portrait (1000x1500), mobile-first, text readable at thumbnail size;
- strong headline (<= 6 words) + short subtitle + a CTA bar;
- explicit ``Ad`` disclosure for affiliate/partner links (FTC + Pinterest policy);
- keyword-rich title/description sidecar (JSON) ready for POST /v5/pins.

Backgrounds: optional AI image from Hugging Face Inference API
(``FLUX.1-schnell`` by default), with a deterministic gradient fallback so pin
generation never depends on network access.
"""

from __future__ import annotations

import io
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

WIDTH, HEIGHT = 1000, 1500
DEFAULT_HF_MODEL = "black-forest-labs/FLUX.1-schnell"
DEFAULT_HF_URL = "https://router.huggingface.co/hf-inference/models/" + DEFAULT_HF_MODEL
DISCLOSURE = "Ad · affiliate link"


@dataclass
class PinSpec:
    """One pin definition from config/pins.yaml."""

    niche: str
    headline: str
    subtitle: str = ""
    bullets: List[str] = field(default_factory=list)
    cta: str = "Read more"
    link: str = ""
    disclosure: str = DISCLOSURE
    image_prompt: str = ""
    title: str = ""
    description: str = ""
    alt_text: str = ""
    style: int = 0
    accent: str = "#4F8CFF"
    background: str = "#0B1220"

    def pinterest_payload(self, board_id: str, image_url: str) -> Dict[str, Any]:
        title = (self.title or self.headline)[:100]
        description = self.description or " ".join(
            part for part in (self.headline, self.subtitle, " ".join(self.bullets), self.cta) if part
        )
        if self.link:
            description = description.rstrip() + " " + self.link
        return {
            "board_id": board_id,
            "title": title,
            "description": description[:500],
            "alt_text": (self.alt_text or title)[:500],
            "link": self.link,
            "media_source": {"source_type": "image_url", "url": image_url},
        }


def _rgb(value: str, default: Tuple[int, int, int] = (79, 140, 255)) -> Tuple[int, int, int]:
    value = str(value or "").lstrip("#")
    try:
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except (ValueError, IndexError):
        return default


def _wrap(draw, text: str, font, max_width: int) -> List[str]:
    words, lines, current = str(text or "").split(), [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def hf_background(prompt: str, token: str = "", timeout: float = 60.0) -> Optional[bytes]:
    """Generate a background image with Hugging Face Inference API (optional)."""
    if not token or not prompt:
        return None
    payload = json.dumps(
        {"inputs": prompt, "parameters": {"width": 1024, "height": 1536}}
    ).encode("utf-8")
    request = urllib.request.Request(
        os.environ.get("HF_IMAGE_URL", DEFAULT_HF_URL),
        data=payload,
        method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "image/png",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
            return data if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:2] == b"\xff\xd8" else None
    except Exception:  # noqa: BLE001 - fallback gradient is fine
        return None


def _gradient_background(accent: Tuple[int, int, int], base: Tuple[int, int, int]):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (WIDTH, HEIGHT), base)
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        t = y / HEIGHT
        draw.line(
            [(0, y), (WIDTH, y)],
            fill=(
                int(base[0] + (accent[0] - base[0]) * 0.20 * t),
                int(base[1] + (accent[1] - base[1]) * 0.20 * t),
                int(base[2] + (accent[2] - base[2]) * 0.20 * t),
            ),
        )
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse((WIDTH - 620, -300, WIDTH + 220, 560), fill=accent + (60,))
    gdraw.ellipse((-340, HEIGHT - 620, 380, HEIGHT + 180), fill=accent + (34,))
    return Image.alpha_composite(image.convert("RGBA"), glow).convert("RGB")


def stock_background(prompt: str, width: int = 1000, height: int = 1500, timeout: float = 120.0) -> Optional[bytes]:
    """Fetch a photo-like background from the free Pollinations image API (with retries)."""
    import time
    import urllib.parse
    import urllib.request

    if not prompt:
        return None
    for attempt in range(4):
        seed = (abs(hash(prompt)) + attempt * 7919) % 1000000
        url = (
            "https://image.pollinations.ai/prompt/"
            + urllib.parse.quote(prompt[:380])
            + f"?width={width}&height={height}&nologo=true&seed={seed}"
        )
        request = urllib.request.Request(url, headers={"User-Agent": "content-factory-pins/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read()
            if len(data) > 5000:
                return data
        except Exception:  # noqa: BLE001
            time.sleep(4 + attempt * 6)
    return None


def render_pin(spec: PinSpec, font_dir: str | Path, image_bytes: Optional[bytes] = None):
    """Render one 1000x1500 photo-style pin and return a Pillow Image."""
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

    accent = _rgb(spec.accent, (255, 107, 53))
    photo = None
    if not image_bytes and spec.image_prompt:
        image_bytes = stock_background(spec.image_prompt)
    if image_bytes:
        try:
            photo = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            # cover-crop to 2:3
            scale = max(WIDTH / photo.width, HEIGHT / photo.height)
            photo = photo.resize((max(WIDTH, int(photo.width * scale)), max(HEIGHT, int(photo.height * scale))), Image.LANCZOS)
            left = (photo.width - WIDTH) // 2
            top = (photo.height - HEIGHT) // 3
            photo = photo.crop((left, top, left + WIDTH, top + HEIGHT))
        except Exception:  # noqa: BLE001
            photo = None
    if photo is None:
        photo = _gradient_background(accent, _rgb(spec.background, (11, 18, 32)))

    image = photo.convert("RGBA")
    # dark scrim: stronger at the bottom for text contrast
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for y in range(HEIGHT):
        bottom = max(0.0, (y - HEIGHT * 0.35) / (HEIGHT * 0.65))
        alpha = int(230 * (bottom ** 1.5))
        top_alpha = int(70 * max(0.0, (1 - y / (HEIGHT * 0.25)))) if y < HEIGHT * 0.25 else 0
        odraw.line([(0, y), (WIDTH, y)], fill=(6, 10, 18, min(245, alpha + top_alpha)))
    image = Image.alpha_composite(image, overlay).convert("RGB")
    image = image.filter(ImageFilter.SMOOTH)

    draw = ImageDraw.Draw(image)
    fonts = Path(font_dir)
    playfair = str(fonts / "PlayfairDisplay.ttf")
    inter = str(fonts / "Inter.ttf")
    chip_font = ImageFont.truetype(inter, 32)
    headline_font = ImageFont.truetype(inter, 96)
    sub_font = ImageFont.truetype(inter, 38)
    cta_font = ImageFont.truetype(inter, 40)
    small = ImageFont.truetype(inter, 24)
    badge_font = ImageFont.truetype(inter, 64)

    pad = 64
    # top chip
    chip = spec.niche.upper()
    chip_w = int(draw.textlength(chip, font=chip_font)) + 44
    draw.rounded_rectangle((pad, 56, pad + chip_w, 56 + 58), radius=29, fill=(8, 12, 20, 210))
    draw.text((pad + 22, 56 + 12), chip, font=chip_font, fill=(255, 255, 255))

    # bottom text block
    y = HEIGHT - 650
    lines = _wrap(draw, spec.headline, headline_font, WIDTH - pad * 2)[:3]
    for line in lines:
        draw.text((pad, y), line, font=headline_font, fill=(255, 255, 255), stroke_width=1, stroke_fill=(255, 255, 255))
        y += 104
    draw.rounded_rectangle((pad, y + 6, pad + 150, y + 16), radius=5, fill=accent)
    y += 64
    for line in _wrap(draw, spec.subtitle, sub_font, WIDTH - pad * 2)[:2]:
        draw.text((pad, y), line, font=sub_font, fill=(226, 232, 240))
        y += 48

    # CTA pill
    cta_text = spec.cta + "  →"
    cta_w = int(draw.textlength(cta_text, font=cta_font)) + 72
    cta_y = HEIGHT - 250
    draw.rounded_rectangle((pad, cta_y, pad + cta_w, cta_y + 82), radius=41, fill=accent)
    draw.text((pad + 36, cta_y + 18), cta_text, font=cta_font, fill=(12, 16, 24))

    # bottom row: disclosure + domain
    draw.text((pad, HEIGHT - 132), spec.disclosure, font=small, fill=(203, 213, 225))
    domain = spec.link.replace("https://", "").replace("http://", "").split("/")[0] or "content-factory"
    dw = int(draw.textlength(domain, font=small))
    draw.text((WIDTH - pad - dw, HEIGHT - 132), domain, font=small, fill=(203, 213, 225))
    # bottom bar covers generator watermark, becomes our brand strip
    draw.rectangle((0, HEIGHT - 56, WIDTH, HEIGHT), fill=(6, 10, 18))
    brand = "content-factory  ·  daily travel picks"
    bw = int(draw.textlength(brand, font=small))
    draw.text(((WIDTH - bw) // 2, HEIGHT - 42), brand, font=small, fill=(148, 163, 184))

    # small price/marker badge (top-right) when headline contains a number-like marker
    marker = None
    for token in spec.headline.split():
        if any(ch.isdigit() for ch in token) and len(token) <= 8:
            marker = token
            break
    if marker:
        cx, cy, rr = WIDTH - pad - 80, 130, 82
        draw.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=accent)
        mw = int(draw.textlength(marker, font=badge_font))
        draw.text((cx - mw // 2, cy - 40), marker, font=badge_font, fill=(12, 16, 24))
    return image


def load_specs(path: str | Path) -> List[PinSpec]:
    """Parse config/pins.yaml into PinSpec objects (PyYAML)."""
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    specs: List[PinSpec] = []
    for item in data.get("pins") or []:
        specs.append(
            PinSpec(
                niche=str(item.get("niche") or "travel"),
                headline=str(item.get("headline") or ""),
                subtitle=str(item.get("subtitle") or ""),
                bullets=[str(b) for b in (item.get("bullets") or [])],
                cta=str(item.get("cta") or "Read more"),
                link=str(item.get("link") or ""),
                disclosure=str(item.get("disclosure") or DISCLOSURE),
                image_prompt=str(item.get("image_prompt") or ""),
                title=str(item.get("title") or ""),
                description=str(item.get("description") or ""),
                alt_text=str(item.get("alt_text") or ""),
                style=int(item.get("style") or 0),
                accent=str(item.get("accent") or "#4F8CFF"),
                background=str(item.get("background") or "#0B1220"),
            )
        )
    return specs
