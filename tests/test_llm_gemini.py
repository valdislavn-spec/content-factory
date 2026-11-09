"""Gemini как OpenAI-совместимый провайдер (ключ AI Studio).

Проверяет дефолты имени провайдера в коде (без правок settings.yaml):
endpoint, имя env-переменной, модель и поведение при отсутствии ключа.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from content_factory.config import Settings  # noqa: E402
from content_factory.nlp.llm import (  # noqa: E402
    OpenAICompatibleLLM,
    _build_llm,
    _has_key,
    _named_provider_config,
)

EXPECTED_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


class GeminiProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings.load(load_env=False)

    def test_defaults(self) -> None:
        config = _named_provider_config(self.settings, "gemini")
        self.assertEqual(config["base_url"], EXPECTED_BASE_URL)
        self.assertEqual(config["api_key_env"], "GEMINI_API_KEY")
        self.assertTrue(str(config["model"]).startswith("gemini"))

    def test_builds_openai_compatible_client(self) -> None:
        client = _build_llm("gemini", self.settings)
        self.assertIsInstance(client, OpenAICompatibleLLM)
        self.assertEqual(client.base_url, EXPECTED_BASE_URL)
        self.assertEqual(client.api_key_env, "GEMINI_API_KEY")
        self.assertTrue(str(client.model).startswith("gemini"))

    def test_available_only_with_key(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            self.assertFalse(_has_key(self.settings, "gemini"))
        with patch.dict(os.environ, {"GEMINI_API_KEY": "gemini_test"}):
            self.assertTrue(_has_key(self.settings, "gemini"))


if __name__ == "__main__":
    unittest.main()
