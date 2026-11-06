"""Тесты Ollama-провайдера: payload, num_ctx, деградация (без сети)."""

from __future__ import annotations

import unittest
from unittest import mock

from content_factory.nlp.llm import LLMError, OllamaLLM


class OllamaPayloadTests(unittest.TestCase):
    def test_payload_has_model_options_and_num_ctx(self):
        client = OllamaLLM(
            {
                "base_url": "http://127.0.0.1:11434",
                "model": "qwen3.5:9b",
                "num_ctx": 8192,
            }
        )
        captured = {}

        def fake_post_json(url, payload, headers=None, timeout=None):
            captured["url"] = url
            captured["payload"] = payload
            return {"response": "  готовый текст  "}

        with mock.patch("content_factory.nlp.llm._post_json", side_effect=fake_post_json):
            text = client.generate("промпт", system="система", max_tokens=123, temperature=0.2)

        self.assertEqual(text, "готовый текст")
        self.assertEqual(captured["url"], "http://127.0.0.1:11434/api/generate")
        payload = captured["payload"]
        self.assertEqual(payload["model"], "qwen3.5:9b")
        self.assertEqual(payload["system"], "система")
        self.assertEqual(payload["options"]["num_ctx"], 8192)
        self.assertEqual(payload["options"]["num_predict"], 123)
        self.assertAlmostEqual(payload["options"]["temperature"], 0.2)

    def test_num_ctx_not_sent_when_not_configured(self):
        client = OllamaLLM({"model": "qwen3.5:9b"})
        captured = {}

        def fake_post_json(url, payload, headers=None, timeout=None):
            captured["payload"] = payload
            return {"response": "ok"}

        with mock.patch("content_factory.nlp.llm._post_json", side_effect=fake_post_json):
            self.assertEqual(client.generate("промпт"), "ok")

        options = captured["payload"].get("options") or {}
        self.assertNotIn("num_ctx", options)

    def test_error_marks_client_unavailable(self):
        client = OllamaLLM({"model": "qwen3.5:9b"})
        self.assertTrue(client.available)
        with mock.patch(
            "content_factory.nlp.llm._post_json",
            side_effect=LLMError("сеть недоступна"),
        ):
            self.assertEqual(client.generate("промпт"), "")
        self.assertFalse(client.available)

    def test_think_false_is_sent_and_disables_reasoning(self):
        client = OllamaLLM({"model": "qwen3.5:9b", "think": False})
        captured = {}

        def fake_post_json(url, payload, headers=None, timeout=None):
            captured["payload"] = payload
            return {"response": "ok"}

        with mock.patch("content_factory.nlp.llm._post_json", side_effect=fake_post_json):
            self.assertEqual(client.generate("промпт"), "ok")
        self.assertIs(captured["payload"]["think"], False)

    def test_think_not_sent_when_not_configured(self):
        client = OllamaLLM({"model": "qwen3.5:9b"})
        captured = {}

        def fake_post_json(url, payload, headers=None, timeout=None):
            captured["payload"] = payload
            return {"response": "ok"}

        with mock.patch("content_factory.nlp.llm._post_json", side_effect=fake_post_json):
            client.generate("промпт")
        self.assertNotIn("think", captured["payload"])

    def test_env_host_overrides_yaml(self):
        with mock.patch.dict("os.environ", {"OLLAMA_HOST": "http://127.0.0.1:11999"}):
            client = OllamaLLM({"model": "qwen3.5:9b"})
        self.assertEqual(client.base_url, "http://127.0.0.1:11999")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
