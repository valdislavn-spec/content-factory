"""Генерация фирменных фото-карточек для постов.

Заголовок — Playfair Display (крупный, характерный serif).
Тело — Inter (простой и читаемый гротеск), с запасным вариантом Georgia.

Карточка накладывается на градиент канала, сверху — аватар канала из
``assets/logos/<channel>.png``, снизу — хэштеги и подпись канала.
PNG складывается в ``data/outbox/cards/<post>.png`` и при публикации
уходит в Telegram через sendPhoto (multipart).

Если Pillow или шрифты недоступны — функция возвращает ``None`` и публикация
идёт обычным текстом (без падения пайплайна).
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "assets" / "fonts"
LOGO_DIR = ROOT / "assets" / "logos"

PLAYFAIR_PATH = FONT_DIR / "PlayfairDisplay.ttf"
INTER_PATH = FONT_DIR / "Inter.ttf"

# локальные запасные шрифты (macOS) — если в assets/fonts нет файлов
GEORGIA_PATHS = [
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
]
INTER_FALLBACK = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]

# цветовые схемы каналов (ключ — id канала; иначе по ключевым словам)
THEMES: Dict[str, Dict[str, Any]] = {
    "ai-news": dict(c1=(8, 20, 42), c2=(18, 84, 168), accent=(79, 195, 247), label="AI NEWS"),
    "tech-ai-es": dict(c1=(16, 19, 62), c2=(64, 74, 168), accent=(129, 199, 255), label="TECNOLOGÍA E IA"),
    "crypto-news": dict(c1=(30, 18, 6), c2=(176, 88, 8), accent=(255, 193, 7), label="CRYPTO"),
    "crypto-es": dict(c1=(34, 20, 8), c2=(196, 104, 12), accent=(255, 213, 79), label="CRIPTO"),
    "sport-news": dict(c1=(14, 20, 28), c2=(168, 28, 42), accent=(255, 209, 102), label="US SPORTS"),
    "futbol-es": dict(c1=(6, 34, 24), c2=(26, 122, 74), accent=(255, 209, 102), label="FÚTBOL"),
}
_FALLBACK_THEMES = [
    (("crypto", "cripto", "blockchain"), THEMES["crypto-news"]),
    (("sport", "deport", "fútbol", "futbol", "soccer"), THEMES["sport-news"]),
    (("ai", "ia", "tech"), THEMES["ai-news"]),
]

FORMAT_LABELS = {
    "ru": {"digest": "ДАЙДЖЕСТ", "story": "НОВОСТЬ", "analysis": "РАЗБОР", "brief": "БРИФ"},
    "en": {"digest": "DIGEST", "story": "NEWS", "analysis": "ANALYSIS", "brief": "BRIEF"},
    "es": {"digest": "DIGESTO", "story": "NOTICIA", "analysis": "ANÁLISIS", "brief": "RESUMEN"},
}

LANG_LABELS = {"ru": "RU", "en": "EN", "es": "ES"}

# публичные юзернеймы каналов (в конфиге хранятся только числовые chat_id)
HANDLES = {
    "ai-news": "AINEWS0007",
    "sport-news": "SPORTNews0007",
    "crypto-news": "HOOPY0007",
    "tech-ai-es": "WORLDNews0007",
    "crypto-es": "TechnologiesNews01",
    "futbol-es": "SPORTSAnalytics007",
}

_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"  # эмодзи
    "\U00002600-\U000027BF"  # символы/дингбаты
    "\U0001F1E6-\U0001F1FF"  # флаги
    "\U00002190-\U000021FF"  # стрелки
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U000020E3"              # keycap
    "\U0000200D"              # ZWJ
    "]+"
)


def _guess_headline(text: str) -> str:
    """Достаёт заголовок из текста поста, даже если переносы схлопнуты."""
    text = " ".join(str(text or "").split())
    if not text:
        return ""
    # 1) первая строка
    first_line = str(text).split("\n")[0].strip()
    if first_line and len(first_line) <= 150 and "\n" in str(text):
        return first_line
    # 2) длинный разделитель «———» / «===» / «---»
    match = re.search(r"\s*[—–_=-]{3,}\s*", text)
    if match:
        candidate = text[: match.start()].strip()
        if 8 <= len(candidate) <= 170:
            return candidate
    # 3) первое предложение
    match = re.match(r"(.{15,170}?[.!?])\s", text)
    if match:
        return match.group(1).strip()
    return text[:120].strip()


_SYMBOL_RE = re.compile("[\u2190-\u21FF\u2300-\u23FF\u2500-\u27BF\u2B00-\u2BFF]")


def _clean_text(text: str) -> str:
    """Убирает эмодзи и служебные символы, которые Playfair/Inter не рисуют."""
    # нумерованные эмодзи "1️⃣" → "1." (после вырезания keycap остался бы "1")
    text = re.sub(r"([0-9])\ufe0f?\u20e3", r"\1. ", text)
    text = _EMOJI_RE.sub(" ", text)
    text = text.replace("\ufe0f", "").replace("\u20e3", "")
    # маркеры списков/рамки: ▪ • □ ■ и т.п. — без них карточка чище
    text = _SYMBOL_RE.sub(" ", text)
    return " ".join(text.split())


def _theme(channel_id: str, language: str = "en") -> Dict[str, Any]:
    theme = THEMES.get(channel_id)
    if theme:
        # ES-варианты наследуют палитру соответствующей темы, но со своим id
        return theme
    key = f"{channel_id} {language}".lower()
    for words, candidate in _FALLBACK_THEMES:
        if any(word in key for word in words):
            return candidate
    return THEMES["ai-news"]


# ---------------------------------------------------------------------------
# шрифты
# ---------------------------------------------------------------------------
def _load_font(primary: Path, fallbacks: Sequence[str], size: int, weight: Optional[int] = None):
    """Загружает шрифт; для вариативных TTF выставляет вес (оси)."""
    from PIL import ImageFont

    candidates: List[str] = []
    for path in (primary,):
        if Path(path).is_file():
            candidates.append(str(path))
    candidates.extend(fallbacks)
    for path in candidates:
        if not Path(path).is_file():
            continue
        try:
            font = ImageFont.truetype(str(path), size)
            if weight is not None:
                axes = font.get_variation_axes()
                if axes:
                    values = []
                    for axis in axes:
                        name = str(axis.get("name") or axis.get("tag") or "").lower()
                        if "weight" in name or "wght" in name:
                            values.append(weight)
                        elif "optical" in name or "opsz" in name or "size" in name:
                            values.append(max(14, min(32, int(size * 0.6))))
                        else:
                            values.append(axis.get("default") or 400)
                    font.set_variation_by_axes(values)
            else:
                instances = font.get_variation_names()
                if instances:
                    # по умолчанию — Regular
                    for name in instances:
                        if name == b"Regular":
                            font.set_variation_by_name(name)
                            break
            return font
        except Exception as exc:  # noqa: BLE001 - шрифт может не подойти
            logger.debug("Шрифт %s недоступен: %s", path, exc)
    return None


def _headline_font(size: int, weight: int = 800):
    return _load_font(PLAYFAIR_PATH, GEORGIA_PATHS, size, weight=weight)


def _body_font(size: int, weight: int = 400):
    return _load_font(INTER_PATH, INTER_FALLBACK, size, weight=weight)


# ---------------------------------------------------------------------------
# вспомогательное рисование
# ---------------------------------------------------------------------------
def _mix(a: Tuple[int, int, int], b: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _gradient(size: Tuple[int, int], c1, c2, angle: float = 0.55):
    from PIL import Image

    w, h = size
    img = Image.new("RGB", (w, h), c2)
    px = img.load()
    for y in range(h):
        base = (y / h) * (1 - angle)
        for x in range(w):
            t = base + (x / w) * angle
            px[x, y] = _mix(c1, c2, max(0.0, min(1.0, t)))
    return img


def _vignette(img, strength: float = 0.55):
    from PIL import Image, ImageDraw, ImageFilter

    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse((-w * 0.3, -h * 0.3, w * 1.3, h * 1.3), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(max(w, h) // 7))
    dark = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(img, Image.blend(img, dark, strength), mask)


def _glow(img, center, radius: int, color, alpha: int = 80):
    from PIL import Image, ImageDraw, ImageFilter

    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(
        (center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius),
        fill=tuple(color) + (alpha,),
    )
    layer = layer.filter(ImageFilter.GaussianBlur(radius // 2))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def _wrap(draw, text: str, font, max_width: int) -> List[str]:
    """Перенос по словам с учётом ширины."""
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit_headline(draw, text: str, max_width: int, max_lines: int, start_size: int, min_size: int = 54):
    """Подбирает кегль так, чтобы заголовок влез в max_lines строк."""
    size = start_size
    while size >= min_size:
        font = _headline_font(size, weight=850)
        if font is None:
            return None, size, []
        lines = _wrap(draw, text, font, max_width)
        if len(lines) <= max_lines:
            return font, size, lines
        size -= 6
    font = _headline_font(min_size, weight=850)
    lines = _wrap(draw, text, font, max_width) if font else []
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip() + " …"
    return font, min_size, lines


def _trim_body(text: str, max_chars: int) -> str:
    text = "\n".join(" ".join(line.split()) for line in text.splitlines())
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    # отрезаем по границе предложения/слова
    for sep in (". ", "! ", "? ", "; "):
        pos = cut.rfind(sep)
        if pos > max_chars * 0.55:
            return cut[: pos + 1].rstrip() + " …"
    pos = cut.rfind(" ")
    return (cut[:pos] if pos > 0 else cut).rstrip() + " …"


def _strip_headline_prefix(text: str, headline: str) -> str:
    """Убирает заголовок в начале текста, не резая текст по длине."""
    if not text or not headline:
        return text
    words = str(headline).split()
    lowered = text.lower()
    for count in range(min(len(words), 12), 2, -1):
        prefix = " ".join(words[:count]).lower()
        if lowered.startswith(prefix):
            return text[len(prefix):].lstrip(" —–-:·|")
    return text


def _avatar(channel_id: str, size: int):
    """Круглый аватар канала из assets/logos (или None)."""
    from PIL import Image, ImageDraw

    path = LOGO_DIR / f"{channel_id}.png"
    if not path.is_file():
        return None
    try:
        logo = Image.open(path).convert("RGB").resize((size, size))
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
        return logo, mask
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# публичная функция
# ---------------------------------------------------------------------------
def render_post_card(
    post: Any,
    channel: Any,
    settings: Any,
    headline: Optional[str] = None,
    width: int = 1080,
    height: int = 1350,
    body_chars: int = 640,
) -> Optional[Path]:
    """Рисует фото-карточку поста. Возвращает путь к PNG или None."""
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:  # noqa: BLE001 - Pillow не установлен
        logger.debug("Pillow недоступен, карточки пропущены: %s", exc)
        return None

    language = str(getattr(channel, "language", "en") or "en")
    theme = _theme(str(getattr(channel, "id", "")), language)
    accent = theme["accent"]
    plain = getattr(post, "plain_text", "") or ""

    # заголовок: headline из сюжета, иначе шапка поста (до длинного
    # разделителя «———»/переноса/первого предложения)
    text_headline = _guess_headline(plain)
    if headline is None or len(str(headline).strip()) < 8:
        headline = text_headline
    headline = _clean_text(str(headline or ""))
    if not headline:
        headline = _clean_text(str(getattr(channel, "title", "") or ""))

    # тело: пост без заголовка, без хвоста источников/хэштегов.
    if "\n" not in plain:
        # strip_html схлопывает переносы: отрезаем заголовок по словам,
        # затем снимаем служебные подписи (Trending/Key points/Context...).
        body_text = _strip_headline_prefix(plain, str(headline))
        label_re = re.compile(
            r"(?:Key points|Trending now|Context|In short|Why it matters|"
            r"Principales|En tendencia|Fuentes|Главное|Контекст|В тренде)\s*:\s*"
        )
        for _ in range(4):  # снимаем несколько служебных префиксов подряд
            label = label_re.search(body_text)
            if label is not None and label.start() < 60:
                body_text = body_text[label.end():]
            else:
                break
        body = _clean_text(body_text)
    else:
        body_lines = [line for line in plain.splitlines() if line.strip()]
        if len(body_lines) > 1 and len(body_lines[0]) <= 140:
            body_lines = body_lines[1:]
        kept = []
        for line in body_lines:
            stripped = line.strip()
            if not stripped:
                continue
            if re.fullmatch(r"[—–\-=\u2022·\s]{2,}", stripped):
                kept.append("")  # абзацный разрыв вместо линии-разделителя
                continue
            kept.append(re.sub(r"\s*[—–]{3,}\s*", "\n", stripped))
        body = "\n".join(_clean_text(part) for part in kept)
    fmt_name = str((getattr(post, "meta", {}) or {}).get("format") or "").lower()
    if fmt_name == "digest":
        # пункты дайджеста "1. ... 2. ..." — с новой строки
        body = re.sub(r"\s+(?=[1-9]\.\s)", "\n", body)
    if not body:
        body = _clean_text(plain)
    # хэштеги рисуются в подвале — убираем их из тела, чтобы не дублировались
    body = re.sub(r"(?<!\w)#[^\s#<]+", "", body)
    body = re.sub(r"[ \t]{2,}", " ", body).strip()
    for marker in ("Источники:", "Sources:"):
        pos = body.find(marker)
        if pos > body_chars * 0.3:
            body = body[:pos]
    body = _trim_body(body, body_chars)

    img = _gradient((width, height), theme["c1"], theme["c2"], angle=0.62)
    img = _vignette(img, 0.42)
    img = _glow(img, (width * 0.2, height * 0.16), int(width * 0.42), accent, 60)

    draw = ImageDraw.Draw(img)
    # лёгкая сетка точек (отдельный RGBA-слой, иначе alpha на RGB игнорируется)
    dots = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dots_draw = ImageDraw.Draw(dots)
    for x in range(60, width, 56):
        for y in range(48, height, 56):
            dots_draw.ellipse((x, y, x + 2, y + 2), fill=(255, 255, 255, 34))
    img = Image.alpha_composite(img.convert("RGBA"), dots).convert("RGB")
    draw = ImageDraw.Draw(img)

    margin = 90
    # --- шапка: аватар + имя канала + формат -------------------------------
    avatar = _avatar(str(getattr(channel, "id", "")), 104)
    ax, ay = margin, 84
    if avatar:
        logo, mask = avatar
        img.paste(logo, (ax, ay), mask)
        draw.ellipse((ax - 2, ay - 2, ax + 104, ay + 104), outline=(255, 255, 255, 70), width=2)

    title_font = _body_font(34, weight=700)
    label_font = _body_font(21, weight=600)
    if title_font and label_font:
        channel_title = str(getattr(channel, "title", "") or getattr(channel, "id", ""))
        draw.text((ax + 132, ay + 12), channel_title, font=title_font, fill=(255, 255, 255, 245))
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%d.%m.%Y")
        lang_label = LANG_LABELS.get(language, language.upper())
        draw.text((ax + 134, ay + 62), f"{today}  ·  {lang_label}", font=label_font, fill=accent + (235,))

    fmt = str((getattr(post, "meta", {}) or {}).get("format") or "").strip().lower()
    labels = FORMAT_LABELS.get(language, FORMAT_LABELS["en"])
    pill = labels.get(fmt, fmt.upper() if fmt else "")
    if pill and label_font:
        pill_font = _body_font(22, weight=700)
        tw = draw.textlength(pill, font=pill_font)
        px = width - margin - tw - 40
        draw.rounded_rectangle((px, ay + 22, px + tw + 40, ay + 22 + 46), radius=23,
                               outline=accent + (200,), width=2)
        draw.text((px + 20, ay + 33), pill, font=pill_font, fill=accent + (245,))

    # --- заголовок ----------------------------------------------------------
    hfont, hsize, hlines = _fit_headline(draw, headline, width - margin * 2, max_lines=5, start_size=92, min_size=52)
    y = 300
    if hfont:
        line_h = int(hsize * 1.12)
        for line in hlines:
            draw.text((margin + 3, y + 4), line, font=hfont, fill=(0, 0, 0, 120))
            draw.text((margin, y), line, font=hfont, fill=(255, 255, 255, 252))
            y += line_h
        y += 26
    # акцентная линия
    draw.rounded_rectangle((margin, y, margin + 132, y + 8), radius=4, fill=accent + (255,))
    y += 46

    # --- тело ---------------------------------------------------------------
    body_font = _body_font(37, weight=400)
    if body_font and body:
        max_w = width - margin * 2
        max_y = height - 210
        line_h = int(37 * 1.55)
        all_lines = []
        for para in body.split("\n"):
            all_lines.extend(_wrap(draw, para, body_font, max_w))
        max_lines = max(1, (max_y - y) // line_h)
        if len(all_lines) > max_lines:
            all_lines = all_lines[:max_lines]
            all_lines[-1] = all_lines[-1].rstrip() + " …"
        for line in all_lines:
            draw.text((margin, y), line, font=body_font, fill=(255, 255, 255, 214))
            y += line_h

    # --- подвал -------------------------------------------------------------
    footer_y = height - 196
    draw.line((margin, footer_y - 26, width - margin, footer_y - 26), fill=(255, 255, 255, 34), width=2)
    hashtags = [str(tag) for tag in (getattr(post, "hashtags", []) or [])[:4]]
    if hashtags and label_font:
        tags_font = _body_font(27, weight=600)
        draw.text((margin, footer_y), "  ".join(hashtags), font=tags_font, fill=accent + (235,))
    channel_id = str(getattr(channel, "id", ""))
    username = str(getattr(channel, "telegram_username", "") or "").strip().lstrip("@")
    username = username or HANDLES.get(channel_id, "")
    handle = "@" + username if username else ""
    if label_font and handle:
        # Водяной знак: заметная «пилюля» с @username — каждая пересылка карточки
        # приводит новых подписчиков, даже если текст поста потерялся.
        wm_font = _body_font(28, weight=700)
        if wm_font:
            hw = draw.textlength(handle, font=wm_font)
            pad_x, pad_y = 20, 10
            wx = width - margin - hw - pad_x * 2
            wy = footer_y + 46
            draw.rounded_rectangle(
                (wx, wy, wx + hw + pad_x * 2, wy + 28 + pad_y * 2),
                radius=22, fill=(0, 0, 0, 96), outline=(255, 255, 255, 90), width=2,
            )
            draw.text((wx + pad_x, wy + pad_y - 2), handle, font=wm_font, fill=(255, 255, 255, 235))

    # --- сохранение ---------------------------------------------------------
    try:
        data_dir = Path(getattr(settings, "data_dir", "data"))
        out_dir = data_dir / "outbox" / "cards"
        out_dir.mkdir(parents=True, exist_ok=True)
        post_id = str(getattr(post, "id", "") or "card")
        path = out_dir / f"{post_id}.png"
        img.convert("RGB").save(path, "PNG", optimize=True)
        return path
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось сохранить карточку поста: %s", exc)
        return None
