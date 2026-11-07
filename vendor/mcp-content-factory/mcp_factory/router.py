"""Маршрутизатор моделей: роль → цепочка провайдеров, fallback, бюджет."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .config import RouteConfig
from .models import Completion, Provider
from .utils import extract_json


class AllProvidersFailed(RuntimeError):
    """Ни один провайдер в цепочке роли не ответил."""


class BudgetExceeded(RuntimeError):
    """Превышен лимит токенов на один запуск."""


@dataclass
class CallRecord:
    """Один вызов модели (успешный или нет) для лога и аналитики."""

    role: str
    provider: str
    model: str
    attempt: int
    ok: bool
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "provider": self.provider,
            "model": self.model,
            "attempt": self.attempt,
            "ok": self.ok,
            "latency_ms": self.latency_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "error": self.error,
        }


class ModelRouter:
    """Выполняет запросы к моделям по ролям.

    Пример: role="writer" → [{"provider": "ollama", "model": "qwen2.5:7b"},
    {"provider": "gemini", "model": "gemini-2.5-flash"}]. Если первый
    провайдер упал, пробуем следующий. Все вызовы пишутся в records.
    """

    def __init__(
        self,
        providers: Dict[str, Provider],
        routes: Dict[str, RouteConfig],
        budget_tokens: int = 0,
    ):
        self.providers = providers
        self.routes = routes
        self.budget_tokens = max(0, int(budget_tokens))
        self.records: List[CallRecord] = []
        self.used_tokens = 0
        # Параллельные ветки графа могут звать complete() одновременно.
        self._lock = threading.Lock()

    def _record(self, record: CallRecord) -> None:
        """Добавить запись о вызове (потокобезопасно)."""
        with self._lock:
            self.records.append(record)

    def has_role(self, role: str) -> bool:
        return role in self.routes

    def complete(self, role: str, messages: List[Dict[str, str]]) -> Completion:
        """Выполнить запрос по роли с fallback-цепочкой."""
        route = self.routes.get(role)
        if route is None:
            raise AllProvidersFailed("роль {!r} не объявлена в routes".format(role))

        errors: List[str] = []
        for attempt, reference in enumerate(route.chain, start=1):
            provider_name = reference["provider"]
            model_name = reference["model"]
            provider = self.providers.get(provider_name)
            if provider is None:
                record = CallRecord(
                    role=role,
                    provider=provider_name,
                    model=model_name,
                    attempt=attempt,
                    ok=False,
                    error="провайдер не создан",
                )
                self._record(record)
                errors.append("{}: провайдер не создан".format(provider_name))
                continue

            try:
                completion = provider.complete(
                    model=model_name,
                    messages=messages,
                    temperature=route.temperature,
                    max_tokens=route.max_tokens,
                    json_mode=route.json,
                )
            except Exception as exc:  # noqa: BLE001 — нужен fallback на любой сбой
                record = CallRecord(
                    role=role,
                    provider=provider_name,
                    model=model_name,
                    attempt=attempt,
                    ok=False,
                    error=str(exc)[:500],
                )
                self._record(record)
                errors.append("{}: {}".format(provider_name, exc))
                continue

            total = completion.total_tokens
            with self._lock:
                if self.budget_tokens and self.used_tokens + total > self.budget_tokens:
                    over_budget = True
                else:
                    self.used_tokens += total
                    over_budget = False
            if over_budget:
                record = CallRecord(
                    role=role,
                    provider=provider_name,
                    model=model_name,
                    attempt=attempt,
                    ok=False,
                    latency_ms=completion.latency_ms,
                    prompt_tokens=completion.prompt_tokens,
                    completion_tokens=completion.completion_tokens,
                    error="превышен бюджет токенов",
                )
                self._record(record)
                raise BudgetExceeded(
                    "бюджет {} токенов исчерпан (уже {})".format(
                        self.budget_tokens, self.used_tokens
                    )
                )

            self._record(
                CallRecord(
                    role=role,
                    provider=provider_name,
                    model=model_name,
                    attempt=attempt,
                    ok=True,
                    latency_ms=completion.latency_ms,
                    prompt_tokens=completion.prompt_tokens,
                    completion_tokens=completion.completion_tokens,
                )
            )
            return completion

        raise AllProvidersFailed(
            "роль {}: все провайдеры упали ({})".format(role, "; ".join(errors))
        )

    def complete_json(
        self, role: str, messages: List[Dict[str, str]]
    ) -> Tuple[Any, Completion]:
        """Выполнить запрос и распарсить JSON; одна попытка «починить» ответ."""
        last_error: Optional[Exception] = None
        working_messages = list(messages)
        for attempt in range(2):
            completion = self.complete(role, working_messages)
            try:
                data = extract_json(completion.text)
                if not isinstance(data, (dict, list)):
                    raise ValueError("JSON должен быть объектом или массивом")
                return data, completion
            except ValueError as exc:
                last_error = exc
                if attempt == 0:
                    working_messages = list(messages) + [
                        {
                            "role": "user",
                            "content": (
                                "Предыдущий ответ не был валидным JSON ({}). "
                                "Верни ТОЛЬКО валидный JSON без пояснений и markdown."
                            ).format(exc),
                        }
                    ]
                    continue
        raise AllProvidersFailed(
            "роль {}: не удалось получить JSON: {}".format(role, last_error)
        )

    def summary(self) -> Dict[str, Any]:
        """Сводка для run-лога."""
        calls = [record.as_dict() for record in self.records]
        failures = [call for call in calls if not call["ok"]]
        return {
            "calls": calls,
            "failures": len(failures),
            "used_tokens": self.used_tokens,
            "budget_tokens": self.budget_tokens,
            "by_role": {
                role: sum(1 for call in calls if call["role"] == role)
                for role in sorted({call["role"] for call in calls})
            },
        }

    def dump_json(self) -> str:
        return json.dumps(self.summary(), ensure_ascii=False, indent=2)
