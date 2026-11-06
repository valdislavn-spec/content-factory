"""Учёт токенов LLM и оценка экономии.

Токены берутся из фактического ответа провайдера, если он их отдаёт:

* Ollama — поля ``prompt_eval_count`` / ``eval_count`` в ``/api/generate``;
* OpenAI-совместимые API — ``usage.prompt_tokens`` / ``usage.completion_tokens``;
* остальные (Dify, GigaChat, YandexGPT) — как получится, чаще оценка.

Если провайдер usage не вернул, токены оцениваются по длине текста
(для русского ≈ 3.3 символа на токен, для английского ≈ 4.0). Оценка
помечается флагом ``estimated`` — это не биллинг, а ориентир для экономии.

Файл ``data/llm_tokens.json`` хранит статистику за текущие сутки UTC и
обнуляется при смене даты. Рядом с ним (в том же каталоге) лежит
``llm_usage.json`` — счётчик запросов ;) бюджета, см. ``budget.py``.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..utils import atomic_write_text

LOGGER = logging.getLogger(__name__)

CHARS_PER_TOKEN_RU = 3.3
CHARS_PER_TOKEN_EN = 4.0
MIN_PROMPT_OVERHEAD = 4  # служебные токены на любой запрос


def estimate_tokens(text: str, language: str = "ru") -> int:
    """Оценка числа токенов по длине текста (без токенизатора, быстро)."""
    value = str(text or "")
    if not value:
        return 0
    ratio = CHARS_PER_TOKEN_EN if str(language).lower().startswith("en") else CHARS_PER_TOKEN_RU
    return int(len(value) / ratio) + MIN_PROMPT_OVERHEAD


class TokenTracker:
    """Суточная статистика токенов с сохранением на диск (UTC)."""

    def __init__(self, path: Any, clock: Optional[Callable[[], datetime]] = None) -> None:
        self.path = Path(path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()

    # -- внутреннее ----------------------------------------------------------
    def _today(self) -> str:
        return self._clock().astimezone(timezone.utc).strftime("%Y-%m-%d")

    def _empty(self) -> Dict[str, Any]:
        return {
            "date": self._today(),
            "calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "estimated_calls": 0,
            "cache_hits": 0,
            "cache_saved_tokens": 0,
            "by_provider": {},
        }

    def _load(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self._empty()
        if not isinstance(data, dict) or data.get("date") != self._today():
            return self._empty()
        base = self._empty()
        base.update({key: data.get(key, base[key]) for key in base})
        if not isinstance(base.get("by_provider"), dict):
            base["by_provider"] = {}
        return base

    def _save(self, data: Dict[str, Any]) -> None:
        try:
            atomic_write_text(self.path, json.dumps(data, ensure_ascii=False))
        except OSError as exc:  # не роняем конвейер из-за прав на data/
            LOGGER.warning("Учёт токенов: не удалось сохранить %s: %s", self.path, exc)

    # -- публичное -----------------------------------------------------------
    def record(
        self,
        provider: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        estimated: bool = False,
    ) -> None:
        """Записывает один вызов LLM (реальные токены или оценку)."""
        prompt_tokens = max(0, int(prompt_tokens or 0))
        completion_tokens = max(0, int(completion_tokens or 0))
        with self._lock:
            data = self._load()
            data["calls"] = int(data.get("calls") or 0) + 1
            data["prompt_tokens"] = int(data.get("prompt_tokens") or 0) + prompt_tokens
            data["completion_tokens"] = int(data.get("completion_tokens") or 0) + completion_tokens
            if estimated:
                data["estimated_calls"] = int(data.get("estimated_calls") or 0) + 1
            per = data.setdefault("by_provider", {}).setdefault(
                provider or "unknown",
                {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0},
            )
            per["calls"] = int(per.get("calls") or 0) + 1
            per["prompt_tokens"] = int(per.get("prompt_tokens") or 0) + prompt_tokens
            per["completion_tokens"] = int(per.get("completion_tokens") or 0) + completion_tokens
            self._save(data)

    def record_cache_hit(self, provider: str, saved_tokens: int = 0) -> None:
        """Кэш отдал готовый ответ: запрос к модели не ушёл, токены сэкономлены."""
        with self._lock:
            data = self._load()
            data["cache_hits"] = int(data.get("cache_hits") or 0) + 1
            data["cache_saved_tokens"] = int(data.get("cache_saved_tokens") or 0) + max(
                0, int(saved_tokens or 0)
            )
            per = data.setdefault("by_provider", {}).setdefault(
                provider or "unknown",
                {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0},
            )
            per.setdefault("cache_hits", 0)
            per["cache_hits"] = int(per.get("cache_hits") or 0) + 1
            self._save(data)

    def today(self) -> Dict[str, Any]:
        data = self._load()
        data["total_tokens"] = int(data.get("prompt_tokens") or 0) + int(
            data.get("completion_tokens") or 0
        )
        return data

    def reset(self) -> None:
        self._save(self._empty())

    def describe(self) -> str:
        data = self.today()
        return (
            "токены за сутки (UTC): промпт {p}, ответ {c}, всего {t}; "
            "кэш: {h} попаданий, сэкономлено {s}"
        ).format(
            p=data["prompt_tokens"],
            c=data["completion_tokens"],
            t=data["total_tokens"],
            h=data["cache_hits"],
            s=data["cache_saved_tokens"],
        )


# ---------------------------------------------------------------------------
# Глобальный трекер: настраивается в get_llm() под data_dir проекта
# ---------------------------------------------------------------------------

_TRACKER: Optional[TokenTracker] = None
_TRACKER_LOCK = threading.Lock()


def configure(path: Any) -> TokenTracker:
    """Настраивает глобальный трекер под конкретный проект/данные."""
    global _TRACKER
    with _TRACKER_LOCK:
        _TRACKER = TokenTracker(path)
        return _TRACKER


def get_tracker() -> Optional[TokenTracker]:
    return _TRACKER


def record_usage(
    provider: str,
    usage: Optional[Dict[str, Any]] = None,
    prompt: str = "",
    completion: str = "",
    language: str = "ru",
) -> None:
    """Записывает usage провайдера; если его нет — оценивает по тексту."""
    tracker = _TRACKER
    if tracker is None:
        return
    usage = dict(usage or {})
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    estimated = False
    if not prompt_tokens:
        prompt_tokens = estimate_tokens(prompt, language)
        estimated = True
    if not completion_tokens:
        completion_tokens = estimate_tokens(completion, language)
        estimated = True
    tracker.record(
        provider,
        int(prompt_tokens or 0),
        int(completion_tokens or 0),
        estimated=estimated,
    )


__all__ = [
    "TokenTracker",
    "configure",
    "estimate_tokens",
    "get_tracker",
    "record_usage",
]
