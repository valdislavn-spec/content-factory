"""Тесты маршрутизации LLM по этапам, автопереключения и суточных лимитов."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from content_factory import config as config_module
from content_factory.nlp.llm import FallbackLLMClient, LLMClient, get_llm


class FakeLLM(LLMClient):
    """Клиент-заглушка: возвращает собственное имя и считает вызовы."""

    def __init__(self, name: str = "fake", available: bool = True) -> None:
        super().__init__(name=name, available=available, config={})
        self.calls = 0

    def _generate(self, prompt, system, max_tokens, temperature) -> str:
        self.calls += 1
        return "ответ-{}".format(self.name)


def _settings(tmpdir: str, **llm_overrides):
    payload = {
        "provider": "groq",
        "fallback": ["openrouter"],
        "providers": {
            "groq": {"api_key_env": "GROQ_API_KEY"},
            "openrouter": {"api_key_env": "OPENROUTER_API_KEY"},
            "cloudflare": {"api_key_env": "CLOUDFLARE_API_TOKEN"},
            "deepseek_chat": {"api_key_env": "DEEPSEEK_API_KEY"},
            "cohere": {"api_key_env": "COHERE_API_KEY"},
        },
        "stage_routes": {
            "analysis": {"provider": "cloudflare", "fallback": ["cohere"]},
            "generation": {"provider": "deepseek_chat", "fallback": ["groq"]},
        },
        "provider_limits": {},
    }
    payload.update(llm_overrides)
    return SimpleNamespace(llm=payload, data_dir=Path(tmpdir))


class StageRouteTests(unittest.TestCase):
    def _build(self, requested):
        def fake_build(name, settings):
            requested.append(name)
            return FakeLLM(name)

        return fake_build

    def test_generation_uses_its_own_provider_and_fallback(self):
        requested = []
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(tmp)
            with mock.patch(
                "content_factory.nlp.llm._build_llm",
                side_effect=self._build(requested),
            ):
                client = get_llm(settings, stage="generation")
        self.assertEqual(client.name, "deepseek_chat")
        self.assertEqual(requested, ["deepseek_chat", "groq"])

    def test_analysis_uses_free_provider(self):
        requested = []
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(tmp)
            with mock.patch(
                "content_factory.nlp.llm._build_llm",
                side_effect=self._build(requested),
            ):
                client = get_llm(settings, stage="analysis")
        self.assertEqual(client.name, "cloudflare")
        self.assertEqual(requested, ["cloudflare", "cohere"])

    def test_without_stage_uses_general_chain(self):
        requested = []
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(tmp)
            with mock.patch(
                "content_factory.nlp.llm._build_llm",
                side_effect=self._build(requested),
            ):
                client = get_llm(settings)
        self.assertEqual(client.name, "groq")
        self.assertEqual(requested, ["groq", "openrouter"])


class ProviderLimitFailoverTests(unittest.TestCase):
    def test_exhausted_provider_switches_to_next(self):
        clients = {}

        def fake_build(name, settings):
            clients[name] = FakeLLM(name)
            return clients[name]

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(
                tmp,
                stage_routes={
                    "generation": {"provider": "groq", "fallback": ["deepseek_chat"]}
                },
                provider_limits={"groq": 1},
            )
            with mock.patch(
                "content_factory.nlp.llm._build_llm", side_effect=fake_build
            ):
                client = get_llm(settings, stage="generation")
                first = client.generate("первый")
                second = client.generate("второй")

        self.assertEqual(first, "ответ-groq")
        self.assertEqual(second, "ответ-deepseek_chat")
        self.assertEqual(clients["groq"].calls, 1)
        self.assertEqual(clients["deepseek_chat"].calls, 1)

    def test_no_limits_keeps_single_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(
                tmp,
                stage_routes={"generation": {"provider": "groq", "fallback": []}},
            )
            with mock.patch(
                "content_factory.nlp.llm._build_llm",
                side_effect=lambda name, settings: FakeLLM(name),
            ) as builder:
                client = get_llm(settings, stage="generation")
        self.assertEqual(client.name, "groq")
        self.assertEqual(builder.call_count, 1)


class SettingsValidationTests(unittest.TestCase):
    def _base(self):
        return {
            "llm": {
                "provider": "cloudflare",
                "providers": {"cloudflare": {"api_key_env": "CLOUDFLARE_API_TOKEN"}},
            }
        }

    def test_unknown_stage_provider_rejected(self):
        payload = self._base()
        payload["llm"]["stage_routes"] = {"analysis": {"provider": "nope"}}
        with self.assertRaises(config_module.ConfigError):
            config_module._validate_settings(payload)

    def test_invalid_provider_limit_rejected(self):
        payload = self._base()
        payload["llm"]["provider_limits"] = {"cloudflare": "много"}
        with self.assertRaises(config_module.ConfigError):
            config_module._validate_settings(payload)

    def test_valid_stage_routes_pass(self):
        payload = self._base()
        payload["llm"]["stage_routes"] = {
            "analysis": {"provider": "cloudflare", "fallback": ["cloudflare"]},
            "generation": {"provider": "cloudflare", "fallback": []},
        }
        payload["llm"]["provider_limits"] = {"cloudflare": 150}
        config_module._validate_settings(payload)  # не должно бросить

    def test_demo_settings_are_offline(self):
        from content_factory.config import Settings
        from content_factory.pipeline import demo_settings

        settings = Settings.load(load_env=False)
        demo = demo_settings(settings)
        self.assertEqual(demo.llm.get("provider"), "extractive")
        self.assertEqual(demo.llm.get("stage_routes"), {})
        self.assertEqual(demo.llm.get("fallback"), [])
        self.assertEqual(demo.llm.get("daily_request_limit"), 0)


if __name__ == "__main__":
    unittest.main()
