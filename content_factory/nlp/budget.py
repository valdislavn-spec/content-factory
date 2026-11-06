"""Суточный бюджет обращений к платной LLM.

Нужен, чтобы бесплатные лимиты (Dify Cloud Sandbox — 200 message credits,
GigaChat/YandexGPT и т.п.) не выжигались за пару дней. Бюджет считается по
фактическим запросам ``LLMClient.generate``, хранится в JSON рядом с базой
и автоматически обнуляется при смене даты (UTC).

Если бюджет исчерпан, ``LimitedLLMClient`` перестаёт звать модель, и конвейер
продолжает работать в бесплатном экстрактивном режиме — посты выходят, но
без расходования кредитов.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..utils import atomic_write_text

logger = logging.getLogger(__name__)


class DailyBudget:
    """Счётчик запросов к LLM за сутки UTC с сохранением на диск."""

    def __init__(
        self,
        path: Any,
        limit: int,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.path = Path(path)
        self.limit = max(0, int(limit))
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()

    def _today(self) -> str:
        return self._clock().astimezone(timezone.utc).strftime("%Y-%m-%d")

    def _load(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: Dict[str, Any]) -> None:
        try:
            atomic_write_text(self.path, json.dumps(data, ensure_ascii=False))
        except OSError as exc:  # не роняем конвейер из-за прав на data/
            logger.warning("Бюджет LLM: не удалось сохранить %s: %s", self.path, exc)

    @property
    def unlimited(self) -> bool:
        return self.limit <= 0

    def used(self) -> int:
        data = self._load()
        if data.get("date") != self._today():
            return 0
        try:
            return max(0, int(data.get("count") or 0))
        except (TypeError, ValueError):
            return 0

    def remaining(self) -> int:
        if self.unlimited:
            return 10**9
        return max(0, self.limit - self.used())

    def try_consume(self, amount: int = 1) -> bool:
        """Резервирует запрос; ``False`` — дневной лимит уже исчерпан."""
        if self.unlimited:
            return True
        with self._lock:
            used = self.used()
            if used + amount > self.limit:
                return False
            self._save({"date": self._today(), "count": used + amount})
            return True

    def describe(self) -> str:
        if self.unlimited:
            return "бюджет: без ограничений"
        return "бюджет: {}/{} запросов сегодня (UTC)".format(self.used(), self.limit)
