"""Тесты суточного бюджета LLM и обёртки LimitedLLMClient (без сети)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from content_factory.nlp.budget import DailyBudget
from content_factory.nlp.llm import (
    ExtractiveLLM,
    LLMClient,
    LimitedLLMClient,
    get_llm,
)


class FakeLLM(LLMClient):
    """Клиент-заглушка: считает реальные вызовы ``_generate``."""

    def __init__(self, available: bool = True) -> None:
        super().__init__(name="fake", available=available, config={})
        self.calls = 0

    def _generate(self, prompt, system, max_tokens, temperature) -> str:
        self.calls += 1
        return "ответ {}".format(self.calls)


class DailyBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "data" / "llm_usage.json"

    def test_consumes_until_limit_then_denies(self) -> None:
        budget = DailyBudget(self.path, 2)
        self.assertEqual(budget.remaining(), 2)
        self.assertTrue(budget.try_consume())
        self.assertTrue(budget.try_consume())
        self.assertEqual(budget.used(), 2)
        self.assertEqual(budget.remaining(), 0)
        self.assertFalse(budget.try_consume())
        self.assertEqual(budget.used(), 2)

    def test_counter_persists_between_instances(self) -> None:
        self.assertTrue(DailyBudget(self.path, 5).try_consume())
        other = DailyBudget(self.path, 5)
        self.assertEqual(other.used(), 1)
        self.assertEqual(other.remaining(), 4)

    def test_resets_on_next_utc_day(self) -> None:
        clock = [datetime(2026, 11, 6, 23, 59, tzinfo=timezone.utc)]
        budget = DailyBudget(self.path, 1, clock=lambda: clock[0])
        self.assertTrue(budget.try_consume())
        self.assertEqual(budget.remaining(), 0)
        clock[0] = datetime(2026, 11, 7, 0, 1, tzinfo=timezone.utc)
        self.assertEqual(budget.used(), 0)
        self.assertEqual(budget.remaining(), 1)
        self.assertTrue(budget.try_consume())

    def test_zero_limit_is_unlimited(self) -> None:
        budget = DailyBudget(self.path, 0)
        for _ in range(50):
            self.assertTrue(budget.try_consume())
        self.assertTrue(budget.unlimited)
        self.assertIn("без ограничений", budget.describe())

    def test_broken_file_does_not_crash(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("не json", encoding="utf-8")
        budget = DailyBudget(self.path, 3)
        self.assertEqual(budget.used(), 0)
        self.assertTrue(budget.try_consume())


class LimitedClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.budget = DailyBudget(Path(self._tmp.name) / "llm_usage.json", 2)

    def test_generate_stops_after_daily_limit(self) -> None:
        inner = FakeLLM()
        client = LimitedLLMClient(inner, self.budget)
        self.assertTrue(client.available)
        self.assertEqual(client.generate("раз"), "ответ 1")
        self.assertEqual(client.generate("два"), "ответ 2")
        self.assertFalse(client.available)
        self.assertEqual(client.generate("три"), "")
        self.assertEqual(inner.calls, 2)  # сверх лимита модель не вызывается
        self.assertIn("2/2", client.describe())

    def test_unavailable_inner_does_not_spend_budget(self) -> None:
        inner = FakeLLM(available=False)
        client = LimitedLLMClient(inner, self.budget)
        self.assertFalse(client.available)
        self.assertEqual(client.generate("раз"), "")
        self.assertEqual(self.budget.used(), 0)

    def test_empty_prompt_not_counted(self) -> None:
        client = LimitedLLMClient(FakeLLM(), self.budget)
        self.assertEqual(client.generate(""), "")
        self.assertEqual(self.budget.used(), 0)


class GetLlmBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_dir = Path(self._tmp.name) / "data"

    def _settings(self, **llm):
        payload = {"provider": "openai_compatible"}
        payload.update(llm)
        return SimpleNamespace(llm=payload, data_dir=self.data_dir)

    def test_wraps_available_client_when_limit_set(self) -> None:
        client = get_llm(self._settings(daily_request_limit=3))
        self.assertIsInstance(client, LimitedLLMClient)
        self.assertEqual(client.name, "openai_compatible")
        self.assertEqual(client.budget.limit, 3)

    def test_no_wrap_without_limit(self) -> None:
        client = get_llm(self._settings())
        self.assertNotIsInstance(client, LimitedLLMClient)
        self.assertEqual(client.name, "openai_compatible")

    def test_extractive_is_never_wrapped(self) -> None:
        client = get_llm(self._settings(provider="extractive", daily_request_limit=10))
        self.assertIsInstance(client, ExtractiveLLM)
        self.assertNotIsInstance(client, LimitedLLMClient)


if __name__ == "__main__":
    unittest.main()
