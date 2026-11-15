"""Параметры payload для reasoning-моделей Groq."""
from __future__ import annotations

import os
import unittest
from unittest import mock

from content_factory.nlp.llm import OpenAICompatibleLLM


class OpenAICompatiblePayloadTests(unittest.TestCase):
    def test_min_max_tokens_and_extra_body(self) -> None:
        captured = {}

        def fake_post_json(url, payload, headers=None, timeout=None):
            captured["payload"] = payload
            return {"choices": [{"message": {"content": "OK"}}]}

        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "test"}):
            client = OpenAICompatibleLLM(
                {
                    "base_url": "https://api.groq.com/openai/v1",
                    "api_key_env": "GROQ_API_KEY",
                    "model": "openai/gpt-oss-120b",
                    "min_max_tokens": 400,
                    "extra_body": {"reasoning_effort": "low"},
                }
            )
        with mock.patch("content_factory.nlp.llm._post_json", side_effect=fake_post_json):
            self.assertEqual(
                client.generate("prompt", system="system", max_tokens=80, temperature=0.2),
                "OK",
            )
        payload = captured["payload"]
        self.assertEqual(payload["max_tokens"], 400)
        self.assertEqual(payload["reasoning_effort"], "low")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
