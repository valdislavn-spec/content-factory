"""Язык контента: минимальный языковой слой (ru/en/es).

Завод по умолчанию русскоязычный, но канал может быть объявлен английским
(``language: en``) или испанским (``language: es``) в config/channels.yaml.
Генератор постов, анализ и шаблонный fallback выбирают язык по каналу, а не
по глобальной настройке — так один запуск может обслуживать каналы на разных
языках. Неизвестные/пустые значения по-прежнему сводятся к ``ru``, поэтому
старое поведение не меняется.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

SUPPORTED_LANGUAGES = ("ru", "en", "es")
DEFAULT_LANGUAGE = "ru"


def language_code(value: Any, default: str = DEFAULT_LANGUAGE) -> str:
    """Приводит язык к ``ru``/``en``/``es``; неизвестное значение — ``default``.

    Понимает коды вида ``es``, ``es-ES``, ``es_419``, ``es-MX`` (аналогично
    ``en-US``/``ru-RU`` для прежних языков).
    """
    text = str(value or "").strip().lower().replace("_", "-")
    if text.startswith("en"):
        return "en"
    if text.startswith("ru"):
        return "ru"
    if text.startswith("es"):
        return "es"
    return default


def is_english(value: Any) -> bool:
    return language_code(value) == "en"


def is_spanish(value: Any) -> bool:
    return language_code(value) == "es"


def resolve_language(
    explicit: Any = None,
    articles: Optional[Iterable[Any]] = None,
    settings: Any = None,
    default: str = DEFAULT_LANGUAGE,
) -> str:
    """Определяет язык контента.

    Приоритет: явный язык канала → язык статей кластера → ``app.language``
    из настроек → ``ru``. Так старые вызовы без канала сохраняют поведение,
    а английский или испанский канал всегда получает анализ на своём языке.
    """
    if explicit:
        return language_code(explicit, default)
    for article in articles or []:
        value = getattr(article, "language", "")
        if value:
            return language_code(value, default)
    if settings is not None:
        try:
            value = settings.get("app.language")
        except Exception:  # pragma: no cover - нестандартные Settings
            value = None
        if value:
            return language_code(value, default)
    return language_code(default, default)
