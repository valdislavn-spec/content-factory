"""Pinterest-style promo cards for the Telegram channel network.

Each card is a 1000x1500 portrait image (2:3, Pinterest format) with:
- channel logo + language/topic badge;
- large serif title and a short description;
- 3 topic bullets;
- Telegram CTA (``t.me/<handle>``);
- travel affiliate strip (partner link + ``Ad`` disclosure);
- network footer.

The aim is one card per channel that can be posted to Mastodon/Akkoma,
Bluesky/X/Facebook (via Buffer), Tumblr and Pinterest. Captions are
platform-aware: short for X/Bluesky, richer for Mastodon/Tumblr/Pinterest.

Pure-Python + Pillow (no network); safe to unit-test captions without Pillow.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

CARD_WIDTH, CARD_HEIGHT = 1000, 1500

TRAVEL_OFFERS: List[Dict[str, str]] = [
    {
        "name": "Aviasales",
        "label": "Compare flight deals",
        "label_es": "Comparar vuelos baratos",
        "display": "is.gd/Flights",
        "url": "https://links-tracker.valdislav-n.workers.dev/r/travel-aviasales",
    },
    {
        "name": "Airalo",
        "label": "Get a travel eSIM",
        "label_es": "eSIM para viajar",
        "display": "is.gd/TravelESIM",
        "url": "https://links-tracker.valdislav-n.workers.dev/r/travel-airalo",
    },
    {
        "name": "Kiwitaxi",
        "label": "Book an airport transfer",
        "label_es": "Traslado al aeropuerto",
        "display": "is.gd/AirportTaxi",
        "url": "https://links-tracker.valdislav-n.workers.dev/r/travel-kiwitaxi",
    },
    {
        "name": "Yesim",
        "label": "Mobile data for the trip",
        "label_es": "Datos móviles para el viaje",
        "display": "is.gd/TravelData",
        "url": "https://links-tracker.valdislav-n.workers.dev/r/travel-yesim",
    },
]

TRAVEL_DISCLOSURE = {
    "en": "Ad · travel partner · prices vary",
    "es": "Anuncio · socio de viajes · precios varían",
}


@dataclass
class ChannelCard:
    id: str
    language: str  # en | es
    badge: str
    title: str
    description: str
    bullets: List[str]
    cta: str
    handle: str
    telegram_url: str
    hashtags: List[str]
    accent: str
    base: str
    logo: str = ""
    alt_text: str = ""

    @property
    def filename(self) -> str:
        return f"{self.id}.png"


CARDS: Dict[str, ChannelCard] = {
    "crypto-news": ChannelCard(
        id="crypto-news",
        language="en",
        badge="TELEGRAM · EN · CRYPTO",
        title="Crypto &\nBlockchain",
        description=(
            "Bitcoin, Ethereum, markets, regulation and the companies moving "
            "the space. US-focused daily coverage."
        ),
        bullets=[
            "Bitcoin & ETF flows",
            "SEC / CFTC regulation",
            "Market moves in 5 minutes",
        ],
        cta="Follow in Telegram",
        handle="@HOOPY0007",
        telegram_url="https://t.me/HOOPY0007",
        hashtags=["#Crypto", "#Bitcoin", "#Telegram"],
        accent="#FFC107",
        base="#1E1206",
        logo="crypto-news.png",
    ),
    "ai-news": ChannelCard(
        id="ai-news",
        language="en",
        badge="TELEGRAM · EN · AI",
        title="AI News",
        description=(
            "Model releases, products, policy and the companies building AI. "
            "Daily updates from TechCrunch, The Verge, OpenAI and NVIDIA."
        ),
        bullets=[
            "New models & products",
            "AI policy & funding",
            "What actually matters",
        ],
        cta="Follow in Telegram",
        handle="@AINEWS0007",
        telegram_url="https://t.me/AINEWS0007",
        hashtags=["#AI", "#MachineLearning", "#Telegram"],
        accent="#4FC3F7",
        base="#08142A",
        logo="ai-news.png",
    ),
    "sport-news": ChannelCard(
        id="sport-news",
        language="en",
        badge="TELEGRAM · EN · US SPORTS",
        title="US Sports\nNews",
        description=(
            "NFL, NBA, MLB, NHL and college football: scores, trades, injuries "
            "and analysis. 16 updates a day, no fluff."
        ),
        bullets=[
            "Scores & injuries",
            "Trades & rumors",
            "Playoff picture",
        ],
        cta="Follow in Telegram",
        handle="@SPORTNews0007",
        telegram_url="https://t.me/SPORTNews0007",
        hashtags=["#NFL", "#NBA", "#Telegram"],
        accent="#FFD166",
        base="#0E141C",
        logo="sport-news.png",
    ),
    "crypto-es": ChannelCard(
        id="crypto-es",
        language="es",
        badge="TELEGRAM · ES · CRIPTO",
        title="Cripto &\nBlockchain",
        description=(
            "Bitcoin, Ethereum, mercados y regulación en español. "
            "CriptoNoticias, BeInCrypto y las noticias que mueven el mercado."
        ),
        bullets=[
            "Bitcoin y ETFs",
            "Regulación en LatAm",
            "Mercado en 5 minutos",
        ],
        cta="Seguir en Telegram",
        handle="@TechnologiesNews01",
        telegram_url="https://t.me/TechnologiesNews01",
        hashtags=["#Cripto", "#Bitcoin", "#Telegram"],
        accent="#FFD54F",
        base="#221408",
        logo="crypto-es.png",
    ),
    "tech-ai-es": ChannelCard(
        id="tech-ai-es",
        language="es",
        badge="TELEGRAM · ES · IA",
        title="IA en\nEspañol",
        description=(
            "Modelos, productos, empresas y políticas de IA. "
            "Hipertextual, ABC Tecnología, FayerWayer y más."
        ),
        bullets=[
            "Nuevos modelos",
            "Startups y fondos",
            "IA que importa",
        ],
        cta="Seguir en Telegram",
        handle="@WORLDNews0007",
        telegram_url="https://t.me/WORLDNews0007",
        hashtags=["#InteligenciaArtificial", "#IA", "#Telegram"],
        accent="#81C7FF",
        base="#10133E",
        logo="tech-ai-es.png",
    ),
    "futbol-es": ChannelCard(
        id="futbol-es",
        language="es",
        badge="TELEGRAM · ES · DEPORTE",
        title="Deporte &\nFútbol",
        description=(
            "Resultados, fichajes y análisis en español. "
            "LaLiga, Champions y selecciones — todos los días."
        ),
        bullets=[
            "Resultados y jornadas",
            "Fichajes y rumores",
            "Análisis táctico",
        ],
        cta="Seguir en Telegram",
        handle="@SPORTSAnalytics007",
        telegram_url="https://t.me/SPORTSAnalytics007",
        hashtags=["#Fútbol", "#Deporte", "#Telegram"],
        accent="#FFD166",
        base="#062218",
        logo="futbol-es.png",
    ),
}


def get_card(channel_id: str) -> ChannelCard:
    try:
        return CARDS[channel_id]
    except KeyError as exc:
        raise KeyError(f"нет карточки для канала {channel_id!r}") from exc


def travel_offer(index: int) -> Dict[str, str]:
    return TRAVEL_OFFERS[index % len(TRAVEL_OFFERS)]


def _clean(text: str, limit: int = 0) -> str:
    value = " ".join(str(text or "").split())
    if limit and len(value) > limit:
        value = value[: max(0, limit - 1)].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return value


def build_caption(
    card: ChannelCard,
    platform: str,
    travel: Optional[Dict[str, str]] = None,
) -> str:
    """Build a platform-aware caption with Telegram + travel links.

    platform: ``mastodon``/``akkoma`` (480), ``x`` (270), ``bluesky`` (290),
    ``facebook`` (600), ``tumblr``/``pinterest`` (1000).
    """
    platform = str(platform or "").lower()
    travel = travel or travel_offer(0)
    disclosure = TRAVEL_DISCLOSURE.get(card.language, TRAVEL_DISCLOSURE["en"])
    heading = f"📌 {card.title.replace(chr(10), ' ')} — Telegram"
    short_desc = _clean(card.description, 170 if platform in {"x", "bluesky"} else 260)
    bullets = "\n".join(f"• {_clean(item, 70)}" for item in card.bullets[:3])
    travel_label = travel.get("label") if card.language == "en" else travel.get("label_es", travel.get("label"))
    links = f"{card.cta}: {card.telegram_url}\n✈️ {travel_label}: {travel['url']} ({disclosure})"
    tags = " ".join(card.hashtags[:3])

    if platform in {"x"}:
        body = f"{card.title.replace(chr(10), ' ')} — Telegram\n\n{short_desc}\n\n{card.telegram_url} · ✈️ {travel['display']}\n\n{tags}"
        return _clean(body, 270)
    if platform == "bluesky":
        body = f"{card.title.replace(chr(10), ' ')} — Telegram\n\n{short_desc}\n\n{card.telegram_url}\n✈️ {travel['label']}: {travel['url']}\n\n{tags}"
        return body[:290]
    if platform == "facebook":
        body = f"{heading}\n\n{short_desc}\n\n{bullets}\n\n{links}\n\n{tags}"
        return body[:600]
    if platform in {"pinterest"}:
        body = (
            f"{card.title.replace(chr(10), ' ')} — {card.description} "
            f"{' '.join(card.bullets)}. {links} {tags}"
        )
        return body[:480]
    if platform == "mastodon_nolinks":
        # mastodon.social режет новые аккаунты с внешними ссылками: ссылки
        # остаются на картинке, в тексте — только описание и @handle.
        body = (
            f"{heading}\n\n{short_desc}\n\n{bullets}\n\n"
            f"{card.cta}: {card.handle} (links are on the card)\n\n{tags}"
        )
        return body[:480]
    # mastodon / akkoma / tumblr
    body = f"{heading}\n\n{short_desc}\n\n{bullets}\n\n{links}\n\n{tags}"
    return body[:480]


def render_card(
    card: ChannelCard,
    *,
    travel: Optional[Dict[str, str]] = None,
    font_dir: Optional[Path] = None,
    logo_dir: Optional[Path] = None,
    size: tuple[int, int] = (CARD_WIDTH, CARD_HEIGHT),
):
    """Render one card and return a Pillow Image (1000x1500 by default)."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    width, height = size
    root = Path(__file__).resolve().parents[1]
    font_dir = Path(font_dir) if font_dir else root / "assets" / "fonts"
    logo_dir = Path(logo_dir) if logo_dir else root / "assets" / "logos"
    travel = travel or travel_offer(0)

    def rgb(hex_value: str, fallback=(20, 24, 40)):
        value = str(hex_value or "").lstrip("#")
        try:
            return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
        except (ValueError, IndexError):
            return fallback

    base = rgb(card.base, (10, 14, 24))
    accent = rgb(card.accent, (79, 140, 255))

    # --- background: vertical gradient + soft accent glows + fine grid ----
    image = Image.new("RGB", (width, height), base)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(base[i] + (accent[i] - base[i]) * 0.16 * t) for i in range(3))
        draw.line([(0, y), (width, y)], fill=color)
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse((width - 520, -260, width + 260, 520), fill=accent + (52,))
    gdraw.ellipse((-320, height - 640, 360, height + 160), fill=accent + (28,))
    glow = glow.filter(ImageFilter.GaussianBlur(2))
    image = Image.alpha_composite(image.convert("RGBA"), glow)
    grid = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    for x in range(0, width, 40):
        gd.line([(x, 0), (x, height)], fill=(255, 255, 255, 6), width=1)
    for y in range(0, height, 40):
        gd.line([(0, y), (width, y)], fill=(255, 255, 255, 6), width=1)
    image = Image.alpha_composite(image, grid).convert("RGB")
    draw = ImageDraw.Draw(image)

    # --- fonts ------------------------------------------------------------
    def font(name: str, size: int, fallback: str):
        for path in (font_dir / name, Path(fallback)):
            try:
                return ImageFont.truetype(str(path), size=size)
            except (OSError, ValueError):
                continue
        return ImageFont.load_default()

    serif_bold = font("PlayfairDisplay.ttf", 88, "/System/Library/Fonts/Supplemental/Georgia Bold.ttf")
    sans = font("Inter.ttf", 34, "/System/Library/Fonts/Supplemental/Arial.ttf")
    sans_bold = font("Inter.ttf", 38, "/System/Library/Fonts/Supplemental/Arial Bold.ttf")
    small = font("Inter.ttf", 27, "/System/Library/Fonts/Supplemental/Arial.ttf")
    tiny = font("Inter.ttf", 23, "/System/Library/Fonts/Supplemental/Arial.ttf")

    def wrap(text: str, font_obj, max_width: int) -> List[str]:
        lines: List[str] = []
        for raw_line in str(text).splitlines():
            words, current = raw_line.split(), ""
            if not words:
                lines.append("")
                continue
            for word in words:
                candidate = (current + " " + word).strip()
                if draw.textlength(candidate, font=font_obj) <= max_width:
                    current = candidate
                else:
                    if current:
                        lines.append(current)
                    current = word
            if current:
                lines.append(current)
        return lines

    def text_block(x: int, y: int, lines: Iterable[str], font_obj, fill, spacing: int = 8) -> int:
        for line in lines:
            draw.text((x, y), line, font=font_obj, fill=fill)
            box = draw.textbbox((x, y), line, font=font_obj)
            y = box[3] + spacing
        return y

    margin = 72

    # --- header badge + logo ---------------------------------------------
    badge_font = small
    badge_text = card.badge
    bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    badge_w, badge_h = bbox[2] - bbox[0] + 36, bbox[3] - bbox[1] + 22
    draw.rounded_rectangle(
        [(margin, 56), (margin + badge_w, 56 + badge_h)],
        radius=badge_h // 2,
        fill=(12, 16, 26),
        outline=accent,
        width=2,
    )
    draw.text((margin + 18, 56 + 10), badge_text, font=badge_font, fill=(240, 246, 255))

    logo_path = logo_dir / (card.logo or f"{card.id}.png")
    logo_size = 168
    logo_x, logo_y = margin, 136
    if logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
        mask = Image.new("L", (logo_size, logo_size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, logo_size, logo_size), fill=255)
        ring = Image.new("RGBA", (logo_size + 12, logo_size + 12), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse(
            (0, 0, logo_size + 11, logo_size + 11), outline=accent + (255,), width=4
        )
        image.paste(logo, (logo_x, logo_y), mask)
        image.paste(ring, (logo_x - 6, logo_y - 6), ring)
    else:
        draw.ellipse(
            (logo_x, logo_y, logo_x + logo_size, logo_y + logo_size),
            fill=accent + (40,),
            outline=accent,
            width=4,
        )
        draw.text(
            (logo_x + logo_size // 2, logo_y + logo_size // 2),
            card.title[:2].upper(),
            font=serif_bold,
            fill=accent,
            anchor="mm",
        )

    # network line under logo
    network = "Crypto • AI • US Sports" if card.language == "en" else "Cripto • IA • Deporte"
    draw.text((logo_x + logo_size + 28, logo_y + 40), network, font=small, fill=(170, 184, 210))
    draw.text(
        (logo_x + logo_size + 28, logo_y + 82),
        "t.me/" + card.handle.lstrip("@"),
        font=sans_bold,
        fill=(255, 255, 255),
    )
    draw.text(
        (logo_x + logo_size + 28, logo_y + 126),
        "daily updates · no noise" if card.language == "en" else "noticias diarias · sin ruido",
        font=tiny,
        fill=(150, 166, 196),
    )
    draw.rectangle([(margin, 336), (width - margin, 338)], fill=accent + (120,))

    # --- title ------------------------------------------------------------
    y = 380
    y = text_block(margin, y, wrap(card.title, serif_bold, width - 2 * margin), serif_bold, (255, 255, 255), 4)
    y += 18
    desc_lines = wrap(card.description, sans, width - 2 * margin)
    y = text_block(margin, y, desc_lines, sans, (214, 224, 242), 10)
    y += 26

    # --- bullets ----------------------------------------------------------
    for bullet in card.bullets[:3]:
        draw.ellipse((margin, y + 12, margin + 14, y + 26), fill=accent)
        draw.text((margin + 30, y), bullet, font=sans_bold, fill=(240, 246, 255))
        box = draw.textbbox((margin + 30, y), bullet, font=sans_bold)
        y = box[3] + 24

    # --- trust line + CTA box --------------------------------------------
    draw.text(
        (margin, height - 470),
        ("Daily updates · Free · No spam" if card.language == "en"
         else "Actualizaciones diarias · Gratis · Sin spam"),
        font=small,
        fill=(186, 200, 224),
    )
    cta_top = height - 420
    draw.rounded_rectangle(
        [(margin, cta_top), (width - margin, cta_top + 118)],
        radius=26,
        fill=accent + (235,),
    )
    draw.text(
        (margin + 34, cta_top + 20),
        card.cta,
        font=sans_bold,
        fill=(14, 18, 28),
    )
    draw.text(
        (margin + 34, cta_top + 68),
        "t.me/" + card.handle.lstrip("@"),
        font=sans,
        fill=(14, 18, 28),
    )
    # arrow chevron
    ax, ay = width - margin - 62, cta_top + 46
    draw.line([(ax, ay), (ax + 22, ay + 16), (ax, ay + 32)], fill=(14, 18, 28), width=5, joint="curve")

    # --- travel strip -----------------------------------------------------
    strip_top = height - 270
    draw.rounded_rectangle(
        [(margin, strip_top), (width - margin, strip_top + 108)],
        radius=22,
        fill=(14, 18, 28),
        outline=(78, 90, 116),
        width=2,
    )
    travel_label = "TRAVEL DEALS" if card.language == "en" else "OFERTAS DE VIAJE"
    travel_label_text = travel.get("label") if card.language == "en" else travel.get("label_es", travel.get("label"))
    draw.text((margin + 28, strip_top + 20), travel_label, font=small, fill=accent)
    draw.text((margin + 28, strip_top + 58), travel["display"], font=sans_bold, fill=(255, 255, 255))
    draw.text(
        (margin + 28 + int(draw.textlength(travel["display"], font=sans_bold)) + 16, strip_top + 62),
        "· " + str(travel_label_text) + (" · Ad" if card.language == "en" else " · Anuncio"),
        font=small,
        fill=(206, 218, 240),
    )

    # --- footer -----------------------------------------------------------
    draw.text(
        (margin, height - 118),
        "Free Telegram channels · EN / ES" if card.language == "en" else "Canales gratis en Telegram · EN / ES",
        font=small,
        fill=(150, 166, 196),
    )
    draw.text(
        (margin, height - 76),
        " ".join(card.hashtags),
        font=small,
        fill=accent,
    )
    return image


def card_manifest(
    *,
    public_base: str = "https://valdislavn-spec.github.io/content-factory",
    channel_ids: Optional[Iterable[str]] = None,
    start_index: int = 0,
) -> List[Dict[str, Any]]:
    """Build per-card manifest with public image URL and platform captions."""
    base = str(public_base).rstrip("/")
    ids = list(channel_ids) if channel_ids else list(CARDS)
    rows: List[Dict[str, Any]] = []
    for offset, channel_id in enumerate(ids):
        card = get_card(channel_id)
        travel = travel_offer(start_index + offset)
        captions = {
            platform: build_caption(card, platform, travel)
            for platform in ("mastodon", "mastodon_nolinks", "akkoma", "x", "bluesky", "facebook", "tumblr", "pinterest")
        }
        rows.append(
            {
                "channel_id": card.id,
                "language": card.language,
                "file": card.filename,
                "image_url": (
                    "https://raw.githubusercontent.com/valdislavn-spec/content-factory/main/"
                    f"docs/assets/channel-cards/{card.filename}"
                ),
                "page_url": f"{base}/assets/channel-cards/{card.filename}",
                "title": card.title.replace("\n", " "),
                "description": _clean(card.description),
                "alt_text": f"{card.title.replace(chr(10), ' ')} — Telegram channel card",
                "telegram_url": card.telegram_url,
                "travel": travel,
                "hashtags": card.hashtags,
                "captions": captions,
            }
        )
    return rows


def render_all(output_dir: Path, *, font_dir: Optional[Path] = None) -> List[Path]:
    """Render all cards into ``output_dir``; returns written paths."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for index, channel_id in enumerate(CARDS):
        image = render_card(get_card(channel_id), travel=travel_offer(index), font_dir=font_dir)
        path = output_dir / get_card(channel_id).filename
        image.save(path, "PNG", optimize=True)
        written.append(path)
    return written
