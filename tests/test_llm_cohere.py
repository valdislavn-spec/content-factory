"""Cohere как OpenAI-совместимый провайдер: конфиг, fallback, доступность."""

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
)

EXPECTED_BASE_URL = "https://api.cohere.ai/compatibility/v1"


class CohereConfigTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings.load(load_env=False)

    def provider_config(self):
        return self.settings.llm["providers"]["cohere"]

    def test_provider_uses_openai_compatible_endpoint(self):
        config = self.provider_config()
        self.assertEqual(config["base_url"], EXPECTED_BASE_URL)
        self.assertEqual(config["api_key_env"], "COHERE_API_KEY")
        self.assertTrue(str(config["model"]).startswith("command"))

    def test_client_is_openai_compatible(self):
        client = _build_llm("cohere", self.settings)
        self.assertIsInstance(client, OpenAICompatibleLLM)
        self.assertEqual(client.base_url, EXPECTED_BASE_URL)
        self.assertEqual(client.model, self.provider_config()["model"])
        self.assertEqual(client.api_key_env, "COHERE_API_KEY")

    def test_cohere_is_in_fallback_chain(self):
        fallback = self.settings.llm.get("fallback") or []
        self.assertIn("cohere", fallback)

    def test_available_only_with_key(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COHERE_API_KEY", None)
            self.assertFalse(_has_key(self.settings, "cohere"))
        with patch.dict(os.environ, {"COHERE_API_KEY": "cohere_test"}):
            self.assertTrue(_has_key(self.settings, "cohere"))


if __name__ == "__main__":
    unittest.main()
