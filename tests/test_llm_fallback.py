"""Тесты LLM-цепочки fallback: Groq → OpenRouter → SambaNova → … (без сети)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from content_factory.nlp.llm import (
    FallbackLLMClient,
    LimitedLLMClient,
    LLMClient,
    get_llm,
)


class FakeLLM(LLMClient):
    def __init__(self, name: str, text: str = "ответ", available: bool = True) -> None:
        super().__init__(name=name, available=available, config={})
        self.text = text
        self.calls = 0

    def _generate(self, prompt, system, max_tokens, temperature) -> str:
        self.calls += 1
        return self.text


class FallbackClientTests(unittest.TestCase):
    def test_uses_first_non_empty_answer(self):
        first = FakeLLM("groq", text="первый")
        second = FakeLLM("openrouter", text="второй")
        client = FallbackLLMClient([first, second])
        self.assertEqual(client.generate("prompt"), "первый")
        self.assertEqual(second.calls, 0)

    def test_falls_through_to_next_provider(self):
        first = FakeLLM("groq", text="")
        second = FakeLLM("openrouter", text="второй")
        client = FallbackLLMClient([first, second])
        self.assertEqual(client.generate("prompt"), "второй")
        self.assertEqual(first.calls, 1)
        self.assertEqual(second.calls, 1)

    def test_marks_unavailable_when_all_fail(self):
        client = FallbackLLMClient([FakeLLM("groq", text=""), FakeLLM("openrouter", text="")])
        self.assertEqual(client.generate("prompt"), "")
        self.assertFalse(client.available)

    def test_describe_lists_chain(self):
        client = FallbackLLMClient([FakeLLM("groq"), FakeLLM("openrouter")])
        described = client.describe()
        self.assertIn("groq", described)
        self.assertIn("openrouter", described)


def _settings(**llm):
    payload = {
        "provider": "groq",
        "fallback": ["openrouter", "sambanova"],
        "providers": {
            "groq": {"api_key_env": "GROQ_API_KEY"},
            "openrouter": {"api_key_env": "OPENROUTER_API_KEY"},
            "sambanova": {"api_key_env": "SAMBANOVA_API_KEY"},
            "huggingface": {"api_key_env": "HUGGINGFACE_API_KEY"},
        },
    }
    payload.update(llm)
    return SimpleNamespace(
        llm=payload,
        data_dir=Path(tempfile.gettempdir()) / "cf-llm-fallback-tests",
    )


class GetLlmFallbackTests(unittest.TestCase):
    def test_no_keys_returns_unavailable_primary(self):
        # Без ключей клиент недоступен, и конвейер сам уходит в extractive.
        with mock.patch.dict(
            os.environ,
            {"GROQ_API_KEY": "", "OPENROUTER_API_KEY": "", "SAMBANOVA_API_KEY": ""},
            clear=False,
        ):
            client = get_llm(_settings())
        self.assertEqual(client.name, "groq")
        self.assertFalse(client.available)
        self.assertEqual(client.generate("prompt"), "")

    def test_single_available_provider_returned_directly(self):
        with mock.patch.dict(
            os.environ,
            {"GROQ_API_KEY": "", "OPENROUTER_API_KEY": "key", "SAMBANOVA_API_KEY": ""},
            clear=False,
        ):
            client = get_llm(_settings())
        self.assertEqual(client.name, "openrouter")
        self.assertTrue(client.available)

    def test_huggingface_provider_available(self):
        with mock.patch.dict(
            os.environ,
            {
                "GROQ_API_KEY": "",
                "OPENROUTER_API_KEY": "",
                "SAMBANOVA_API_KEY": "",
                "HUGGINGFACE_API_KEY": "hf_key",
            },
            clear=False,
        ):
            client = get_llm(_settings(provider="huggingface"))
        self.assertEqual(client.name, "huggingface")
        self.assertTrue(client.available)

    def test_chain_built_when_multiple_providers_available(self):
        with mock.patch.dict(
            os.environ,
            {"GROQ_API_KEY": "key1", "OPENROUTER_API_KEY": "key2", "SAMBANOVA_API_KEY": ""},
            clear=False,
        ):
            client = get_llm(_settings())
        self.assertIsInstance(client, FallbackLLMClient)
        self.assertEqual([c.name for c in client.clients], ["groq", "openrouter"])

    def test_daily_budget_wraps_chain(self):
        with mock.patch.dict(
            os.environ,
            {"GROQ_API_KEY": "key1", "OPENROUTER_API_KEY": "key2", "SAMBANOVA_API_KEY": ""},
            clear=False,
        ):
            client = get_llm(_settings(daily_request_limit=5))
        self.assertIsInstance(client, LimitedLLMClient)
        self.assertIsInstance(client._inner, FallbackLLMClient)


if __name__ == "__main__":
    unittest.main()
