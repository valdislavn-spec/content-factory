"""Design system + overflow-safe layout engine for Pinterest pins (1000x1500).

The module is split in two layers:

* **pure layer** (no Pillow import at module load): design tokens, colour and
  WCAG contrast math, gradient/cover/scrim math, text auto-fit, the layout
  engine and Pinterest payload/CSV helpers.  It runs in any Python 3.9 venv and
  is covered by ``tests/test_brand_design.py`` without image dependencies.
* **render layer** (lazy ``from PIL import ...``): multi-stop gradient and photo
  backgrounds, scrims, rounded cards, CTA pill, brand mark, disclosure footer,
  optional QR (``segno``) and measured-contrast validation.

Typical use::

    from content_factory.brand import design

    content = design.PinContent(
        niche="travel",
        headline="Bali on a budget",
        subtitle="7 days, beaches and rice terraces",
        bullets=("$35-60/day", "Avoid July-August"),
        cta="Read the guide",
        description="What 7 days in Bali actually cost.",
    )
    rendered = design.render_pin(content, variants=("gradient",))["gradient"]
    rendered.save("pin.png")
    rendered.metrics.to_dict()       # measured contrast / min font / margins
    payload = design.build_pinterest_payload(
        content, image_url="https://example.com/pin.png"
    )  # title<=100, description<=500 (CTA+disclosure), alt text
"""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Paths & fixed Pinterest constraints
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
FONT_DIR = ROOT / "assets" / "fonts"
FONT_FILES = {"sans": "Inter.ttf", "display": "PlayfairDisplay.ttf"}

PIN_SIZE = (1000, 1500)
PIN_ASPECT = PIN_SIZE[0] / PIN_SIZE[1]  # 2:3 portrait
TITLE_MAX = 100
DESCRIPTION_MAX = 500
ALT_TEXT_MAX = 500
DISCLOSURE_AFFILIATE = "Ad \u00b7 affiliate link"
DISCLOSURE_GUIDE = "Save this guide"
DEFAULT_SITE = "valdislavn-spec.github.io"

#: Layout quality floors (asserted by tests and by the renderer).
MIN_FONT_SIZE = 24          # never render text smaller than this
SAFE_MARGIN = 72            # designed safe margin for the 1000x1500 canvas
MIN_SAFE_MARGIN = 64        # hard floor accepted by QA
BODY_CONTRAST = 4.5         # WCAG AA for normal text
HEADING_CONTRAST = 3.0      # WCAG AA for large text
HEADLINE_MAX_LINES = 3
SUBTITLE_MAX_LINES = 3
BULLET_MAX_LINES = 2
MAX_BULLETS = 3
SUBTITLE_MIN_SIZE = 32

RGB = Tuple[int, int, int]


class DesignError(Exception):
    """Base error for the design system."""


class LayoutOverflowError(DesignError):
    """Content cannot be placed inside the pin without overflow."""


class TextOverflowError(LayoutOverflowError):
    """A single text (e.g. an unbreakable word) cannot be fitted."""


class QualityError(DesignError):
    """Rendered/layout quality gates failed (contrast, margins, fonts...)."""


class PinterestPayloadError(DesignError):
    """Pinterest payload / CSV row is not publishable."""


# ---------------------------------------------------------------------------
# Colour math (WCAG 2.1)
# ---------------------------------------------------------------------------

INK: RGB = (11, 11, 16)
CREAM: RGB = (247, 242, 233)
WHITE: RGB = (255, 255, 255)
MUTED: RGB = (176, 184, 198)


def hex_to_rgb(value: Any, default: RGB = (79, 140, 255)) -> RGB:
    """``#RRGGBB`` / ``RRGGBB`` -> ``(r, g, b)``; *default* on bad input."""
    text = str(value or "").strip().lstrip("#")
    if len(text) == 3 and all(ch in "0123456789abcdefABCDEF" for ch in text):
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        return default
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return default


def rgb_to_hex(rgb: RGB) -> str:
    return "#%02X%02X%02X" % (int(rgb[0]), int(rgb[1]), int(rgb[2]))


def _clamp_channel(value: float) -> int:
    return max(0, min(255, int(round(value))))


def _srgb_to_linear(channel: float) -> float:
    value = channel / 255.0
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: Sequence[int]) -> float:
    """WCAG relative luminance of an sRGB triple (0.0 .. 1.0)."""
    red, green, blue = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
    return (
        0.2126 * _srgb_to_linear(red)
        + 0.7152 * _srgb_to_linear(green)
        + 0.0722 * _srgb_to_linear(blue)
    )


def contrast_ratio(foreground: Sequence[int], background: Sequence[int]) -> float:
    """WCAG contrast ratio (1.0 .. 21.0) between two sRGB colours."""
    first = relative_luminance(foreground)
    second = relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def contrast_from_luminance(first: float, second: float) -> float:
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def mix(first: RGB, second: RGB, amount: float) -> RGB:
    """Blend *first* towards *second* by ``amount`` (0..1)."""
    t = max(0.0, min(1.0, float(amount)))
    return (
        _clamp_channel(first[0] + (second[0] - first[0]) * t),
        _clamp_channel(first[1] + (second[1] - first[1]) * t),
        _clamp_channel(first[2] + (second[2] - first[2]) * t),
    )


def composite_over(foreground: Sequence[int], background: Sequence[int], alpha: float) -> RGB:
    """Alpha-composite ``foreground`` over ``background`` (both sRGB)."""
    return mix(tuple(int(c) for c in background), tuple(int(c) for c in foreground), alpha)  # type: ignore[arg-type]


def best_text_color(
    background: Sequence[int],
    candidates: Sequence[RGB] = (INK, WHITE, CREAM),
) -> RGB:
    """Candidate text colour with the highest contrast on *background*."""
    best = None
    for candidate in candidates:
        ratio = contrast_ratio(candidate, background)
        if best is None or ratio > best[0] + 1e-9:
            best = (ratio, candidate)
    assert best is not None
    return best[1]


def color_distance(first: Sequence[int], second: Sequence[int]) -> float:
    return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(first, second)))


def ensure_contrast(
    foreground: Sequence[int],
    background: Sequence[int],
    target: float = BODY_CONTRAST,
    candidates: Sequence[RGB] = (WHITE, INK),
) -> RGB:
    """Return *foreground* or the closest blend towards white/ink meeting *target*.

    Raises ``ValueError`` when no blend can reach the target (target > 21).
    """
    if target > 21.0:
        raise ValueError("contrast target %.2f is impossible (max 21)" % target)
    fg: RGB = (int(foreground[0]), int(foreground[1]), int(foreground[2]))
    if contrast_ratio(fg, background) + 1e-9 >= target:
        return fg
    best: Optional[Tuple[float, RGB]] = None
    for reference in candidates:
        for step in range(1, 65):
            mixed = mix(fg, reference, step / 64.0)
            if contrast_ratio(mixed, background) + 1e-9 >= target:
                distance = color_distance(fg, mixed)
                if best is None or distance < best[0]:
                    best = (distance, mixed)
                break
    if best is None:
        raise ValueError("cannot reach contrast %.2f on %r" % (target, tuple(background)))
    return best[1]


def attention_contrast(
    foreground: Sequence[int],
    background: Sequence[int],
    target: float = BODY_CONTRAST,
) -> Tuple[RGB, float]:
    """Best-contrast variant of *foreground* plus its measured ratio."""
    color = ensure_contrast(foreground, background, target)
    return color, contrast_ratio(color, background)


# ---------------------------------------------------------------------------
# Themes (dark ink + accent per niche)
# ---------------------------------------------------------------------------

NICHE_ACCENTS: Dict[str, str] = {
    "travel": "#FF7A45",
    "crypto": "#F0B90B",
    "ai": "#4C9AFF",
    "sports": "#2ECC71",
    "default": "#4F8CFF",
}

NICHE_GRADIENTS: Dict[str, Tuple[str, str, str]] = {
    "travel": ("#06201F", "#0B3B33", "#071A22"),
    "crypto": ("#1A1405", "#2A1E06", "#120D04"),
    "ai": ("#080F1F", "#122A4A", "#0A1424"),
    "sports": ("#07170F", "#0E3322", "#08190F"),
    "default": ("#0B1220", "#16233C", "#0D1626"),
}

#: Multi-stop gradient positions used by :func:`gradient_stops`.
GRADIENT_POSITIONS: Tuple[float, float, float] = (0.0, 0.55, 1.0)


@dataclass(frozen=True)
class Theme:
    """Per-niche colour + gradient palette with pre-validated text colours."""

    niche: str
    accent: RGB
    accent_hex: str
    gradient: Tuple[RGB, RGB, RGB]
    ink: RGB = INK
    cream: RGB = CREAM
    muted: RGB = MUTED
    paper: RGB = WHITE
    headline: RGB = CREAM
    subtitle: RGB = CREAM
    body: RGB = CREAM
    #: Text colour for filled accent surfaces (CTA pill, brand monogram).
    cta_text: RGB = INK
    #: Accent adjusted so it is legible as 24px text on the ink footer band.
    accent_text: RGB = CREAM

    @property
    def accent_on_ink_contrast(self) -> float:
        return contrast_ratio(self.accent_text, self.ink)

    @property
    def cta_contrast(self) -> float:
        return contrast_ratio(self.cta_text, self.accent)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "niche": self.niche,
            "accent": self.accent_hex,
            "gradient": [rgb_to_hex(stop) for stop in self.gradient],
            "ink": rgb_to_hex(self.ink),
            "cream": rgb_to_hex(self.cream),
            "headline": rgb_to_hex(self.headline),
            "cta_text": rgb_to_hex(self.cta_text),
            "accent_text": rgb_to_hex(self.accent_text),
            "cta_contrast": round(self.cta_contrast, 2),
        }


def theme_for(
    niche: str = "",
    accent: str = "",
    background: str = "",
) -> Theme:
    """Build a :class:`Theme` for *niche* with optional accent/background overrides."""
    key = str(niche or "").strip().lower()
    if key not in NICHE_ACCENTS:
        key = "default"
    accent_rgb = hex_to_rgb(accent, hex_to_rgb(NICHE_ACCENTS[key]))
    stops = NICHE_GRADIENTS[key]
    if background:
        base = hex_to_rgb(background, hex_to_rgb(stops[1]))
        gradient = (mix(INK, base, 0.55), base, mix(base, INK, 0.45))
    else:
        gradient = tuple(hex_to_rgb(stop) for stop in stops)  # type: ignore[assignment]
    cta_text = best_text_color(accent_rgb, (INK, WHITE))
    accent_text = ensure_contrast(accent_rgb, INK, BODY_CONTRAST)
    return Theme(
        niche=key,
        accent=accent_rgb,
        accent_hex=rgb_to_hex(accent_rgb),
        gradient=gradient,  # type: ignore[arg-type]
        cta_text=cta_text,
        accent_text=accent_text,
    )


def gradient_stops(theme: Theme) -> Tuple[Tuple[float, RGB], ...]:
    """Multi-stop gradient keyframes for a theme."""
    return tuple(zip(GRADIENT_POSITIONS, theme.gradient))


def gradient_color_at(stops: Sequence[Tuple[float, RGB]], position: float) -> RGB:
    """Colour of a multi-stop gradient at ``position`` (0..1)."""
    t = max(0.0, min(1.0, float(position)))
    if not stops:
        return INK
    if t <= stops[0][0]:
        return tuple(stops[0][1])  # type: ignore[return-value]
    if t >= stops[-1][0]:
        return tuple(stops[-1][1])  # type: ignore[return-value]
    for index in range(1, len(stops)):
        left_pos, left_color = stops[index - 1]
        right_pos, right_color = stops[index]
        if t <= right_pos:
            span = max(1e-9, right_pos - left_pos)
            local = (t - left_pos) / span
            return (
                _clamp_channel(left_color[0] + (right_color[0] - left_color[0]) * local),
                _clamp_channel(left_color[1] + (right_color[1] - left_color[1]) * local),
                _clamp_channel(left_color[2] + (right_color[2] - left_color[2]) * local),
            )
    return tuple(stops[-1][1])  # type: ignore[return-value]


def interpolate_gradient(stops: Sequence[Tuple[float, RGB]], tile: int = 256) -> List[RGB]:
    """Pre-compute a vertical gradient tile of *tile* rows (pure helper)."""
    if tile <= 0:
        raise ValueError("tile must be positive")
    return [gradient_color_at(stops, index / max(1, tile - 1)) for index in range(tile)]


def scrim_alpha_at(position: float) -> float:
    """Alpha of the photo contrast scrim at vertical *position* (0..1).

    The top of the pin (headline zone) is darkened strongly, it fades in the
    middle so the photo stays visible and rises again towards the bottom band.
    """
    t = max(0.0, min(1.0, float(position)))
    if t <= 0.05:
        return 0.88
    if t <= 0.42:
        return 0.88 - (t - 0.05) / 0.37 * 0.16       # 0.88 -> 0.72
    if t <= 0.62:
        return 0.72 - (t - 0.42) / 0.20 * 0.20       # 0.72 -> 0.52
    return 0.52 + (t - 0.62) / 0.38 * 0.18           # 0.52 -> 0.70


def scrim_color_at(position: float, ink: RGB = INK) -> RGB:
    """Ink composited over white at the scrim alpha (worst case for light text)."""
    return composite_over(ink, WHITE, scrim_alpha_at(position))


# ---------------------------------------------------------------------------
# Cover-crop math
# ---------------------------------------------------------------------------


def cover_box(source_width: int, source_height: int, target_width: int, target_height: int) -> Tuple[int, int, int, int]:
    """Crop box (left, top, right, bottom) that covers target at source scale."""
    if source_width <= 0 or source_height <= 0:
        raise ValueError("source image has zero size")
    if target_width <= 0 or target_height <= 0:
        raise ValueError("target size must be positive")
    scale = max(target_width / source_width, target_height / source_height)
    scaled_width = max(target_width, int(round(source_width * scale)))
    scaled_height = max(target_height, int(round(source_height * scale)))
    left = (scaled_width - target_width) // 2
    top = (scaled_height - target_height) // 2
    return (left, top, left + target_width, top + target_height)


# ---------------------------------------------------------------------------
# Text measuring / wrapping / auto-fit (pure)
# ---------------------------------------------------------------------------


class TextMeasurer:
    """Protocol-style interface: measure text width in pixels."""

    def measure(self, text: str, size: int, family: str = "sans") -> float:  # pragma: no cover
        raise NotImplementedError


class ApproxMeasurer(TextMeasurer):
    """Cheap approximate measurer (no Pillow) used when no font is available.

    Conservative factors calibrated against Inter (~0.50) and Playfair
    uppercase (~0.585), so layouts built with it do not under-estimate widths.
    """

    FACTORS = {"sans": 0.54, "display": 0.60}

    def __init__(self, factors: Optional[Mapping[str, float]] = None) -> None:
        self.factors = dict(self.FACTORS)
        if factors:
            self.factors.update({str(k): float(v) for k, v in factors.items()})

    def measure(self, text: str, size: int, family: str = "sans") -> float:
        factor = self.factors.get(family, self.factors["sans"])
        return len(str(text)) * int(size) * factor


class PILTextMeasurer(TextMeasurer):
    """Pillow-backed measurer (lazy import; fonts cached)."""

    def __init__(self, font_dir: Optional[Path | str] = None) -> None:
        from PIL import Image, ImageDraw, ImageFont  # noqa: F401  (lazy)

        self.font_dir = Path(font_dir) if font_dir else FONT_DIR
        self._fonts: Dict[Tuple[str, int], Any] = {}
        self._draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    def font(self, family: str = "sans", size: int = 24):
        from PIL import ImageFont

        key = (family, int(size))
        if key not in self._fonts:
            file_name = FONT_FILES.get(family, FONT_FILES["sans"])
            path = self.font_dir / file_name
            if not path.exists():
                raise FileNotFoundError(
                    "font %s not found in %s (expected %s)" % (file_name, self.font_dir, path)
                )
            self._fonts[key] = ImageFont.truetype(str(path), int(size))
        return self._fonts[key]

    def measure(self, text: str, size: int, family: str = "sans") -> float:
        return float(self._draw.textlength(str(text), font=self.font(family, size)))


def normalize_text(value: Any) -> str:
    """Collapse whitespace and strip control characters."""
    text = str(value or "").replace("\r", " ").replace("\t", " ")
    return re.sub(r"[ ]{2,}", " ", text).strip()


def wrap_text(
    text: str,
    measure: TextMeasurer,
    size: int,
    max_width: int,
    family: str = "sans",
) -> List[str]:
    """Greedy word-wrap; honours explicit ``\\n`` breaks; raises on long words."""
    lines: List[str] = []
    for paragraph in str(text or "").split("\n"):
        words = paragraph.split()
        if not words:
            continue
        current = ""
        for word in words:
            candidate = word if not current else current + " " + word
            if measure.measure(candidate, size, family) <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            if measure.measure(word, size, family) > max_width:
                raise TextOverflowError(
                    "word %r is wider than %dpx at %dpx" % (word, max_width, size)
                )
            current = word
        if current:
            lines.append(current)
    return lines


def truncate_to_width(
    text: str,
    measure: TextMeasurer,
    size: int,
    max_width: int,
    family: str = "sans",
    ellipsis: str = "\u2026",
) -> str:
    """Trim *text* (word-aware) so it fits *max_width*, appending an ellipsis."""
    value = normalize_text(text)
    if not value:
        return ""
    if measure.measure(value, size, family) <= max_width:
        return value
    if measure.measure(ellipsis, size, family) > max_width:
        return ""
    words = value.split(" ")
    kept = ""
    for word in words:
        candidate = word if not kept else kept + " " + word
        if measure.measure(candidate + ellipsis, size, family) <= max_width:
            kept = candidate
        else:
            break
    if kept:
        return kept + ellipsis
    # Fall back to character trimming for a single huge word.
    trimmed = ""
    for char in value:
        if measure.measure(trimmed + char + ellipsis, size, family) <= max_width:
            trimmed += char
        else:
            break
    return (trimmed + ellipsis) if trimmed else ""


@dataclass(frozen=True)
class TextFit:
    """Result of :func:`fit_text`: font size, wrapped lines and geometry."""

    text: str
    size: int
    lines: Tuple[str, ...]
    line_height: int
    width: int
    height: int
    family: str = "sans"
    line_height_ratio: float = 1.32
    truncated: bool = False

    @property
    def line_count(self) -> int:
        return len(self.lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "lines": list(self.lines),
            "size": self.size,
            "line_height": self.line_height,
            "width": self.width,
            "height": self.height,
            "truncated": self.truncated,
        }


def _unique_sizes(sizes: Iterable[int], min_size: int = MIN_FONT_SIZE) -> List[int]:
    wanted = sorted({int(size) for size in sizes if int(size) > 0}, reverse=True)
    return [size for size in wanted if size >= min_size] or [int(min_size)]


def fit_text(
    text: str,
    measure: TextMeasurer,
    *,
    max_width: int,
    sizes: Iterable[int],
    max_lines: int,
    line_height_ratio: float = 1.32,
    family: str = "sans",
    min_size: int = MIN_FONT_SIZE,
    truncate: bool = False,
) -> TextFit:
    """Largest font size whose wrapped text fits *max_width* and *max_lines*.

    Raises :class:`TextOverflowError` when not even the smallest size fits (use
    ``truncate=True`` to ellipsize the last line instead).
    """
    value = normalize_text(text)
    if not value:
        return TextFit("", int(min_size), (), int(round(min_size * line_height_ratio)), 0, 0, family, line_height_ratio)
    last: Optional[Tuple[int, List[str], int]] = None
    for size in _unique_sizes(sizes, min_size):
        try:
            lines = wrap_text(value, measure, size, max_width, family)
        except TextOverflowError:
            continue
        widths = [measure.measure(line, size, family) for line in lines]
        if not lines:
            continue
        last = (size, lines, max(widths) if widths else 0)
        if len(lines) <= max_lines:
            return TextFit(
                text=value,
                size=size,
                lines=tuple(lines),
                line_height=int(round(size * line_height_ratio)),
                width=int(math.ceil(max(widths))),
                height=int(round(size * line_height_ratio)) * len(lines),
                family=family,
                line_height_ratio=line_height_ratio,
            )
    if truncate and last is not None:
        size, lines, width = last
        kept = lines[:max_lines]
        if len(lines) > max_lines:
            remainder = " ".join(lines[max_lines:])
            extension = (remainder.split()[0] + " ") if remainder else ""
            kept[-1] = truncate_to_width(kept[-1] + " " + extension, measure, size, max_width, family)
        return TextFit(
            text=value,
            size=size,
            lines=tuple(kept),
            line_height=int(round(size * line_height_ratio)),
            width=int(math.ceil(max(measure.measure(line, size, family) for line in kept))),
            height=int(round(size * line_height_ratio)) * len(kept),
            family=family,
            line_height_ratio=line_height_ratio,
            truncated=bool(len(lines) > max_lines),
        )
    raise TextOverflowError(
        "cannot fit %r into %d lines of %dpx (smallest %dpx)"
        % (value[:60], max_lines, max_width, min_size)
    )


def fit_single_line(
    text: str,
    measure: TextMeasurer,
    *,
    max_width: int,
    sizes: Iterable[int],
    family: str = "sans",
    min_size: int = MIN_FONT_SIZE,
    line_height_ratio: float = 1.3,
) -> TextFit:
    """Fit one line, shrinking then ellipsizing (never raises for long text)."""
    value = normalize_text(text)
    for size in _unique_sizes(sizes, min_size):
        if measure.measure(value, size, family) <= max_width:
            return TextFit(value, size, (value,), int(round(size * line_height_ratio)),
                           int(math.ceil(measure.measure(value, size, family))),
                           int(round(size * line_height_ratio)), family, line_height_ratio)
    size = _unique_sizes(sizes, min_size)[-1]
    truncated = truncate_to_width(value, measure, size, max_width, family)
    return TextFit(value, size, (truncated,), int(round(size * line_height_ratio)),
                   int(math.ceil(measure.measure(truncated, size, family))),
                   int(round(size * line_height_ratio)), family, line_height_ratio,
                   truncated=truncated != value)


def letterspaced_width(text: str, measure: TextMeasurer, size: int, tracking: int, family: str = "sans") -> int:
    value = normalize_text(text)
    if not value:
        return 0
    return int(math.ceil(measure.measure(value, size, family) + max(0, tracking) * (len(value) - 1)))


# ---------------------------------------------------------------------------
# Design tokens & type scale
# ---------------------------------------------------------------------------

HEADLINE_SIZES: Tuple[int, ...] = (136, 128, 120, 112, 104, 96, 88, 80, 72, 64)
#: Last-resort sizes (used only when the recommended scale cannot fit); the
#: engine records a warning so unusually small headlines get caught in review.
FALLBACK_HEADLINE_SIZES: Tuple[int, ...] = (56, 48, 40, 32, 24)
SUBTITLE_SIZES: Tuple[int, ...] = (44, 42, 40, 38, 36, 34, 32)
BULLET_SIZES: Tuple[int, ...] = (34, 32, 30, 28, 26)
CTA_SIZES: Tuple[int, ...] = (38, 36, 34, 32, 30, 28, 26)
FOOTER_SIZES: Tuple[int, ...] = (26, 24)

TYPE_SCALE: Dict[str, int] = {
    "display": 136,
    "headline": 112,
    "subtitle": 44,
    "body": 34,
    "caption": 26,
    "micro": 24,
    "cta": 36,
    "tag": 24,
    "brand": 24,
}


@dataclass(frozen=True)
class DesignTokens:
    """Spacing / shape / type tokens for the 1000x1500 Pinterest pin."""

    width: int = PIN_SIZE[0]
    height: int = PIN_SIZE[1]
    margin: int = SAFE_MARGIN
    min_margin: int = MIN_SAFE_MARGIN
    min_font_size: int = MIN_FONT_SIZE
    radius_card: int = 28
    radius_pill: int = 40
    radius_small: int = 14
    radius_qr: int = 18
    header_height: int = 48
    brand_mark: int = 46
    brand_gap: int = 12
    accent_rule_width: int = 148
    accent_rule_height: int = 10
    cta_height: int = 76
    cta_pad_x: int = 36
    footer_height: int = 140
    footer_height_qr: int = 196
    footer_pad: int = 22
    card_pad_x: int = 26
    card_pad_y: int = 16
    card_gap: int = 14
    card_icon: int = 30
    icon_gap: int = 16
    qr_card: int = 172
    qr_inset: int = 8
    shadow_offset: int = 6
    shadow_alpha: int = 56
    max_content_offset: int = 180
    #: gaps: header->headline, headline->rule, rule->subtitle,
    #: subtitle->bullets, CTA->footer, minimum content->CTA.
    gaps: Tuple[int, int, int, int, int, int] = (40, 28, 24, 32, 28, 24)


DESIGN = DesignTokens()


# ---------------------------------------------------------------------------
# Layout primitives
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def center_x(self) -> int:
        return self.x + self.w // 2

    @property
    def center_y(self) -> int:
        return self.y + self.h // 2

    def expanded(self, pad: int) -> "Rect":
        return Rect(self.x - pad, self.y - pad, self.w + 2 * pad, self.h + 2 * pad)

    def intersects(self, other: "Rect") -> bool:
        return (
            self.x < other.right
            and other.x < self.right
            and self.y < other.bottom
            and other.y < self.bottom
        )

    def contains(self, other: "Rect") -> bool:
        return (
            self.x <= other.x
            and self.y <= other.y
            and self.right >= other.right
            and self.bottom >= other.bottom
        )

    def to_dict(self) -> Dict[str, int]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


@dataclass(frozen=True)
class TextBlock:
    role: str
    rect: Rect
    text: str
    lines: Tuple[str, ...]
    font_size: int
    line_height: int
    family: str
    color: RGB
    target_contrast: float = BODY_CONTRAST
    align: str = "left"
    line_width: int = 0

    @property
    def line_count(self) -> int:
        return len(self.lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "rect": self.rect.to_dict(),
            "lines": list(self.lines),
            "font_size": self.font_size,
            "line_height": self.line_height,
            "color": rgb_to_hex(self.color),
            "target_contrast": self.target_contrast,
            "align": self.align,
            "line_width": self.line_width,
        }


@dataclass(frozen=True)
class PillBlock:
    rect: Rect
    text: str
    font_size: int
    line_height: int
    fill: RGB
    text_color: RGB
    border_color: RGB
    border_width: int = 2
    radius: int = 40
    tracking: int = 0
    align: str = "center"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rect": self.rect.to_dict(),
            "text": self.text,
            "font_size": self.font_size,
            "fill": rgb_to_hex(self.fill),
            "text_color": rgb_to_hex(self.text_color),
            "border_color": rgb_to_hex(self.border_color),
        }


@dataclass(frozen=True)
class ButtonBlock:
    rect: Rect
    label: str
    font_size: int
    line_height: int
    fill: RGB
    text_color: RGB
    border_color: Optional[RGB] = None
    radius: int = 40
    target_contrast: float = BODY_CONTRAST

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rect": self.rect.to_dict(),
            "label": self.label,
            "font_size": self.font_size,
            "line_height": self.line_height,
            "fill": rgb_to_hex(self.fill),
            "text_color": rgb_to_hex(self.text_color),
            "target_contrast": self.target_contrast,
        }


@dataclass(frozen=True)
class CardBlock:
    rect: Rect
    text: TextBlock
    icon: Rect
    fill: RGB
    border_color: RGB
    radius: int = 28

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rect": self.rect.to_dict(),
            "icon": self.icon.to_dict(),
            "text": self.text.to_dict(),
            "fill": rgb_to_hex(self.fill),
            "border_color": rgb_to_hex(self.border_color),
        }


@dataclass(frozen=True)
class BrandMark:
    monogram_rect: Rect
    monogram_text: str
    monogram_font_size: int
    wordmark: Optional[TextBlock]
    fill: RGB
    text_color: RGB
    tracking: int = 0

    @property
    def rect(self) -> Rect:
        if self.wordmark is not None:
            return Rect(
                self.monogram_rect.x,
                min(self.monogram_rect.y, self.wordmark.rect.y),
                self.wordmark.rect.right - self.monogram_rect.x,
                max(self.monogram_rect.bottom, self.wordmark.rect.bottom)
                - min(self.monogram_rect.y, self.wordmark.rect.y),
            )
        return self.monogram_rect

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rect": self.rect.to_dict(),
            "monogram": self.monogram_text,
            "wordmark": self.wordmark.lines[0] if self.wordmark is not None and self.wordmark.lines else "",
        }


@dataclass(frozen=True)
class HeaderRow:
    rect: Rect
    tag: Optional[PillBlock]
    brand: BrandMark

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rect": self.rect.to_dict(),
            "tag": self.tag.to_dict() if self.tag else None,
            "brand": self.brand.to_dict(),
        }


@dataclass(frozen=True)
class FooterBlock:
    rect: Rect
    texts: Tuple[TextBlock, ...]
    qr_rect: Optional[Rect]
    fill: RGB
    border_color: RGB
    radius: int = 28
    inner_pad: int = 22

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rect": self.rect.to_dict(),
            "texts": [block.to_dict() for block in self.texts],
            "qr_rect": self.qr_rect.to_dict() if self.qr_rect else None,
            "fill": rgb_to_hex(self.fill),
            "border_color": rgb_to_hex(self.border_color),
        }


# ---------------------------------------------------------------------------
# Pin content spec (pure)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PinContent:
    """Everything needed to render one pin + its Pinterest payload."""

    niche: str = "travel"
    headline: str = ""
    subtitle: str = ""
    bullets: Tuple[str, ...] = ()
    cta: str = "Read more"
    link: str = ""
    disclosure: str = ""
    attribution: str = ""
    site: str = DEFAULT_SITE
    tag: str = ""
    image_prompt: str = ""
    title: str = ""
    description: str = ""
    alt_text: str = ""
    style: int = 0
    accent: str = ""
    background: str = ""

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "PinContent":
        def text(key: str, default: str = "") -> str:
            value = mapping.get(key)
            return default if value is None else str(value)

        raw_bullets = mapping.get("bullets") or ()
        if isinstance(raw_bullets, str):
            raw_bullets = (raw_bullets,)
        return cls(
            niche=text("niche", "travel") or "travel",
            headline=text("headline"),
            subtitle=text("subtitle"),
            bullets=tuple(str(item) for item in raw_bullets if str(item).strip()),
            cta=text("cta", "Read more") or "Read more",
            link=text("link"),
            disclosure=text("disclosure"),
            attribution=text("attribution"),
            site=text("site", DEFAULT_SITE) or DEFAULT_SITE,
            tag=text("tag"),
            image_prompt=text("image_prompt"),
            title=text("title"),
            description=text("description"),
            alt_text=text("alt_text"),
            style=int(mapping.get("style") or 0),
            accent=text("accent"),
            background=text("background"),
        )

    @classmethod
    def from_object(cls, obj: Any) -> "PinContent":
        """Adapt ``content_factory.integrations.pins.PinSpec``-like objects."""
        if isinstance(obj, PinContent):
            return obj
        if isinstance(obj, Mapping):
            return cls.from_mapping(obj)
        data: Dict[str, Any] = {}
        for attribute in (
            "niche", "headline", "subtitle", "bullets", "cta", "link", "disclosure",
            "attribution", "site", "tag", "image_prompt", "title", "description",
            "alt_text", "style", "accent", "background",
        ):
            if hasattr(obj, attribute):
                data[attribute] = getattr(obj, attribute)
        return cls.from_mapping(data)

    @property
    def clean_headline(self) -> str:
        return normalize_text(self.headline) or normalize_text(self.title) or "Pinterest pin"

    @property
    def clean_cta(self) -> str:
        return normalize_text(self.cta) or "Read more"

    @property
    def clean_disclosure(self) -> str:
        disclosure = normalize_text(self.disclosure)
        if disclosure:
            return disclosure
        return DISCLOSURE_AFFILIATE if normalize_text(self.link) else DISCLOSURE_GUIDE


# ---------------------------------------------------------------------------
# Layout engine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PinLayout:
    """Overflow-safe placement of every pin element (produced without PIL)."""

    content: PinContent
    size: Tuple[int, int]
    theme: Theme
    variant: str
    margin: int
    scale: float
    header: HeaderRow
    headline: TextBlock
    accent_rule: Rect
    subtitle: Optional[TextBlock]
    bullets: Tuple[CardBlock, ...]
    cta: ButtonBlock
    footer: FooterBlock
    qr: Optional[Rect]
    dropped: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()

    # -- derived ----------------------------------------------------------
    @property
    def width(self) -> int:
        return int(self.size[0])

    @property
    def height(self) -> int:
        return int(self.size[1])

    @property
    def aspect_ratio(self) -> float:
        return self.width / float(self.height)

    def text_blocks(self) -> List[TextBlock]:
        blocks: List[TextBlock] = [self.headline]
        if self.subtitle is not None:
            blocks.append(self.subtitle)
        for card in self.bullets:
            blocks.append(card.text)
        blocks.extend(self.footer.texts)
        if self.header.brand.wordmark is not None:
            blocks.append(self.header.brand.wordmark)
        return blocks

    def font_sizes(self) -> List[int]:
        sizes = [self.headline.font_size, self.cta.font_size, self.footer.texts[0].font_size]
        if self.subtitle is not None:
            sizes.append(self.subtitle.font_size)
        sizes.extend(card.text.font_size for card in self.bullets)
        sizes.extend(block.font_size for block in self.footer.texts)
        if self.header.tag is not None:
            sizes.append(self.header.tag.font_size)
        if self.header.brand.wordmark is not None:
            sizes.append(self.header.brand.wordmark.font_size)
        sizes.append(self.header.brand.monogram_font_size)
        return sizes

    @property
    def min_font_size(self) -> int:
        return min(self.font_sizes())

    def top_level_rects(self) -> List[Tuple[str, Rect]]:
        rects: List[Tuple[str, Rect]] = [
            ("headline", self.headline.rect),
            ("accent_rule", self.accent_rule),
            ("cta", self.cta.rect),
            ("footer", self.footer.rect),
            ("header", self.header.rect),
        ]
        if self.subtitle is not None:
            rects.append(("subtitle", self.subtitle.rect))
        rects.extend(("bullet_%d" % index, card.rect) for index, card in enumerate(self.bullets, start=1))
        return rects

    # -- validation -------------------------------------------------------
    def validate(self) -> List[str]:
        """Return a list of layout quality violations (empty == valid)."""
        errors: List[str] = []
        width, height = self.width, self.height
        margin = self.margin
        if margin < MIN_SAFE_MARGIN:
            errors.append("safe margin %d < %d" % (margin, MIN_SAFE_MARGIN))
        if self.min_font_size < MIN_FONT_SIZE:
            errors.append("min font %d < %d" % (self.min_font_size, MIN_FONT_SIZE))
        for name, rect in self.top_level_rects():
            if rect.x < margin or rect.y < margin or rect.right > width - margin or rect.bottom > height - margin:
                errors.append("%s out of safe area: %r" % (name, rect))
            if rect.w <= 0 or rect.h <= 0:
                errors.append("%s has empty rect: %r" % (name, rect))
        rects = self.top_level_rects()
        for index, (name_a, rect_a) in enumerate(rects):
            for name_b, rect_b in rects[index + 1:]:
                if rect_a.intersects(rect_b):
                    errors.append("%s overlaps %s" % (name_a, name_b))
        if not self.headline.lines:
            errors.append("headline is empty")
        if len(self.headline.lines) > HEADLINE_MAX_LINES:
            errors.append("headline has %d lines > %d" % (len(self.headline.lines), HEADLINE_MAX_LINES))
        for block in self.text_blocks():
            if block.rect.w <= 0 or block.rect.h <= 0:
                errors.append("text block %s has empty rect" % block.role)
                continue
            self_width = block.line_width or max(
                (self._line_width(block, line) for line in block.lines), default=0
            )
            if self_width > block.rect.w + 1:
                errors.append(
                    "text %r overflows its box (%dpx > %dpx)" % (block.role, self_width, block.rect.w)
                )
        if not self.cta.label.strip():
            errors.append("CTA label is empty")
        if contrast_ratio(self.cta.text_color, self.cta.fill) + 1e-9 < self.cta.target_contrast:
            errors.append(
                "CTA contrast %.2f < %.2f" % (contrast_ratio(self.cta.text_color, self.cta.fill), self.cta.target_contrast)
            )
        if not any(block.role == "disclosure" for block in self.footer.texts):
            errors.append("footer disclosure is missing")
        for block in self.footer.texts:
            if contrast_ratio(block.color, self.footer.fill) + 1e-9 < BODY_CONTRAST:
                errors.append(
                    "footer %r contrast %.2f < %.2f"
                    % (block.role, contrast_ratio(block.color, self.footer.fill), BODY_CONTRAST)
                )
        if self.header.tag is not None:
            tag_rect = self.header.tag.rect
            if tag_rect.x < margin or tag_rect.y < margin or tag_rect.right > width - margin or tag_rect.bottom > height - margin:
                errors.append("tag pill out of safe area: %r" % tag_rect)
            if tag_rect.intersects(self.header.brand.rect):
                errors.append("tag pill overlaps brand mark")
            if contrast_ratio(self.header.tag.text_color, self.header.tag.fill) + 1e-9 < BODY_CONTRAST:
                errors.append("tag pill contrast too low")
        if self.header.brand.wordmark is not None:
            if self.header.brand.wordmark.rect.h <= 0:
                errors.append("brand wordmark has empty rect")
        if self.cta.rect.bottom > self.footer.rect.y:
            errors.append("CTA overlaps footer")
        if self.bullets:
            lowest = max(card.rect.bottom for card in self.bullets)
            if lowest > self.cta.rect.y:
                errors.append("bullets overlap CTA")
        if self.qr is not None and not self.footer.rect.contains(self.qr):
            errors.append("QR is outside the footer band")
        if self.variant != "photo":
            stops = gradient_stops(self.theme)
            for position, stop in stops:
                if contrast_ratio(self.headline.color, stop) + 1e-9 < HEADING_CONTRAST:
                    errors.append("headline contrast %.2f on gradient stop %.2f" % (contrast_ratio(self.headline.color, stop), position))
                for block in self.text_blocks():
                    if block.role == "headline":
                        continue
                    if contrast_ratio(block.color, stop) + 1e-9 < BODY_CONTRAST and block.role not in ("disclosure",):
                        # Footer/tag text sits on solid fills, only top text is directly on the gradient.
                        if block.rect.y < self.footer.rect.y:
                            errors.append(
                                "%s contrast %.2f on gradient stop %.2f"
                                % (block.role, contrast_ratio(block.color, stop), position)
                            )
        return errors

    @staticmethod
    def _line_width(block: TextBlock, line: str) -> int:
        # Pure fallback: approximate width with the block's font size.  The
        # renderer replaces this with real measured widths in PinMetrics.
        return int(math.ceil(len(line) * block.font_size * 0.60))

    def assert_valid(self) -> "PinLayout":
        errors = self.validate()
        if errors:
            raise QualityError("invalid pin layout:\n- " + "\n- ".join(errors))
        return self

    @property
    def content_bottom(self) -> int:
        bottoms = [self.headline.rect.bottom, self.accent_rule.bottom, self.cta.rect.y]
        if self.subtitle is not None:
            bottoms.append(self.subtitle.rect.bottom)
        bottoms.extend(card.rect.bottom for card in self.bullets)
        return max(bottoms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "size": [self.width, self.height],
            "aspect_ratio": round(self.aspect_ratio, 4),
            "variant": self.variant,
            "margin": self.margin,
            "scale": round(self.scale, 3),
            "min_font_size": self.min_font_size,
            "theme": self.theme.to_dict(),
            "header": self.header.to_dict(),
            "headline": self.headline.to_dict(),
            "accent_rule": self.accent_rule.to_dict(),
            "subtitle": self.subtitle.to_dict() if self.subtitle else None,
            "bullets": [card.to_dict() for card in self.bullets],
            "cta": self.cta.to_dict(),
            "footer": self.footer.to_dict(),
            "qr": self.qr.to_dict() if self.qr else None,
            "dropped": list(self.dropped),
            "warnings": list(self.warnings),
            "content": {
                "niche": self.content.niche,
                "headline": self.content.headline,
                "subtitle": self.content.subtitle,
                "cta": self.content.cta,
                "disclosure": self.content.disclosure,
            },
        }


def _fit_descending(
    text: str,
    measure: TextMeasurer,
    sizes: Sequence[int],
    *,
    max_width: int,
    max_lines: int,
    ratio: float,
    family: str,
    min_size: int,
    truncate: bool = False,
) -> List[TextFit]:
    """All valid fits for *text*, biggest font size first."""
    fits: List[TextFit] = []
    for size in _unique_sizes(sizes, min_size):
        try:
            fit = fit_text(
                text,
                measure,
                max_width=max_width,
                sizes=(size,),
                max_lines=max_lines,
                line_height_ratio=ratio,
                family=family,
                min_size=min_size,
                truncate=truncate,
            )
        except TextOverflowError:
            continue
        fits.append(fit)
    return fits


def _shift_rect(rect: Rect, dy: int) -> Rect:
    return Rect(rect.x, rect.y + int(dy), rect.w, rect.h)


def layout_pin(
    content: PinContent | Mapping[str, Any] | Any,
    *,
    size: Tuple[int, int] = PIN_SIZE,
    theme: Optional[Theme] = None,
    measure: Optional[TextMeasurer] = None,
    variant: str = "gradient",
    qr: bool = False,
    tokens: DesignTokens = DESIGN,
) -> PinLayout:
    """Build an overflow-safe :class:`PinLayout` for *content*.

    The engine first tries the largest headline that fits in <= 2 lines (then
    <= 3 lines), then progressively reduces inter-block gaps, subtitle size,
    the number of bullet cards and finally the headline size.  When nothing
    fits it raises :class:`LayoutOverflowError` instead of clipping text.
    """
    spec = PinContent.from_object(content)
    measurer = measure or ApproxMeasurer()
    chosen_theme = theme or theme_for(spec.niche, accent=spec.accent, background=spec.background)
    width, height = int(size[0]), int(size[1])
    if width <= 0 or height <= 0:
        raise ValueError("pin size must be positive")
    scale = min(width / float(PIN_SIZE[0]), height / float(PIN_SIZE[1]))

    def px(value: float) -> int:
        return max(1, int(round(float(value) * scale)))

    def fs(value: float) -> int:
        return max(MIN_FONT_SIZE, int(round(float(value) * scale)))

    margin = max(MIN_SAFE_MARGIN, px(tokens.margin))
    if width <= 2 * margin or height <= 2 * margin:
        raise LayoutOverflowError(
            "canvas %dx%d leaves no room inside a %dpx safe margin" % (width, height, margin)
        )
    x0, x1 = margin, width - margin
    content_w = x1 - x0
    warnings: List[str] = []

    # ---- header: tag pill (left) + brand mark (right) --------------------
    header_h = px(tokens.header_height)
    mono_size = px(tokens.brand_mark)
    mono_font = fs(TYPE_SCALE["brand"])
    wordmark_tracking = px(2)
    wordmark_text = normalize_text("Content Factory").upper()
    wordmark_size = fs(TYPE_SCALE["brand"])
    wordmark_width = letterspaced_width(wordmark_text, measurer, wordmark_size, wordmark_tracking)
    brand_width = mono_size
    wordmark: Optional[TextBlock] = None
    if wordmark_width + mono_size + px(tokens.brand_gap) <= content_w // 2:
        brand_width = mono_size + px(tokens.brand_gap) + wordmark_width
    else:
        wordmark_text = ""
        warnings.append("brand wordmark hidden: header too narrow")
    brand_x = x1 - brand_width
    mono_rect = Rect(brand_x, margin + (header_h - mono_size) // 2, mono_size, mono_size)
    if wordmark_text:
        wordmark_rect = Rect(
            mono_rect.right + px(tokens.brand_gap),
            int(margin + (header_h - wordmark_size * 1.3) // 2),
            int(wordmark_width),
            int(round(wordmark_size * 1.3)),
        )
        wordmark = TextBlock(
            role="brandmark",
            rect=wordmark_rect,
            text=wordmark_text,
            lines=(wordmark_text,),
            font_size=wordmark_size,
            line_height=int(round(wordmark_size * 1.3)),
            family="sans",
            color=chosen_theme.cream,
            target_contrast=BODY_CONTRAST,
            line_width=wordmark_width,
        )
    brand = BrandMark(
        monogram_rect=mono_rect,
        monogram_text="CF",
        monogram_font_size=mono_font,
        wordmark=wordmark,
        fill=chosen_theme.accent,
        text_color=chosen_theme.cta_text,
        tracking=wordmark_tracking,
    )
    tag_text = normalize_text(spec.tag).upper() or normalize_text(spec.niche).upper()
    tag: Optional[PillBlock] = None
    if tag_text:
        tag_size = fs(TYPE_SCALE["tag"])
        tag_pad_x = px(22)
        max_pill_w = content_w - brand_width - px(16)
        if max_pill_w >= px(150):
            fitted = fit_single_line(
                tag_text, measurer, max_width=max_pill_w - 2 * tag_pad_x,
                sizes=(tag_size,), min_size=MIN_FONT_SIZE, line_height_ratio=1.3,
            )
            pill_w = min(max_pill_w, int(fitted.width) + 2 * tag_pad_x)
            pill_h = px(tokens.header_height)
            tag = PillBlock(
                rect=Rect(x0, margin + (header_h - pill_h) // 2, pill_w, pill_h),
                text=fitted.lines[0],
                font_size=fitted.size,
                line_height=fitted.line_height,
                fill=chosen_theme.ink,
                text_color=chosen_theme.cream,
                border_color=chosen_theme.accent,
                border_width=max(1, px(2)),
                radius=pill_h // 2,
                tracking=px(1),
            )
        else:
            warnings.append("keyword tag hidden: header too narrow")
    header_rect = Rect(x0, margin, content_w, header_h)
    header = HeaderRow(rect=header_rect, tag=tag, brand=brand)

    # ---- text fits ------------------------------------------------------
    headline_sizes = [fs(value) for value in HEADLINE_SIZES + FALLBACK_HEADLINE_SIZES]
    headline_fits = _fit_descending(
        spec.clean_headline, measurer, headline_sizes,
        max_width=content_w, max_lines=HEADLINE_MAX_LINES, ratio=1.16,
        family="display", min_size=MIN_FONT_SIZE,
    )
    if not headline_fits:
        raise TextOverflowError(
            "headline %r cannot fit in %d lines at >=%dpx on a %dpx column"
            % (spec.clean_headline[:60], HEADLINE_MAX_LINES, MIN_FONT_SIZE, content_w)
        )
    two_line = [fit for fit in headline_fits if fit.line_count <= 2]
    preferred_headline = two_line[0] if two_line else headline_fits[0]
    headline_candidates = [preferred_headline] + [fit for fit in headline_fits if fit is not preferred_headline]

    subtitle_sizes = [fs(value) for value in SUBTITLE_SIZES if fs(value) >= SUBTITLE_MIN_SIZE]
    if not normalize_text(spec.subtitle):
        subtitle_candidates: List[Optional[TextFit]] = [None]
    elif subtitle_sizes:
        subtitle_candidates: List[Optional[TextFit]] = list(
            _fit_descending(
                spec.subtitle, measurer, subtitle_sizes,
                max_width=content_w, max_lines=SUBTITLE_MAX_LINES, ratio=1.34,
                family="sans", min_size=SUBTITLE_MIN_SIZE,
            )
        )
        if not subtitle_candidates:
            subtitle_candidates = [None]
            if normalize_text(spec.subtitle):
                warnings.append("subtitle dropped: too long for the pin")
    else:
        subtitle_candidates = [None]

    bullet_sources = [normalize_text(item) for item in spec.bullets if normalize_text(item)][:MAX_BULLETS]
    card_pad_x, card_pad_y = px(tokens.card_pad_x), px(tokens.card_pad_y)
    icon_size, icon_gap = px(tokens.card_icon), px(tokens.icon_gap)
    bullet_text_w = content_w - 2 * card_pad_x - icon_size - icon_gap
    bullet_fits: List[TextFit] = []
    for bullet_text in bullet_sources:
        fits = _fit_descending(
            bullet_text, measurer, [fs(value) for value in BULLET_SIZES],
            max_width=bullet_text_w, max_lines=BULLET_MAX_LINES, ratio=1.34,
            family="sans", min_size=MIN_FONT_SIZE, truncate=True,
        )
        if fits:
            bullet_fits.append(fits[0])
        else:
            bullet_fits.append(
                fit_text(
                    bullet_text, measurer, max_width=bullet_text_w,
                    sizes=(MIN_FONT_SIZE,), max_lines=BULLET_MAX_LINES,
                    line_height_ratio=1.34, family="sans", min_size=MIN_FONT_SIZE,
                    truncate=True,
                )
            )

    # CTA label / button geometry.
    cta_text = spec.clean_cta
    if not cta_text.endswith("\u2192"):
        cta_text = cta_text + "  \u2192"
    cta_pad_x = px(tokens.cta_pad_x)
    cta_sizes = [fs(value) for value in CTA_SIZES]
    cta_fit = fit_text(
        cta_text, measurer, max_width=max(px(80), content_w - 2 * cta_pad_x),
        sizes=cta_sizes, max_lines=1, line_height_ratio=1.2, family="sans",
        min_size=MIN_FONT_SIZE, truncate=True,
    )
    cta_h = max(px(tokens.cta_height), cta_fit.line_height + 2 * px(18))
    cta_w = min(content_w, cta_fit.width + 2 * cta_pad_x)

    # Footer: disclosure + attribution/brand + optional QR.
    qr_effective = bool(qr) and content_w >= px(tokens.qr_card) + px(150) + 2 * px(tokens.footer_pad)
    footer_h = px(tokens.footer_height_qr) if qr_effective else px(tokens.footer_height)

    def compose(head_fit: TextFit, sub_fit: Optional[TextFit], card_fits: Sequence[TextFit], gap_scale: float) -> Dict[str, Any]:
        gap = [px(round(value * gap_scale)) for value in tokens.gaps]
        y = margin + header_h + gap[0]
        headline_rect = Rect(x0, y, content_w, head_fit.height)
        y = headline_rect.bottom + gap[1]
        rule_rect = Rect(x0, y, px(tokens.accent_rule_width), px(tokens.accent_rule_height))
        y = rule_rect.bottom + gap[2]
        subtitle_rect: Optional[Rect] = None
        if sub_fit is not None:
            subtitle_rect = Rect(x0, y, content_w, sub_fit.height)
            y = subtitle_rect.bottom
        y += gap[3]
        card_rects: List[Rect] = []
        for index, fit in enumerate(card_fits):
            card_h = max(px(72), fit.height + 2 * card_pad_y)
            card_rects.append(Rect(x0, y, content_w, card_h))
            y += card_h
            if index < len(card_fits) - 1:
                y += max(1, px(round(tokens.card_gap * gap_scale)))
        content_end = y
        footer_rect = Rect(x0, height - margin - footer_h, content_w, footer_h)
        cta_rect = Rect(x0, footer_rect.y - gap[4] - cta_h, cta_w, cta_h)
        fits = cta_rect.y > margin and content_end + gap[5] <= cta_rect.y
        return {
            "fits": fits,
            "content_end": content_end,
            "gap": gap,
            "headline_rect": headline_rect,
            "rule_rect": rule_rect,
            "subtitle_rect": subtitle_rect,
            "card_rects": card_rects,
            "cta_rect": cta_rect,
            "footer_rect": footer_rect,
        }

    chosen: Optional[Dict[str, Any]] = None
    chosen_headline = preferred_headline
    chosen_subtitle: Optional[TextFit] = subtitle_candidates[0]
    chosen_bullets: Sequence[TextFit] = bullet_fits
    chosen_gap_scale = 1.0
    gap_scales = (1.0, 0.82, 0.66, 0.52)
    for head_index, head_fit in enumerate(headline_candidates):
        for gap_index, gap_scale in enumerate(gap_scales):
            for sub_index, sub_fit in enumerate(subtitle_candidates):
                for bullet_count in range(len(bullet_fits), -1, -1):
                    geometry = compose(head_fit, sub_fit, bullet_fits[:bullet_count], gap_scale)
                    if geometry["fits"]:
                        chosen = geometry
                        chosen_headline = head_fit
                        chosen_subtitle = sub_fit
                        chosen_bullets = bullet_fits[:bullet_count]
                        chosen_gap_scale = gap_scale
                        if head_index:
                            warnings.append("headline shrunk to %dpx to fit" % head_fit.size)
                        if gap_index:
                            warnings.append("inter-block spacing reduced (x%.2f) to fit" % gap_scale)
                        if sub_index:
                            warnings.append("subtitle shrunk to %dpx to fit" % (sub_fit.size if sub_fit else 0))
                        if bullet_count < len(bullet_fits):
                            warnings.append("%d bullet(s) dropped to fit" % (len(bullet_fits) - bullet_count))
                        break
                if chosen is not None:
                    break
            if chosen is not None:
                break
        if chosen is not None:
            break
    if chosen is None:
        raise LayoutOverflowError(
            "content does not fit on %dx%d even after shrinking (headline=%r, bullets=%d)"
            % (width, height, spec.clean_headline[:60], len(bullet_fits))
        )

    # Vertically centre the content column between header and CTA when there
    # is spare room: a deliberate composition instead of one huge gap.
    extra_space = chosen["cta_rect"].y - chosen["gap"][5] - chosen["content_end"]
    offset = 0
    if extra_space >= px(80):
        offset = min(extra_space // 2, px(tokens.max_content_offset))
        chosen = dict(chosen)
        chosen["headline_rect"] = _shift_rect(chosen["headline_rect"], offset)
        chosen["rule_rect"] = _shift_rect(chosen["rule_rect"], offset)
        if chosen["subtitle_rect"] is not None:
            chosen["subtitle_rect"] = _shift_rect(chosen["subtitle_rect"], offset)
        chosen["card_rects"] = [_shift_rect(rect, offset) for rect in chosen["card_rects"]]
        chosen["content_end"] = chosen["content_end"] + offset
        warnings.append("content centred vertically (+%dpx)" % offset)

    # ---- concrete blocks -------------------------------------------------
    headline_block = TextBlock(
        role="headline",
        rect=chosen["headline_rect"],
        text=chosen_headline.text,
        lines=chosen_headline.lines,
        font_size=chosen_headline.size,
        line_height=chosen_headline.line_height,
        family="display",
        color=chosen_theme.headline,
        target_contrast=HEADING_CONTRAST,
        line_width=chosen_headline.width,
    )
    subtitle_block: Optional[TextBlock] = None
    if chosen_subtitle is not None and chosen["subtitle_rect"] is not None:
        subtitle_block = TextBlock(
            role="subtitle",
            rect=chosen["subtitle_rect"],
            text=chosen_subtitle.text,
            lines=chosen_subtitle.lines,
            font_size=chosen_subtitle.size,
            line_height=chosen_subtitle.line_height,
            family="sans",
            color=chosen_theme.subtitle,
            target_contrast=BODY_CONTRAST,
            line_width=chosen_subtitle.width,
        )

    cards: List[CardBlock] = []
    for index, (fit, declared_rect) in enumerate(zip(chosen_bullets, chosen["card_rects"]), start=1):
        card_rect = Rect(declared_rect.x, declared_rect.y, declared_rect.w, declared_rect.h)
        icon_rect = Rect(
            card_rect.x + card_pad_x,
            card_rect.y + (card_rect.h - icon_size) // 2,
            icon_size,
            icon_size,
        )
        text_rect = Rect(
            icon_rect.right + icon_gap,
            card_rect.y + max(card_pad_y, (card_rect.h - fit.height) // 2),
            bullet_text_w,
            fit.height,
        )
        text_block = TextBlock(
            role="bullet_%d" % index,
            rect=text_rect,
            text=fit.text,
            lines=fit.lines,
            font_size=fit.size,
            line_height=fit.line_height,
            family="sans",
            color=chosen_theme.body,
            target_contrast=BODY_CONTRAST,
            line_width=fit.width,
        )
        cards.append(
            CardBlock(
                rect=card_rect,
                text=text_block,
                icon=icon_rect,
                fill=chosen_theme.ink,
                border_color=chosen_theme.accent,
                radius=px(tokens.radius_card),
            )
        )

    cta_block = ButtonBlock(
        rect=chosen["cta_rect"],
        label=cta_fit.lines[0],
        font_size=cta_fit.size,
        line_height=cta_fit.line_height,
        fill=chosen_theme.accent,
        text_color=chosen_theme.cta_text,
        border_color=None,
        radius=chosen["cta_rect"].h // 2,
        target_contrast=BODY_CONTRAST,
    )

    footer_rect = chosen["footer_rect"]
    footer_pad = px(tokens.footer_pad)
    qr_rect: Optional[Rect] = None
    text_column_w = content_w - 2 * footer_pad
    if qr_effective:
        qr_card = px(tokens.qr_card)
        qr_rect = Rect(footer_rect.right - footer_pad - qr_card, footer_rect.y + (footer_rect.h - qr_card) // 2, qr_card, qr_card)
        text_column_w = qr_rect.x - px(18) - (footer_rect.x + footer_pad)
    disclosure_text = spec.clean_disclosure
    footer_specs: List[Tuple[str, str, RGB, float]] = [
        ("disclosure", disclosure_text, chosen_theme.accent_text, BODY_CONTRAST),
    ]
    if normalize_text(spec.attribution):
        footer_specs.append(("attribution", normalize_text(spec.attribution), chosen_theme.muted, BODY_CONTRAST))
    footer_specs.append(("site", normalize_text(spec.site) or DEFAULT_SITE, chosen_theme.muted, BODY_CONTRAST))
    footer_blocks: List[TextBlock] = []
    line_heights: List[int] = []
    for role, text, color, target in footer_specs:
        fitted = fit_single_line(
            text, measurer, max_width=text_column_w,
            sizes=[fs(value) for value in FOOTER_SIZES], family="sans",
            min_size=MIN_FONT_SIZE, line_height_ratio=1.3,
        )
        line_heights.append(fitted.line_height)
        footer_blocks.append(
            TextBlock(
                role=role,
                rect=Rect(0, 0, text_column_w, fitted.line_height),
                text=fitted.text,
                lines=fitted.lines,
                font_size=fitted.size,
                line_height=fitted.line_height,
                family="sans",
                color=color,
                target_contrast=target,
                line_width=fitted.width,
            )
        )
    total_text_h = sum(line_heights) + px(6) * (len(line_heights) - 1)
    text_x = footer_rect.x + footer_pad
    text_y = footer_rect.y + max(footer_pad, (footer_rect.h - total_text_h) // 2)
    positioned: List[TextBlock] = []
    for block in footer_blocks:
        positioned.append(
            TextBlock(
                role=block.role,
                rect=Rect(text_x, text_y, text_column_w, block.line_height),
                text=block.text,
                lines=block.lines,
                font_size=block.font_size,
                line_height=block.line_height,
                family=block.family,
                color=block.color,
                target_contrast=block.target_contrast,
                line_width=block.line_width,
            )
        )
        text_y += block.line_height + px(6)
    footer = FooterBlock(
        rect=footer_rect,
        texts=tuple(positioned),
        qr_rect=qr_rect,
        fill=chosen_theme.ink,
        border_color=chosen_theme.accent,
        radius=px(tokens.radius_card),
        inner_pad=footer_pad,
    )

    dropped = tuple(bullet_sources[len(chosen_bullets):]) if len(chosen_bullets) < len(bullet_sources) else ()
    layout = PinLayout(
        content=spec,
        size=(width, height),
        theme=chosen_theme,
        variant=variant,
        margin=margin,
        scale=scale,
        header=header,
        headline=headline_block,
        accent_rule=chosen["rule_rect"],
        subtitle=subtitle_block,
        bullets=tuple(cards),
        cta=cta_block,
        footer=footer,
        qr=qr_rect,
        dropped=dropped,
        warnings=tuple(warnings),
    )
    return layout


# ---------------------------------------------------------------------------
# Render layer (lazy Pillow import)
# ---------------------------------------------------------------------------


def _iter_pixels(image):
    """Iterate RGB/L pixels without the deprecated ``getdata`` (Pillow 12+)."""
    flattened = getattr(image, "get_flattened_data", None)
    if flattened is not None:
        bands = image.getbands()
        values = flattened()
        if len(bands) == 1:
            return [(int(value),) for value in values]
        if values and isinstance(values[0], tuple):
            return list(values)
        width = len(bands)
        return [tuple(values[index:index + width]) for index in range(0, len(values), width)]
    return image.getdata()


class _FontCache:
    def __init__(self, font_dir: Optional[Path | str] = None) -> None:
        self.dir = Path(font_dir) if font_dir else FONT_DIR
        self._cache: Dict[Tuple[str, int], Any] = {}

    def get(self, family: str, size: int):
        from PIL import ImageFont

        key = (family, int(size))
        if key not in self._cache:
            path = self.dir / FONT_FILES.get(family, FONT_FILES["sans"])
            if not path.exists():
                raise FileNotFoundError("font not found: %s" % path)
            self._cache[key] = ImageFont.truetype(str(path), int(size))
        return self._cache[key]


def load_photo(path: Path | str):
    """Load a photo as RGB Pillow image (lazy import)."""
    from PIL import Image

    return Image.open(Path(path)).convert("RGB")


def photo_cover(photo, size: Tuple[int, int] = PIN_SIZE):
    """Center-crop *photo* so it covers *size* exactly."""
    from PIL import Image

    width, height = int(size[0]), int(size[1])
    box = cover_box(photo.width, photo.height, width, height)
    cropped = photo.crop(box)
    if cropped.size != (width, height):
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        cropped = cropped.resize((width, height), resampling)
    return cropped


def qr_available() -> bool:
    try:
        import segno  # noqa: F401
        return True
    except ImportError:
        return False


def make_qr_image(
    data: str,
    size: int = 156,
    *,
    dark: RGB = INK,
    light: RGB = WHITE,
) -> Optional[Any]:
    """Render a QR code as a crisp Pillow image (``None`` when segno is absent)."""
    try:
        import segno
    except ImportError:
        return None
    from PIL import Image

    payload = str(data or "").strip()
    if not payload:
        return None
    code = segno.make(payload, error="m")
    total_modules = code.symbol_size(border=2)[0]
    scale = max(1, int(size) // max(1, total_modules))
    buffer = io.BytesIO()
    code.save(
        buffer,
        kind="png",
        scale=scale,
        border=2,
        dark=rgb_to_hex(dark),
        light=rgb_to_hex(light),
    )
    buffer.seek(0)
    image = Image.open(buffer).convert("RGB")
    if image.size != (int(size), int(size)):
        canvas = Image.new("RGB", (int(size), int(size)), light)
        ratio = min(size / image.width, size / image.height)
        new_size = (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))
        resampling = getattr(Image, "Resampling", Image).NEAREST
        resized = image.resize(new_size, resampling)
        canvas.paste(resized, ((size - new_size[0]) // 2, (size - new_size[1]) // 2))
        return canvas
    return image


@dataclass
class PinMetrics:
    """Measured quality metrics of a rendered pin."""

    variant: str
    width: int
    height: int
    margin: int
    margins: Dict[str, int]
    min_font_size: int
    contrast: Dict[str, float]
    min_body_contrast: float
    min_heading_contrast: float
    blocks: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def aspect_ratio(self) -> float:
        return self.width / float(self.height)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variant": self.variant,
            "width": self.width,
            "height": self.height,
            "aspect_ratio": round(self.aspect_ratio, 4),
            "margin": self.margin,
            "margins": dict(self.margins),
            "min_font_size": self.min_font_size,
            "contrast": {key: round(value, 2) for key, value in self.contrast.items()},
            "min_body_contrast": round(self.min_body_contrast, 2),
            "min_heading_contrast": round(self.min_heading_contrast, 2),
            "blocks": self.blocks,
            "warnings": list(self.warnings),
        }

    def violations(self) -> List[str]:
        errors: List[str] = []
        if abs(self.aspect_ratio - PIN_ASPECT) > 0.002:
            errors.append("aspect ratio %.4f != %.4f" % (self.aspect_ratio, PIN_ASPECT))
        if self.min_font_size < MIN_FONT_SIZE:
            errors.append("min font %d < %d" % (self.min_font_size, MIN_FONT_SIZE))
        if self.min_body_contrast + 1e-6 < BODY_CONTRAST:
            errors.append("min body contrast %.2f < %.2f" % (self.min_body_contrast, BODY_CONTRAST))
        if self.min_heading_contrast + 1e-6 < HEADING_CONTRAST:
            errors.append("min heading contrast %.2f < %.2f" % (self.min_heading_contrast, HEADING_CONTRAST))
        for name, value in self.margins.items():
            if value + 1e-6 < MIN_SAFE_MARGIN:
                errors.append("%s margin %d < %d" % (name, value, MIN_SAFE_MARGIN))
        for block in self.blocks:
            line_width = block.get("line_width")
            box_width = block.get("box_width")
            if line_width is not None and box_width is not None and line_width > box_width + 1:
                errors.append("text %r overflows (%s > %s)" % (block.get("role"), line_width, box_width))
        return errors


@dataclass
class RenderedPin:
    """A rendered pin image together with its layout and measured metrics."""

    image: Any
    layout: PinLayout
    metrics: PinMetrics
    variant: str

    @property
    def size(self) -> Tuple[int, int]:
        return self.image.size

    def save(self, path: Path | str, format: Optional[str] = None, **kwargs: Any) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        params: Dict[str, Any] = {}
        if target.suffix.lower() == ".png":
            params.setdefault("optimize", True)
        params.update(kwargs)
        if format:
            self.image.save(str(target), format, **params)
        else:
            self.image.save(str(target), **params)
        return target


class _PinRenderer:
    """Draws a :class:`PinLayout` onto a Pillow image and measures contrast."""

    def __init__(
        self,
        layout: PinLayout,
        *,
        measure: PILTextMeasurer,
        fonts: _FontCache,
        photo: Optional[Any] = None,
        qr_data: str = "",
    ) -> None:
        from PIL import Image

        self.layout = layout
        self.measure = measure
        self.fonts = fonts
        self.photo = photo
        self._qr_data = qr_data
        self.contrast: Dict[str, float] = {}
        self.blocks: List[Dict[str, Any]] = []
        self.warnings: List[str] = list(layout.warnings)
        self.Image = Image
        self.img = self._background()

    # -- backgrounds ------------------------------------------------------
    def _background(self):
        from PIL import Image, ImageDraw

        width, height = self.layout.width, self.layout.height
        theme = self.layout.theme
        if self.layout.variant == "photo" and self.photo is not None:
            base = photo_cover(self.photo, (width, height))
            scrim = Image.new("L", (1, height))
            for y in range(height):
                scrim.putpixel((0, y), int(round(scrim_alpha_at(y / height) * 255)))
            scrim = scrim.resize((width, height))
            ink_layer = Image.new("RGB", (width, height), theme.ink)
            image = Image.composite(ink_layer, base, scrim)
        else:
            stops = gradient_stops(theme)
            image = Image.new("RGB", (width, height))
            draw = ImageDraw.Draw(image)
            for y in range(height):
                draw.line([(0, y), (width, y)], fill=gradient_color_at(stops, y / height))
            image = self._soft_glow(
                image,
                center=(int(width * 0.18), int(height * 0.96)),
                radius=int(width * 0.72),
                color=theme.accent,
                peak_alpha=42,
            )
            image = self._soft_glow(
                image,
                center=(int(width * 0.92), int(height * 0.04)),
                radius=int(width * 0.52),
                color=theme.accent,
                peak_alpha=30,
            )
        return image

    @staticmethod
    def _soft_glow(image, *, center, radius, color, peak_alpha):
        """Composite a soft radial glow (radial mask, no hard ellipse edge)."""
        from PIL import Image, ImageDraw

        diameter = max(16, int(radius) * 2)
        mask = Image.radial_gradient("L").resize((diameter, diameter))
        # radial_gradient is black in the centre -> invert to white in the centre.
        mask = mask.point(lambda value: 255 - value)
        peak = max(0, min(255, int(peak_alpha)))
        mask = mask.point(lambda value: value * peak // 255)
        glow_patch = Image.new("RGBA", (diameter, diameter), tuple(int(c) for c in color) + (255,))
        glow_patch.putalpha(mask)
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        layer.paste(glow_patch, (int(center[0]) - diameter // 2, int(center[1]) - diameter // 2), glow_patch)
        return Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")

    # -- primitives -------------------------------------------------------
    def _overlay(self):
        return self.Image.new("RGBA", self.img.size, (0, 0, 0, 0))

    def rounded(self, rect: Rect, radius: int, fill: Optional[Tuple[int, int, int, int]] = None,
                outline: Optional[Tuple[int, int, int, int]] = None, width: int = 0) -> None:
        if fill is None and outline is None:
            return
        from PIL import ImageDraw

        overlay = self._overlay()
        draw = ImageDraw.Draw(overlay)
        draw.rounded_rectangle(
            (rect.x, rect.y, rect.right - 1, rect.bottom - 1),
            radius=max(0, min(radius, rect.h // 2, rect.w // 2)),
            fill=fill,
            outline=outline,
            width=width,
        )
        self.img = self.Image.alpha_composite(self.img.convert("RGBA"), overlay).convert("RGB")

    def shadow(self, rect: Rect, radius: int) -> None:
        offset = self.layout.scale * DESIGN.shadow_offset
        shadow_rect = Rect(rect.x + int(round(offset * 0.2)), rect.y + int(round(offset)), rect.w, rect.h)
        self.rounded(shadow_rect, radius, fill=(0, 0, 0, DESIGN.shadow_alpha))

    def panel(self, rect: Rect, radius: int, alpha: int, dark: bool = True) -> None:
        color = (4, 5, 9, alpha) if dark else (250, 250, 245, alpha)
        self.rounded(rect, radius, fill=color)

    def _region_contrast(self, rect: Rect, color: RGB) -> float:
        from PIL import Image

        if rect.w <= 0 or rect.h <= 0:
            return 1.0
        crop = self.img.crop((rect.x, rect.y, rect.right, rect.bottom)).convert("RGB")
        sample_w = max(1, min(48, crop.width))
        sample_h = max(1, min(48, crop.height))
        crop = crop.resize((sample_w, sample_h))
        text_lum = relative_luminance(color)
        worst = 21.0
        for pixel in _iter_pixels(crop):
            ratio = contrast_from_luminance(text_lum, relative_luminance(pixel))
            if ratio < worst:
                worst = ratio
        return worst

    def draw_readable_text(self, block: TextBlock, region: Optional[Rect] = None, panel_pad: int = 10) -> float:
        from PIL import ImageDraw

        target = block.target_contrast
        sample_rect = region or block.rect
        needed = sample_rect.expanded(2)
        contrast = self._region_contrast(needed, block.color)
        text_is_light = relative_luminance(block.color) >= 0.3
        for attempt, alpha in enumerate((110, 170, 230)):
            if contrast + 1e-6 >= target:
                break
            pad = panel_pad + attempt * 2
            panel_rect = sample_rect.expanded(pad)
            self.panel(panel_rect, max(8, min(24, panel_rect.h // 2)), alpha, dark=text_is_light)
            contrast = self._region_contrast(needed, block.color)
        if contrast + 1e-6 < target:
            raise QualityError(
                "role %r contrast %.2f < %.2f after scrim panels" % (block.role, contrast, target)
            )
        draw = ImageDraw.Draw(self.img)
        font = self.fonts.get(block.family, block.font_size)
        for index, line in enumerate(block.lines):
            bbox = font.getbbox(line) if line else (0, 0, 0, 0)
            glyph_height = max(0, bbox[3] - bbox[1])
            slot_top = block.rect.y + index * block.line_height
            y = slot_top + (block.line_height - glyph_height) // 2 - bbox[1]
            if block.align == "center":
                draw.text(
                    (block.rect.center_x, slot_top + block.line_height // 2),
                    line,
                    font=font,
                    fill=block.color,
                    anchor="mm",
                )
            else:
                draw.text((block.rect.x, y), line, font=font, fill=block.color)
        self.contrast[block.role] = round(contrast, 2)
        line_width = max((int(math.ceil(self.measure.measure(line, block.font_size, block.family))) for line in block.lines), default=0)
        self.blocks.append(
            {
                "role": block.role,
                "font_size": block.font_size,
                "lines": len(block.lines),
                "box_width": block.rect.w,
                "line_width": line_width,
                "rect": block.rect.to_dict(),
                "contrast": round(contrast, 2),
            }
        )
        return contrast

    def draw_pill(self, pill: PillBlock) -> None:
        from PIL import ImageDraw

        self.rounded(
            pill.rect,
            pill.radius,
            fill=pill.fill + (242,),
            outline=pill.border_color + (255,),
            width=max(1, pill.border_width),
        )
        font = self.fonts.get("sans", pill.font_size)
        draw = ImageDraw.Draw(self.img)
        if pill.tracking:
            total = letterspaced_width(pill.text, self.measure, pill.font_size, pill.tracking)
            x = pill.rect.center_x - total / 2
            for char in pill.text:
                draw.text((int(round(x)), pill.rect.center_y), char, font=font, fill=pill.text_color, anchor="lm")
                x += self.measure.measure(char, pill.font_size, "sans") + pill.tracking
        else:
            draw.text((pill.rect.center_x, pill.rect.center_y), pill.text, font=font, fill=pill.text_color, anchor="mm")
        self.contrast["tag"] = round(contrast_ratio(pill.text_color, pill.fill), 2)
        self.blocks.append(
            {
                "role": "tag",
                "font_size": pill.font_size,
                "lines": 1,
                "box_width": pill.rect.w,
                "line_width": int(math.ceil(self.measure.measure(pill.text, pill.font_size, "sans"))),
                "rect": pill.rect.to_dict(),
                "contrast": self.contrast["tag"],
            }
        )

    def draw_brand(self, brand: BrandMark) -> None:
        from PIL import ImageDraw

        self.rounded(brand.monogram_rect, max(8, brand.monogram_rect.w // 4), fill=brand.fill + (255,))
        font = self.fonts.get("sans", brand.monogram_font_size)
        draw = ImageDraw.Draw(self.img)
        draw.text(
            (brand.monogram_rect.center_x, brand.monogram_rect.center_y),
            brand.monogram_text,
            font=font,
            fill=brand.text_color,
            anchor="mm",
        )
        self.contrast["brandmark"] = round(contrast_ratio(brand.text_color, brand.fill), 2)
        if brand.wordmark is not None:
            block = brand.wordmark
            sample = Rect(block.rect.x, block.rect.y, block.rect.w, block.rect.h)
            contrast = self._region_contrast(sample.expanded(2), block.color)
            if contrast + 1e-6 < BODY_CONTRAST:
                self.panel(sample.expanded(8), 10, 150, dark=True)
                contrast = self._region_contrast(sample.expanded(2), block.color)
            if contrast + 1e-6 < BODY_CONTRAST:
                raise QualityError("brand wordmark contrast %.2f < %.2f" % (contrast, BODY_CONTRAST))
            font = self.fonts.get("sans", block.font_size)
            draw = ImageDraw.Draw(self.img)
            x = block.rect.x
            for char in block.text:
                draw.text((x, block.rect.center_y), char, font=font, fill=block.color, anchor="lm")
                x += self.measure.measure(char, block.font_size, "sans") + brand.tracking
            self.contrast["brandmark_text"] = round(contrast, 2)
            self.blocks.append(
                {
                    "role": "brandmark_text",
                    "font_size": block.font_size,
                    "lines": 1,
                    "box_width": block.rect.w,
                    "line_width": int(math.ceil(self.measure.measure(block.text, block.font_size, "sans"))),
                    "rect": block.rect.to_dict(),
                    "contrast": round(contrast, 2),
                }
            )

    def draw_rule(self, rect: Rect) -> None:
        self.rounded(rect, rect.h // 2, fill=self.layout.theme.accent + (255,))

    def draw_card(self, card: CardBlock) -> None:
        from PIL import ImageDraw

        self.shadow(card.rect, card.radius)
        self.rounded(card.rect, card.radius, fill=card.fill + (236,), outline=card.border_color + (200,), width=2)
        self.rounded(card.icon, card.icon.w // 2, fill=self.layout.theme.accent + (255,))
        draw = ImageDraw.Draw(self.img)
        font = self.fonts.get("sans", int(card.icon.h * 0.55))
        if font.size < MIN_FONT_SIZE:
            font = self.fonts.get("sans", MIN_FONT_SIZE)
        draw.text((card.icon.center_x, card.icon.center_y), "\u2713", font=font,
                  fill=self.layout.theme.cta_text, anchor="mm")

    def draw_cta(self, button: ButtonBlock) -> None:
        from PIL import ImageDraw

        self.shadow(button.rect, button.radius)
        self.rounded(button.rect, button.radius, fill=button.fill + (255,),
                     outline=button.border_color + (255,) if button.border_color else None,
                     width=2 if button.border_color else 0)
        # CTA fill is an opaque solid, so the analytic WCAG ratio is exact.
        contrast = contrast_ratio(button.text_color, button.fill)
        if contrast + 1e-6 < button.target_contrast:
            raise QualityError("CTA contrast %.2f < %.2f" % (contrast, button.target_contrast))
        font = self.fonts.get("sans", button.font_size)
        draw = ImageDraw.Draw(self.img)
        draw.text((button.rect.x + (button.rect.w // 2), button.rect.center_y),
                  button.label, font=font, fill=button.text_color, anchor="mm")
        self.contrast["cta"] = round(contrast, 2)
        self.blocks.append(
            {
                "role": "cta",
                "font_size": button.font_size,
                "lines": 1,
                "box_width": button.rect.w,
                "line_width": int(math.ceil(self.measure.measure(button.label, button.font_size, "sans"))),
                "rect": button.rect.to_dict(),
                "contrast": round(contrast, 2),
            }
        )

    def draw_footer(self, footer: FooterBlock) -> None:
        from PIL import ImageDraw

        self.rounded(footer.rect, footer.radius, fill=footer.fill + (255,),
                     outline=footer.border_color + (120,), width=2)
        for block in footer.texts:
            self.draw_readable_text(block)
        if footer.qr_rect is not None:
            qr_card = footer.qr_rect
            self.rounded(qr_card, DESIGN.radius_qr, fill=(255, 255, 255, 255))
            inset = max(4, DESIGN.qr_inset)
            inner = Rect(qr_card.x + inset, qr_card.y + inset, qr_card.w - 2 * inset, qr_card.h - 2 * inset)
            qr_image = make_qr_image(self._qr_data, size=max(32, inner.w))
            if qr_image is None:
                draw = ImageDraw.Draw(self.img)
                draw.text(
                    (qr_card.center_x, qr_card.center_y),
                    "QR",
                    font=self.fonts.get("sans", MIN_FONT_SIZE),
                    fill=INK,
                    anchor="mm",
                )
            else:
                self.img.paste(qr_image, (inner.x, inner.y))

    # -- compose ----------------------------------------------------------
    def draw(self) -> None:
        self.draw_pill(self.layout.header.tag) if self.layout.header.tag is not None else None
        self.draw_brand(self.layout.header.brand)
        self.draw_readable_text(self.layout.headline)
        self.draw_rule(self.layout.accent_rule)
        if self.layout.subtitle is not None:
            self.draw_readable_text(self.layout.subtitle)
        for card in self.layout.bullets:
            self.draw_card(card)
            self.draw_readable_text(card.text, region=card.text.rect)
        self.draw_cta(self.layout.cta)
        self.draw_footer(self.layout.footer)

    def fill_metrics(self) -> PinMetrics:
        layout = self.layout
        width, height = layout.width, layout.height
        top_level = [rect for _, rect in layout.top_level_rects()]
        top_level.extend([layout.header.tag.rect] if layout.header.tag is not None else [])
        top_level.append(layout.header.brand.rect)
        left = min(rect.x for rect in top_level)
        top = min(rect.y for rect in top_level)
        right = width - max(rect.right for rect in top_level)
        bottom = height - max(rect.bottom for rect in top_level)
        heading_roles = {"headline"}
        body_contrasts = [value for role, value in self.contrast.items() if role not in heading_roles]
        min_body = min(body_contrasts) if body_contrasts else 21.0
        min_heading = min((value for role, value in self.contrast.items() if role in heading_roles), default=21.0)
        return PinMetrics(
            variant=layout.variant,
            width=width,
            height=height,
            margin=layout.margin,
            margins={"left": left, "top": top, "right": right, "bottom": bottom},
            min_font_size=layout.min_font_size,
            contrast=dict(self.contrast),
            min_body_contrast=min_body,
            min_heading_contrast=min_heading,
            blocks=list(self.blocks),
            warnings=list(self.warnings),
        )


def _resolve_photo(photo: Any = None, photo_bytes: Optional[bytes] = None, photo_path: Optional[Path | str] = None):
    from PIL import Image

    if photo is not None:
        return photo.convert("RGB")
    if photo_bytes:
        return Image.open(io.BytesIO(photo_bytes)).convert("RGB")
    if photo_path:
        return load_photo(photo_path)
    return None


def render_pin(
    content: PinContent | Mapping[str, Any] | Any,
    size: Tuple[int, int] = PIN_SIZE,
    variants: Sequence[str] = ("photo", "gradient"),
    *,
    photo: Any = None,
    photo_bytes: Optional[bytes] = None,
    photo_path: Optional[Path | str] = None,
    qr_data: str = "",
    font_dir: Optional[Path | str] = None,
    theme: Optional[Theme] = None,
    validate: bool = True,
    tokens: DesignTokens = DESIGN,
) -> Dict[str, RenderedPin]:
    """Render one pin per requested variant and return ``{variant: RenderedPin}``.

    ``photo`` / ``photo_bytes`` / ``photo_path`` supply the photo background.
    When no photo is available the photo variant falls back to the gradient
    variant (and the returned key is ``"gradient"``).  ``qr_data`` adds an
    optional QR code to the footer.  Raises :class:`QualityError` when the
    measured metrics (contrast, font size, margins, overflow) fail the gates.
    """
    spec = PinContent.from_object(content)
    chosen_theme = theme or theme_for(spec.niche, accent=spec.accent, background=spec.background)
    photo_image = _resolve_photo(photo, photo_bytes, photo_path)
    requested = [str(item) for item in variants] if not isinstance(variants, str) else [variants]
    plans: List[str] = []
    for item in requested:
        if item == "photo" and photo_image is not None:
            plans.append("photo")
        elif item == "gradient":
            plans.append("gradient")
    if not plans:
        plans = ["gradient"]
        if "photo" in requested:
            # No photo available: degrade gracefully instead of failing.
            plans = ["gradient"]
    results: Dict[str, RenderedPin] = {}
    fonts = _FontCache(font_dir)
    for variant in plans:
        measurer = PILTextMeasurer(font_dir)
        layout = layout_pin(
            spec,
            size=size,
            theme=chosen_theme,
            measure=measurer,
            variant=variant,
            qr=bool(qr_data),
            tokens=tokens,
        )
        layout.assert_valid()
        renderer = _PinRenderer(
            layout,
            measure=measurer,
            fonts=fonts,
            photo=photo_image if variant == "photo" else None,
            qr_data=qr_data,
        )
        renderer.draw()
        metrics = renderer.fill_metrics()
        if validate:
            violations = metrics.violations()
            if violations:
                raise QualityError(
                    "rendered %s pin failed quality gates:\n- %s" % (variant, "\n- ".join(violations))
                )
        results[variant] = RenderedPin(
            image=renderer.img,
            layout=layout,
            metrics=metrics,
            variant=variant,
        )
    return results


def render_pin_single(
    content: PinContent | Mapping[str, Any] | Any,
    *,
    variant: str = "gradient",
    **kwargs: Any,
) -> RenderedPin:
    """Convenience wrapper around :func:`render_pin` for a single variant."""
    result = render_pin(content, variants=(variant,), **kwargs)
    if variant in result:
        return result[variant]
    return next(iter(result.values()))


# ---------------------------------------------------------------------------
# Pinterest payload / CSV helpers (pure)
# ---------------------------------------------------------------------------

BOARD_BY_NICHE: Dict[str, str] = {
    "travel": "Travel ideas",
    "crypto": "Crypto",
    "ai": "AI tools",
    "sports": "Sports",
    "default": "Pins",
}

KEYWORDS_BY_NICHE: Dict[str, Tuple[str, ...]] = {
    "travel": ("travel tips", "city breaks", "budget travel", "travel guide"),
    "crypto": ("bitcoin", "crypto news", "prediction markets", "crypto explained"),
    "ai": ("ai tools", "productivity", "ai news", "workflow automation"),
    "sports": ("nfl", "sports picks", "sports news", "game preview"),
    "default": ("content factory", "guides", "explained"),
}

STOPWORDS = frozenset(
    "a an and are as at be by for from how in into is it its of on or that the this to was "
    "what when where which who why with you your we our their they them he she i".split()
)


def board_for_niche(niche: str) -> str:
    """Pinterest board name for a niche (deterministic mapping)."""
    key = str(niche or "").strip().lower()
    return BOARD_BY_NICHE.get(key, BOARD_BY_NICHE["default"])


def _keyword_tokens(text: str) -> List[str]:
    words = re.findall(r"[a-z0-9][a-z0-9\-]{2,}", str(text or "").lower())
    return [word for word in words if word not in STOPWORDS]


def keywords_for(niche: str, *texts: str, limit: int = 8, max_keyword_len: int = 64) -> Tuple[str, ...]:
    """Keyword list for a pin: niche keywords first, then title/description tokens."""
    key = str(niche or "").strip().lower()
    candidates: List[str] = list(KEYWORDS_BY_NICHE.get(key, KEYWORDS_BY_NICHE["default"]))
    for text in texts:
        for token in _keyword_tokens(text):
            candidates.append(token)
    result: List[str] = []
    seen = set()
    for candidate in candidates:
        value = normalize_text(candidate).lower()[:max_keyword_len].strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) >= limit:
            break
    return tuple(result)


def keywords_text(niche: str, *texts: str, limit: int = 8) -> str:
    return ", ".join(keywords_for(niche, *texts, limit=limit))


def _clamp_text(text: Any, limit: int) -> str:
    value = normalize_text(text)
    if len(value) <= limit:
        return value
    if limit <= 0:
        return ""
    cut = value[: limit - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    cut = cut.rstrip(" ,.;:-")
    return (cut + "\u2026")[:limit]


def _composed_description(content: PinContent) -> str:
    parts: List[str] = []
    if normalize_text(content.headline):
        parts.append(normalize_text(content.headline) + ".")
    if normalize_text(content.subtitle):
        parts.append(normalize_text(content.subtitle) + ".")
    if content.bullets:
        parts.append(" ".join(normalize_text(item) for item in content.bullets[:3]) + ".")
    return " ".join(parts)


def build_pinterest_payload(
    content: PinContent | Mapping[str, Any] | Any,
    *,
    image_url: str,
    board_id: str = "<BOARD_ID>",
    disclosure: str = "",
    include_link: Optional[bool] = None,
) -> Dict[str, Any]:
    """Build a ``POST /v5/pins`` payload with validated Pinterest limits.

    Title <= 100 chars, description <= 500 chars and *always* contains the CTA
    and the disclosure; alt text <= 500 chars.  Raises
    :class:`PinterestPayloadError` for an invalid media URL.
    """
    spec = PinContent.from_object(content)
    url = normalize_text(image_url)
    if not re.match(r"^https?://", url):
        raise PinterestPayloadError("image_url must be an http(s) URL, got %r" % image_url)
    title = _clamp_text(spec.title or spec.headline or "Content Factory pin", TITLE_MAX) or "Content Factory pin"
    cta = normalize_text(spec.cta) or "Read more"
    if not cta.endswith((".", "!", "?", "\u2192")):
        cta = cta + "."
    disclosure_text = normalize_text(disclosure) or spec.clean_disclosure
    base = normalize_text(spec.description) or _composed_description(spec)
    tail_parts = [cta]
    if disclosure_text:
        tail_parts.append(disclosure_text)
    tail = " ".join(tail_parts)
    if len(tail) >= DESCRIPTION_MAX:
        tail = _clamp_text(tail, DESCRIPTION_MAX)
        base = ""
    else:
        base = _clamp_text(base, DESCRIPTION_MAX - len(tail) - 1)
    description = (base + " " + tail).strip() if base else tail
    description = _clamp_text(description, DESCRIPTION_MAX)
    if spec.alt_text:
        alt_source = spec.alt_text
    else:
        alt_source = ". ".join(
            part.strip().rstrip(".") for part in (spec.headline, spec.subtitle) if normalize_text(part)
        )
        if alt_source:
            alt_source += "."
    alt_text = _clamp_text(alt_source or title, ALT_TEXT_MAX) or title
    payload: Dict[str, Any] = {
        "board_id": normalize_text(board_id) or "<BOARD_ID>",
        "title": title,
        "description": description,
        "alt_text": alt_text,
        "media_source": {"source_type": "image_url", "url": url},
    }
    include = include_link if include_link is not None else bool(normalize_text(spec.link))
    if include and normalize_text(spec.link):
        payload["link"] = normalize_text(spec.link)
    errors = validate_pinterest_payload(payload)
    if errors:
        raise PinterestPayloadError("invalid Pinterest payload: " + "; ".join(errors))
    return payload


def validate_pinterest_payload(payload: Mapping[str, Any]) -> List[str]:
    """Validate a ``POST /v5/pins`` payload; returns a list of problems."""
    errors: List[str] = []
    if not isinstance(payload, Mapping):
        return ["payload must be a mapping"]
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("title is required")
    elif len(title) > TITLE_MAX:
        errors.append("title is %d chars > %d" % (len(title), TITLE_MAX))
    description = payload.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append("description is required")
    elif len(description) > DESCRIPTION_MAX:
        errors.append("description is %d chars > %d" % (len(description), DESCRIPTION_MAX))
    alt_text = payload.get("alt_text")
    if alt_text is not None and (not isinstance(alt_text, str) or len(alt_text) > ALT_TEXT_MAX):
        errors.append("alt_text is missing or > %d chars" % ALT_TEXT_MAX)
    media_source = payload.get("media_source")
    if not isinstance(media_source, Mapping):
        errors.append("media_source is required")
    else:
        if media_source.get("source_type") != "image_url":
            errors.append("media_source.source_type must be 'image_url'")
        url = str(media_source.get("url") or "")
        if not re.match(r"^https?://", url):
            errors.append("media_source.url must be an http(s) URL")
    link = payload.get("link")
    if link is not None and (not isinstance(link, str) or not re.match(r"^https?://", link)):
        errors.append("link must be an http(s) URL")
    board_id = payload.get("board_id")
    if board_id is not None and not isinstance(board_id, str):
        errors.append("board_id must be a string")
    return errors


CSV_COLUMNS: Tuple[str, ...] = (
    "Title",
    "Media URL",
    "Pinterest board",
    "Thumbnail",
    "Description",
    "Link",
    "Publish date",
    "Keywords",
)
KEYWORDS_MAX_CHARS = 320
KEYWORD_MAX_CHARS = 64


def build_csv_row(meta: Mapping[str, Any], *, default_link: str = "") -> Dict[str, str]:
    """Normalise a pin sidecar (JSON) into a Pinterest import CSV row."""
    meta = meta or {}
    pin = meta.get("pin") or {}
    if not isinstance(pin, Mapping):
        pin = {}
    niche = str(meta.get("niche") or "travel").strip().lower()
    title = normalize_text(pin.get("title") or meta.get("title"))
    media = meta.get("image_url") or (pin.get("media_source") or {}).get("url") or ""
    description = normalize_text(pin.get("description") or meta.get("description"))
    board = normalize_text(meta.get("board")) or board_for_niche(niche)
    keywords = meta.get("keywords")
    if isinstance(keywords, (list, tuple)):
        keywords = ", ".join(str(item) for item in keywords if str(item).strip())
    keywords = normalize_text(keywords) or keywords_text(niche, title, description)
    link = normalize_text(pin.get("link") or meta.get("link")) or normalize_text(default_link)
    return {
        "Title": title,
        "Media URL": str(media or ""),
        "Pinterest board": board,
        "Thumbnail": "",
        "Description": description,
        "Link": link,
        "Publish date": "",
        "Keywords": keywords,
    }


def validate_csv_row(
    row: Mapping[str, Any],
    *,
    meta: Optional[Mapping[str, Any]] = None,
    strict: bool = False,
) -> Tuple[List[str], List[str]]:
    """Validate one CSV row; returns ``(errors, warnings)``."""
    errors: List[str] = []
    warnings: List[str] = []
    meta = meta or {}
    title = str(row.get("Title") or "")
    if not title.strip():
        errors.append("Title is required")
    elif len(title) > TITLE_MAX:
        errors.append("Title is %d chars > %d" % (len(title), TITLE_MAX))
    description = str(row.get("Description") or "")
    if not description.strip():
        errors.append("Description is required")
    elif len(description) > DESCRIPTION_MAX:
        errors.append("Description is %d chars > %d" % (len(description), DESCRIPTION_MAX))
    media = str(row.get("Media URL") or "").strip()
    if not media:
        errors.append("Media URL is required")
    else:
        path = media.split("?", 1)[0].split("#", 1)[0].lower()
        if not re.match(r"^https?://", media):
            errors.append("Media URL must be an absolute http(s) URL: %s" % media[:80])
        elif not path.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            errors.append("Media URL must point to an image file: %s" % media[:80])
    board = str(row.get("Pinterest board") or "").strip()
    if not board:
        errors.append("Pinterest board is required")
    elif board not in BOARD_BY_NICHE.values():
        warnings.append("board %r is not in the standard mapping (it will be auto-created)" % board)
    keywords = str(row.get("Keywords") or "").strip()
    if not keywords:
        errors.append("Keywords are required")
    else:
        parts = [part.strip() for part in keywords.split(",")]
        if any(not part for part in parts):
            errors.append("Keywords contain empty values")
        if any(len(part) > KEYWORD_MAX_CHARS for part in parts):
            errors.append("a keyword is longer than %d chars" % KEYWORD_MAX_CHARS)
        if len(keywords) > KEYWORDS_MAX_CHARS:
            errors.append("Keywords total %d chars > %d" % (len(keywords), KEYWORDS_MAX_CHARS))
    link = str(row.get("Link") or "").strip()
    if link and not re.match(r"^https?://", link):
        errors.append("Link must be an absolute http(s) URL")
    if bool(meta.get("affiliate")) and not link:
        errors.append("affiliate pin has no Link")
    disclosure = normalize_text(meta.get("disclosure"))
    if bool(meta.get("affiliate")):
        if disclosure and disclosure not in description:
            warnings.append("affiliate disclosure %r is missing from Description" % disclosure)
        elif not disclosure and "ad" not in description.lower():
            warnings.append("affiliate Description does not mention the disclosure")
    if strict:
        errors.extend(warnings)
        warnings = []
    return errors, warnings


def validate_csv_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    metas: Optional[Sequence[Mapping[str, Any]]] = None,
    strict: bool = False,
) -> Tuple[List[str], List[str]]:
    """Validate a batch of CSV rows, adding duplicate checks."""
    errors: List[str] = []
    warnings: List[str] = []
    seen_titles: Dict[str, int] = {}
    seen_urls: Dict[str, int] = {}
    for index, row in enumerate(rows):
        meta = metas[index] if metas and index < len(metas) else None
        row_errors, row_warnings = validate_csv_row(row, meta=meta, strict=strict)
        label = "row %d (%r)" % (index + 1, str(row.get("Title") or "")[:40])
        errors.extend("%s: %s" % (label, error) for error in row_errors)
        warnings.extend("%s: %s" % (label, warning) for warning in row_warnings)
        title = str(row.get("Title") or "").strip().lower()
        url = str(row.get("Media URL") or "").strip().lower()
        if title:
            if title in seen_titles:
                warnings.append("%s: duplicate Title (also row %d)" % (label, seen_titles[title] + 1))
            else:
                seen_titles[title] = index
        if url:
            if url in seen_urls:
                warnings.append("%s: duplicate Media URL (also row %d)" % (label, seen_urls[url] + 1))
            else:
                seen_urls[url] = index
    if strict:
        errors.extend(warnings)
        warnings = []
    return errors, warnings


def format_attribution(credit: Optional[Mapping[str, Any]], max_author: int = 48) -> str:
    """Human-readable photo attribution preserving author and license."""
    if not credit:
        return ""
    author = normalize_text(credit.get("author") or "")
    if len(author) > max_author:
        author = author[: max_author - 1].rstrip() + "\u2026"
    license_name = normalize_text(credit.get("license") or "CC")
    parts = ["Photo: " + author] if author else ["Photo"]
    if license_name:
        parts.append(license_name)
    line = " \u00b7 ".join(parts)
    source = str(credit.get("source") or "")
    if source and "commons" in source.lower():
        line += " \u00b7 Wikimedia"
    return line
