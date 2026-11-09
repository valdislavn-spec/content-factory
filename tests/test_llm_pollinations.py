"""Pollinations: бесплатный OpenAI-совместимый провайдер без ключа."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

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

EXPECTED_BASE_URL = "https://text.pollinations.ai/openai"


class PollinationsProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings.load(load_env=False)

    def test_defaults(self) -> None:
        config = _named_provider_config(self.settings, "pollinations")
        self.assertEqual(config["base_url"], EXPECTED_BASE_URL)
        self.assertEqual(config["api_key_env"], "")
        self.assertEqual(config["model"], "openai")

    def test_client_builds_and_is_always_available(self) -> None:
        client = _build_llm("pollinations", self.settings)
        self.assertIsInstance(client, OpenAICompatibleLLM)
        self.assertEqual(client.base_url, EXPECTED_BASE_URL)
        self.assertTrue(client.available)
        self.assertTrue(_has_key(self.settings, "pollinations"))


if __name__ == "__main__":
    unittest.main()
