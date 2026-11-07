"""Общие утилиты: JSON, текст, время, оценка токенов."""

from __future__ import annotations

import datetime
import json
import re
from typing import Any


def now_iso() -> str:
    """Текущее время в UTC в ISO-формате (секунды)."""
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def approx_tokens(text: str) -> int:
    """Грубая оценка числа токенов: ~4 символа на токен.

    Нужна только для бюджета и логов демо; реальные провайдеры возвращают
    точные значения в usage.
    """
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def truncate(text: str, limit: int) -> str:
    """Схлопнуть пробелы и обрезать строку по границе слова."""
    text = " ".join((text or "").split())
    if limit <= 0 or len(text) <= limit:
        return text
    cut = text[:limit].rstrip()
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:—-") + "…"


def strip_html(text: str) -> str:
    """Убрать HTML-теги и лишние пробелы из текста RSS."""
    text = re.sub(r"<script.*?</script>", " ", text or "", flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return " ".join(text.split())


def slugify(text: str, fallback: str = "post") -> str:
    """Безопасное имя файла: латиница, цифры, дефис."""
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    return text[:60] or fallback


def extract_json(text: str) -> Any:
    """Достать JSON из ответа модели.

    Поддерживает чистый JSON, ```json-блоки и текст с JSON внутри.
    Бросает ValueError, если JSON не найден.
    """
    if not text or not text.strip():
        raise ValueError("пустой ответ модели")

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json|JSON)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except ValueError:
        pass

    starts = [i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1]
    if not starts:
        raise ValueError("в ответе нет JSON-объекта или массива")
    start = min(starts)
    end = max(cleaned.rfind("}"), cleaned.rfind("]"))
    if end <= start:
        raise ValueError("не удалось выделить границы JSON")
    candidate = cleaned[start : end + 1]
    try:
        return json.loads(candidate)
    except ValueError as exc:
        raise ValueError("ответ не является валидным JSON") from exc
