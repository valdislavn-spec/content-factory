"""Тесты учёта токенов LLM: реальный usage, оценка, суточный сброс, кэш-попадания."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from content_factory.nlp.tokens import (
    TokenTracker,
    configure,
    estimate_tokens,
    get_tracker,
    record_usage,
)

FIXED = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


class EstimateTokensTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(estimate_tokens(""), 0)

    def test_russian_estimate(self):
        text = "а" * 330
        self.assertGreaterEqual(estimate_tokens(text, "ru"), 100)
        self.assertLessEqual(estimate_tokens(text, "ru"), 110)

    def test_english_estimate_lower_than_russian(self):
        text = "a" * 400
        self.assertLess(estimate_tokens(text, "en"), estimate_tokens(text, "ru"))


class TokenTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "llm_tokens.json"
        self.now = FIXED
        self.tracker = TokenTracker(self.path, clock=lambda: self.now)

    def test_record_totals_and_persistence(self):
        self.tracker.record("ollama", 100, 50)
        self.tracker.record("ollama", 200, 25)
        today = self.tracker.today()
        self.assertEqual(today["calls"], 2)
        self.assertEqual(today["prompt_tokens"], 300)
        self.assertEqual(today["completion_tokens"], 75)
        self.assertEqual(today["total_tokens"], 375)
        self.assertEqual(today["by_provider"]["ollama"]["calls"], 2)
        # Новый экземпляр на том же файле видит те же данные (как новый прогон завода).
        same_day = TokenTracker(self.path, clock=lambda: self.now)
        self.assertEqual(same_day.today()["total_tokens"], 375)

    def test_new_day_resets(self):
        self.tracker.record("ollama", 999, 1)
        self.now = FIXED + timedelta(days=1)
        self.assertEqual(self.tracker.today()["total_tokens"], 0)

    def test_cache_hit_is_counted_separately(self):
        self.tracker.record("ollama", 10, 5)
        self.tracker.record_cache_hit("ollama", saved_tokens=90)
        today = self.tracker.today()
        self.assertEqual(today["cache_hits"], 1)
        self.assertEqual(today["cache_saved_tokens"], 90)
        self.assertIn("кэш", self.tracker.describe())


class RecordUsageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "llm_tokens.json"
        configure(self.path)

    def test_real_usage_wins(self):
        record_usage("ollama", {"prompt_tokens": 111, "completion_tokens": 22}, "промпт", "ответ")
        today = get_tracker().today()
        self.assertEqual(today["prompt_tokens"], 111)
        self.assertEqual(today["completion_tokens"], 22)
        self.assertEqual(today["estimated_calls"], 0)

    def test_estimate_when_usage_missing(self):
        record_usage("dify", None, "а" * 330, "б" * 66)
        today = get_tracker().today()
        self.assertGreater(today["prompt_tokens"], 0)
        self.assertGreater(today["completion_tokens"], 0)
        self.assertEqual(today["estimated_calls"], 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
