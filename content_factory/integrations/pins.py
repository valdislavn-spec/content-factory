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


def render_pin(spec: PinSpec, font_dir: str | Path, image_bytes: Optional[bytes] = None):
    """Render one 1000x1500 pin and return a Pillow Image."""
    from PIL import Image, ImageDraw, ImageFont

    accent = _rgb(spec.accent)
    if image_bytes:
        try:
            photo = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            photo = photo.resize((WIDTH, HEIGHT))
            overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
            odraw = ImageDraw.Draw(overlay)
            for y in range(HEIGHT):
                alpha = int(90 + 150 * (y / HEIGHT))
                odraw.line([(0, y), (WIDTH, y)], fill=(5, 8, 14, alpha))
            image = Image.alpha_composite(photo.convert("RGBA"), overlay).convert("RGB")
        except Exception:  # noqa: BLE001
            image = _gradient_background(accent, _rgb(spec.background, (11, 18, 32)))
    else:
        image = _gradient_background(accent, _rgb(spec.background, (11, 18, 32)))

    draw = ImageDraw.Draw(image)
    fonts = Path(font_dir)
    playfair = str(fonts / "PlayfairDisplay.ttf")
    inter = str(fonts / "Inter.ttf")
    kicker = ImageFont.truetype(inter, 34)
    headline_font = ImageFont.truetype(playfair, 96)
    sub_font = ImageFont.truetype(inter, 40)
    bullet_font = ImageFont.truetype(inter, 34)
    cta_font = ImageFont.truetype(inter, 38)
    small = ImageFont.truetype(inter, 27)

    draw.text((64, 96), spec.niche.upper(), font=kicker, fill=accent)

    y = 168
    for line in _wrap(draw, spec.headline, headline_font, WIDTH - 128)[:3]:
        draw.text((64, y), line, font=headline_font, fill=(255, 255, 255))
        y += 108
    draw.rectangle((64, y + 18, 64 + 170, y + 26), fill=accent)
    y += 70
    for line in _wrap(draw, spec.subtitle, sub_font, WIDTH - 128)[:3]:
        draw.text((64, y), line, font=sub_font, fill=(214, 224, 240))
        y += 54
    y += 16
    for bullet in spec.bullets[:4]:
        for line in _wrap(draw, "• " + bullet, bullet_font, WIDTH - 128)[:2]:
            draw.text((64, y), line, font=bullet_font, fill=(176, 190, 212))
            y += 44

    # CTA bar
    cta_y = HEIGHT - 220
    bar_width = 64 + int(draw.textlength(spec.cta + "  →", font=cta_font)) + 40
    draw.rounded_rectangle((64, cta_y, bar_width, cta_y + 68), radius=34, fill=accent)
    draw.text((64 + 26, cta_y + 13), spec.cta + "  →", font=cta_font, fill=(8, 12, 20))

    # disclosure + footer
    draw.text((64, HEIGHT - 128), spec.disclosure, font=small, fill=(240, 200, 120))
    draw.text((64, HEIGHT - 88), spec.link[:70], font=small, fill=(150, 165, 188))
    draw.text((64, HEIGHT - 52), "Saved? Follow for daily picks.", font=small, fill=(120, 134, 158))
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
