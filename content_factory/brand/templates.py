"""Брендовые шаблоны для всех соцсетей: конфиг, план, рендер.

Чистая часть (конфиг/план/партнёры) не требует PIL — её можно тестировать в
обычном venv. Рендер (render) лениво импортирует PIL и segno, поэтому
запускать его нужно интерпретатором с Pillow (DSH-python + PYTHONPATH segno).
"""
from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "brand_templates.yaml"
VALID_LAYOUTS = {"wide", "square", "portrait", "story"}


def load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    import yaml

    config_path = Path(path) if path else DEFAULT_CONFIG
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    networks = data.get("networks") or []
    if not networks:
        raise ValueError("в brand_templates.yaml нет networks")
    for network in networks:
        if network.get("layout") not in VALID_LAYOUTS:
            raise ValueError(f"неизвестный layout у {network.get('key')}: {network.get('layout')}")
        size = network.get("size") or []
        if len(size) != 2 or not all(isinstance(value, int) and value > 0 for value in size):
            raise ValueError(f"некорректный size у {network.get('key')}: {size}")
    if not data.get("topics"):
        raise ValueError("в brand_templates.yaml нет topics")
    data["_path"] = str(config_path)
    return data


def _resolve_partner_file(config: Dict[str, Any]) -> Path:
    raw = Path((config.get("partners") or {}).get("file") or "config/affiliates.yaml")
    return raw if raw.is_absolute() else ROOT / raw


def ready_partners(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Партнёрки в статусе ready (только их можно ставить в шаблоны)."""
    import yaml

    status = str((config.get("partners") or {}).get("status") or "ready")
    path = _resolve_partner_file(config)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    result = []
    for key, program in (data.get("programs") or {}).items():
        if str(program.get("status") or "").lower() != status:
            continue
        if not str(program.get("url") or "").strip():
            continue
        result.append(
            {
                "key": str(key),
                "title": str(program.get("title") or key),
                "url": str(program.get("url")),
                "commission": str(program.get("commission") or ""),
                "age_restricted": bool(program.get("age_restricted")),
            }
        )
    return result


def _network(config: Dict[str, Any], key: str) -> Dict[str, Any]:
    for network in config["networks"]:
        if network["key"] == key:
            return network
    raise ValueError(f"неизвестная сеть: {key}")


def _topic(config: Dict[str, Any], key: str) -> Dict[str, Any]:
    topic = (config.get("topics") or {}).get(key)
    if not topic:
        raise ValueError(f"неизвестная тема: {key}")
    return topic


def plan(
    config: Dict[str, Any],
    network_key: str,
    topic_key: str = "ai",
    partner_key: str = "",
    headline: str = "",
    subtitle: str = "",
    cta: str = "",
) -> Dict[str, Any]:
    """Собирает спецификацию изображения (без рендера)."""
    network = _network(config, network_key)
    topic = _topic(config, topic_key)
    partners = ready_partners(config)
    partner: Optional[Dict[str, Any]] = None
    if partner_key:
        partner = next((item for item in partners if item["key"] == partner_key), None)
        if partner is None:
            raise ValueError(f"партнёрка «{partner_key}» не в статусе ready")
    elif partners:
        partner = partners[0]
    return {
        "network": network["key"],
        "label": network.get("label") or network["key"],
        "size": tuple(network["size"]),
        "layout": network["layout"],
        "topic_key": topic_key,
        "topic": topic,
        "headline": (headline or topic["headline"]).strip(),
        "subtitle": (subtitle or topic.get("subtitle") or "").strip(),
        "cta": (cta or topic.get("cta") or "").strip(),
        "partner": partner,
        "disclosure": (config.get("partners") or {}).get("disclosure") or "",
        "brand": config.get("brand") or {},
        "qr": config.get("qr") or {"enabled": True, "size": 168, "border": 2},
    }


# ---------------------------------------------------------------------------
# рендер (PIL + segno)
# ---------------------------------------------------------------------------
def _hex(color: str) -> Tuple[int, int, int]:
    value = color.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _mix(a: Tuple[int, int, int], b: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def _gradient(size: Tuple[int, int], c1, c2) -> "Any":
    from PIL import Image

    width, height = size
    img = Image.new("RGB", size, c1)
    draw = ImageDraw.Draw(img)  # noqa: F821
    return img


def render(spec: Dict[str, Any], out_dir: Optional[Path] = None) -> Path:
    """Рендерит PNG-шаблон. Требует PIL; segno — для QR."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    brand = spec["brand"]
    colors = brand.get("colors") or {}
    bg1, bg2 = _hex(colors.get("bg1", "#070f1a")), _hex(colors.get("bg2", "#10233c"))
    ink, mute = _hex(colors.get("ink", "#eaf7ff")), _hex(colors.get("mute", "#8fb3c9"))
    cyan = _hex(colors.get("cyan", "#38e8ff"))
    accent = _hex(spec["topic"].get("accent", "#38e8ff"))

    width, height = spec["size"]
    layout = spec["layout"]
    # быстрый вертикальный градиент: столбец → ресайз
    column = Image.new("RGB", (1, height))
    column_px = column.load()
    for y in range(height):
        column_px[0, y] = _mix(bg1, bg2, y / max(1, height - 1))
    img = column.resize((width, height), Image.BILINEAR)

    # сетка/узлы (как в фирменном аватаре)
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    random.seed(11 + width + height)
    nodes = []
    for _ in range(26):
        nx = random.uniform(width * 0.05, width * 0.95)
        ny = random.uniform(height * 0.08, height * 0.92)
        nodes.append((nx, ny))
    for i, p in enumerate(nodes):
        for q in nodes[i + 1:]:
            if math.dist(p, q) < min(width, height) * 0.18:
                draw.line((*p, *q), fill=accent + (26,), width=1)
    for p in nodes:
        draw.ellipse((p[0] - 1.6, p[1] - 1.6, p[0] + 1.6, p[1] + 1.6), fill=accent + (90,))
    glow = layer.filter(ImageFilter.GaussianBlur(2))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    draw = ImageDraw.Draw(img)

    head_font_path = ROOT / (brand.get("fonts") or {}).get("headline", "assets/fonts/PlayfairDisplay.ttf")
    body_font_path = ROOT / (brand.get("fonts") or {}).get("body", "assets/fonts/Inter.ttf")

    def font(path: Path, size: int, weight: Optional[int] = None):
        f = ImageFont.truetype(str(path), size)
        if weight is not None:
            try:
                f.set_variation_by_axes([weight])
            except Exception:  # noqa: BLE001
                pass
        return f

    margin = int(min(width, height) * 0.07)
    is_story = layout in {"story", "portrait"}
    head_size = int(min(width, height) * (0.115 if layout == "wide" else 0.095))
    body_size = int(min(width, height) * (0.032 if layout == "wide" else 0.030))

    # верхняя строка бренда
    top_font = font(body_font_path, int(body_size * 0.85), 700)
    draw.text((margin, margin), "CF", font=font(head_font_path, int(body_size * 1.6)), fill=cyan)
    draw.text((margin + int(body_size * 2.3), margin + 4),
              (brand.get("name") or "Content Factory").upper(), font=top_font, fill=ink)
    tag = spec["label"].upper()
    tag_font = font(body_font_path, int(body_size * 0.8), 500)
    tag_w = draw.textlength(tag, font=tag_font)
    draw.text((width - margin - tag_w, margin + 4), tag, font=tag_font, fill=mute)

    # акцентная линия
    draw.rectangle((margin, margin + int(body_size * 2.6), margin + int(width * 0.12), margin + int(body_size * 2.6) + 5), fill=accent)

    # headline: подбираем кегль
    headline = spec["headline"]
    lines: List[str] = headline.split("\n")
    while head_size > int(body_size * 1.3):
        hfont = font(head_font_path, head_size, 800)
        fits = all(draw.textlength(line, font=hfont) <= width - 2 * margin for line in lines)
        if fits:
            break
        head_size -= 4
    hfont = font(head_font_path, head_size, 800)
    hline = int(head_size * 1.12)
    block_h = hline * len(lines)
    start_y = int(height * (0.30 if layout == "wide" else 0.33))
    for index, line in enumerate(lines):
        draw.text((margin, start_y + index * hline), line, font=hfont, fill=ink)

    # subtitle (перенос по словам)
    sub_font = font(body_font_path, body_size, 400)
    words = spec["subtitle"].split()
    current = ""
    sub_y = start_y + block_h + int(body_size * 1.1)
    for word in words:
        candidate = (current + " " + word).strip()
        if draw.textlength(candidate, font=sub_font) > width - 2 * margin and current:
            draw.text((margin, sub_y), current, font=sub_font, fill=mute)
            sub_y += int(body_size * 1.45)
            current = word
        else:
            current = candidate
    if current:
        draw.text((margin, sub_y), current, font=sub_font, fill=mute)

    # партнёрский блок + QR
    partner = spec.get("partner")
    qr_size = int((spec.get("qr") or {}).get("size") or 168)
    qr_enabled = bool((spec.get("qr") or {}).get("enabled", True))
    chip_h = int(body_size * 2.6)
    chip_y = height - margin - chip_h - (qr_size + int(body_size * 0.6) if qr_enabled and is_story else 0)
    if partner:
        chip_w = min(width - 2 * margin, int(width * 0.62))
        draw.rounded_rectangle((margin, chip_y, margin + chip_w, chip_y + chip_h),
                               radius=int(chip_h * 0.35), outline=accent, width=2,
                               fill=_mix(bg2, accent, 0.06))
        p_font = font(body_font_path, int(body_size * 0.9), 700)
        p_small = font(body_font_path, int(body_size * 0.72), 400)
        draw.text((margin + int(body_size * 0.7), chip_y + int(chip_h * 0.16)),
                  f"Partner: {partner['title']}", font=p_font, fill=ink)
        url = partner["url"].replace("https://", "").replace("http://", "")
        draw.text((margin + int(body_size * 0.7), chip_y + int(chip_h * 0.58)),
                  url[:64], font=p_small, fill=mute)
        if partner.get("age_restricted"):
            draw.text((margin + chip_w - int(body_size * 2.2), chip_y + int(chip_h * 0.16)),
                      "18+", font=p_font, fill=accent)

    if qr_enabled and partner:
        import io

        import segno

        qr = segno.make(partner["url"], error="m")
        buffer = io.BytesIO()
        qr.save(buffer, kind="png", scale=10, border=int((spec.get("qr") or {}).get("border") or 2))
        buffer.seek(0)
        qr_img = Image.open(buffer).convert("RGB")
        qr_img = qr_img.resize((qr_size, qr_size), Image.LANCZOS)
        card = int(qr_size * 1.12)
        qx = width - margin - card
        qy = (height - card) // 2 if layout == "wide" else height - margin - card
        draw.rounded_rectangle((qx, qy, qx + card, qy + card), radius=int(card * 0.08), fill=(255, 255, 255))
        img.paste(qr_img, (qx + (card - qr_size) // 2, qy + (card - qr_size) // 2))

    # CTA + disclosure
    if spec.get("cta"):
        cta_font = font(body_font_path, int(body_size * 0.85), 600)
        draw.text((margin, chip_y - int(body_size * 1.9)), spec["cta"], font=cta_font, fill=cyan)
    disclosure = spec.get("disclosure") or ""
    if disclosure:
        d_font = font(body_font_path, max(12, int(body_size * 0.55)), 400)
        draw.text((margin, height - int(margin * 0.8)), disclosure[:120], font=d_font, fill=mute)

    directory = Path(out_dir) if out_dir else ROOT / "assets" / "brand"
    directory.mkdir(parents=True, exist_ok=True)
    suffix = f"{spec['network']}-{spec['topic_key']}"
    if partner:
        suffix += f"-{partner['key']}"
    target = directory / f"{suffix}.png"
    img.save(target, quality=95)
    return target
