"""Тесты кэша ответов LLM и обёртки CachedLLMClient (без сети)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from content_factory.nlp.llm import CachedLLMClient, LLMClient
from content_factory.nlp.llm_cache import LLMCache, make_key
from content_factory.nlp.tokens import TokenTracker, configure, get_tracker


class FakeInner(LLMClient):
    def __init__(self, text: str = "ответ модели") -> None:
        super().__init__(name="fake", available=True, config={})
        self.text = text
        self.calls = 0

    def _generate(self, prompt, system, max_tokens, temperature) -> str:
        self.calls += 1
        self.last_usage = {"prompt_tokens": 100, "completion_tokens": 20}
        return self.text


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def _cache(self, ttl=168):
        return LLMCache(self.dir / "cache.sqlite3", ttl_hours=ttl)

    def test_key_depends_on_everything_important(self):
        base = make_key("ollama", "sys", "prompt", 500, 0.3)
        self.assertEqual(base, make_key("ollama", "sys", "prompt", 500, 0.3))
        self.assertNotEqual(base, make_key("ollama", "sys", "prompt2", 500, 0.3))
        self.assertNotEqual(base, make_key("ollama", "sys2", "prompt", 500, 0.3))
        self.assertNotEqual(base, make_key("openai", "sys", "prompt", 500, 0.3))
        self.assertNotEqual(base, make_key("ollama", "sys", "prompt", 300, 0.3))
        self.assertNotEqual(base, make_key("ollama", "sys", "prompt", 500, 0.7))

    def test_put_get_and_stats(self):
        cache = self._cache()
        key = make_key("ollama", "sys", "prompt", 500, 0.3)
        self.assertIsNone(cache.get(key))
        cache.put(key, "ollama", "ответ", 100, 20)
        hit = cache.get(key)
        self.assertEqual(hit["response"], "ответ")
        self.assertEqual(hit["prompt_tokens"], 100)
        cache.get(key)
        stats = cache.stats()
        self.assertEqual(stats["entries"], 1)
        self.assertGreaterEqual(stats["hits"], 2)

    def test_expired_entry_is_not_returned(self):
        cache = self._cache(ttl=1)
        key = make_key("ollama", "sys", "prompt", 500, 0.3)
        cache.put(key, "ollama", "ответ", 10, 5)
        # «Старим» запись на двое суток.
        with cache._lock, cache._connect() as connection:
            old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
            connection.execute("UPDATE llm_cache SET created_at = ?", (old,))
        self.assertIsNone(cache.get(key))

    def test_ttl_zero_disables_cache(self):
        cache = self._cache(ttl=0)
        self.assertFalse(cache.enabled)
        cache.put("k", "ollama", "ответ")
        self.assertIsNone(cache.get("k"))


class CachedClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        configure(self.dir / "llm_tokens.json")
        self.cache = LLMCache(self.dir / "cache.sqlite3", ttl_hours=168)

    def test_second_identical_prompt_comes_from_cache(self):
        inner = FakeInner()
        client = CachedLLMClient(inner, self.cache)
        first = client.generate("промпт", system="система", max_tokens=100)
        second = client.generate("промпт", system="система", max_tokens=100)
        self.assertEqual(first, second)
        self.assertEqual(inner.calls, 1)  # второй раз модель не вызывалась
        self.assertTrue(client.last_usage.get("cached"))
        self.assertEqual(get_tracker().today()["cache_hits"], 1)

    def test_different_prompt_goes_to_model(self):
        inner = FakeInner()
        client = CachedLLMClient(inner, self.cache)
        client.generate("промпт 1")
        client.generate("промпт 2")
        self.assertEqual(inner.calls, 2)

    def test_disabled_cache_passes_through(self):
        inner = FakeInner()
        client = CachedLLMClient(inner, LLMCache(self.dir / "c2.sqlite3", ttl_hours=0))
        client.generate("промпт")
        client.generate("промпт")
        self.assertEqual(inner.calls, 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
