"""Кэш ответов LLM: одинаковый промпт → ответ без повторного запроса.

Экономия без потери качества: это точное совпадение промпта (системный
промпт, текст, лимиты, температура и модель), поэтому закэшированный ответ
идентичен новому. Полезно, когда конвейер перезапускают (демон, cron, ручные
прогоны, повторный анализ тех же новостей) — токены не тратятся второй раз.

Хранение — SQLite-файл рядом с рабочей базой проекта (``data/llm_cache.sqlite3``),
TTL по умолчанию 7 суток. Чистится лениво: при записи и по запросу ``purge``.
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

LOGGER = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_cache (
    key             TEXT PRIMARY KEY,
    provider        TEXT NOT NULL,
    prompt_tokens   INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    response        TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    hits            INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_llm_cache_created ON llm_cache (created_at);
"""


def make_key(provider: str, system: str, prompt: str, max_tokens: Any, temperature: Any) -> str:
    """Ключ кэша: всё, что влияет на ответ модели."""
    payload = "\x1f".join(
        [
            str(provider or ""),
            str(system or ""),
            str(prompt or ""),
            str(int(max_tokens or 0)),
            str(float(temperature or 0.0)),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LLMCache:
    """SQLite-кэш ответов LLM с TTL и статистикой."""

    def __init__(self, path: Any, ttl_hours: int = 168) -> None:
        self.path = Path(path)
        self.ttl_hours = max(0, int(ttl_hours or 0))
        self._lock = threading.Lock()
        self._enabled = True
        self._prepare()

    # -- инфраструктура ------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path), timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _prepare(self) -> None:
        try:
            with self._lock, self._connect() as connection:
                connection.executescript(_SCHEMA)
        except sqlite3.Error as exc:  # повреждённый файл кэша не должен ронять завод
            LOGGER.warning("Кэш LLM недоступен (%s): отключаю кэширование", exc)
            self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled and self.ttl_hours > 0

    # -- публичное -----------------------------------------------------------
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        try:
            with self._lock, self._connect() as connection:
                row = connection.execute(
                    "SELECT provider, prompt_tokens, completion_tokens, response, created_at "
                    "FROM llm_cache WHERE key = ?",
                    (key,),
                ).fetchone()
                if row is None:
                    return None
                created_at = _parse_dt(row[4])
                if created_at is not None and datetime.now(timezone.utc) - created_at > timedelta(
                    hours=self.ttl_hours
                ):
                    return None
                connection.execute(
                    "UPDATE llm_cache SET hits = hits + 1 WHERE key = ?", (key,)
                )
        except sqlite3.Error as exc:
            LOGGER.warning("Кэш LLM: ошибка чтения: %s", exc)
            return None
        return {
            "provider": row[0],
            "prompt_tokens": int(row[1] or 0),
            "completion_tokens": int(row[2] or 0),
            "response": str(row[3] or ""),
        }

    def put(
        self,
        key: str,
        provider: str,
        response: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        if not self.enabled or not response:
            return
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._lock, self._connect() as connection:
                connection.execute(
                    "INSERT OR REPLACE INTO llm_cache "
                    "(key, provider, prompt_tokens, completion_tokens, response, created_at, hits) "
                    "VALUES (?, ?, ?, ?, ?, ?, 0)",
                    (
                        key,
                        str(provider or ""),
                        int(prompt_tokens or 0),
                        int(completion_tokens or 0),
                        str(response),
                        now,
                    ),
                )
                self._purge_conn(connection)
        except sqlite3.Error as exc:
            LOGGER.warning("Кэш LLM: ошибка записи: %s", exc)

    def purge(self) -> int:
        """Удаляет устаревшие ответы; возвращает число удалённых строк."""
        if not self.enabled:
            return 0
        try:
            with self._lock, self._connect() as connection:
                return self._purge_conn(connection)
        except sqlite3.Error as exc:
            LOGGER.warning("Кэш LLM: ошибка очистки: %s", exc)
            return 0

    def stats(self) -> Dict[str, int]:
        if not self.enabled:
            return {"entries": 0, "hits": 0, "saved_tokens": 0}
        try:
            with self._lock, self._connect() as connection:
                row = connection.execute(
                    "SELECT COUNT(*), COALESCE(SUM(hits), 0), "
                    "COALESCE(SUM((prompt_tokens + completion_tokens) * hits), 0) FROM llm_cache"
                ).fetchone()
        except sqlite3.Error:
            return {"entries": 0, "hits": 0, "saved_tokens": 0}
        return {
            "entries": int(row[0] or 0),
            "hits": int(row[1] or 0),
            "saved_tokens": int(row[2] or 0),
        }

    def describe(self) -> str:
        data = self.stats()
        return "кэш LLM: {entries} ответов, {hits} попаданий, ~{saved} токенов сэкономлено".format(
            entries=data["entries"], hits=data["hits"], saved=data["saved_tokens"]
        )

    # -- внутреннее ----------------------------------------------------------
    def _purge_conn(self, connection: sqlite3.Connection) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=self.ttl_hours)).isoformat()
        cursor = connection.execute("DELETE FROM llm_cache WHERE created_at < ?", (cutoff,))
        return int(cursor.rowcount or 0)


def _parse_dt(value: Any) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


__all__ = ["LLMCache", "make_key"]
