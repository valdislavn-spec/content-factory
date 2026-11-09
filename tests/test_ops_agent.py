"""Тесты операционного агента: сбор данных, один LLM-вызов, фолбэки, клиенты."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from content_factory.agents.ops_agent import (  # noqa: E402
    analyze,
    build_client,
    collect_data,
    compact_data,
    heuristic_summary,
)
from content_factory.agents.tools import (  # noqa: E402
    TOOLS,
    call_tool,
    tool_distribution,
    tools_prompt,
)
from content_factory.config import Settings  # noqa: E402
from content_factory.nlp.llm import FallbackLLMClient, LLMClient  # noqa: E402


class ScriptedLLM(LLMClient):
    def __init__(self, answers):
        super().__init__(name="scripted", available=True, config={})
        self.answers = list(answers)
        self.calls = 0

    def _generate(self, prompt, system, max_tokens, temperature):
        self.calls += 1
        return self.answers.pop(0) if self.answers else ""


def fake_runner(name, args):
    return {
        "channels": [{"id": "ai-news", "title": "AI News"}],
        "growth": {"ok": True, "summary": "Всего: 3681 подп.\nCrypto: 3666"},
        "health": [{"name": "content-factory", "status": "success"}],
        "budget": {"tokens": {"total": 100, "limit": 700000}},
        "promo": {"outreach_rows": 2, "statuses": {"negotiating": 2}},
        "distribution": {
            "platforms": [{"platform": "Mastodon", "last": "success"}],
            "failing": [],
        },
    }[name]


def fake_data():
    return {
        "channels": [{"id": "ai-news"}],
        "growth": {"summary": "Всего: 3681 подп."},
        "health": [{"name": "content-factory", "status": "success"}],
        "budget": {"tokens": {"total": 100}},
        "promo": {"outreach_rows": 2, "statuses": {}},
        "distribution": {
            "platforms": [{"platform": "Mastodon", "last": "success"}],
            "failing": [],
        },
    }


class OpsAgentTests(unittest.TestCase):
    def test_collect_data_uses_all_tools(self) -> None:
        seen = []

        def runner(name, args):
            seen.append(name)
            return fake_runner(name, args)

        data = collect_data(runner)
        self.assertEqual(
            set(seen), {"channels", "growth", "health", "budget", "promo", "distribution"}
        )
        self.assertIn("channels", data)

    def test_analyze_returns_llm_text(self) -> None:
        client = ScriptedLLM(["Сводка: всё ок. 1) метрики 2) промо 3) бюджет"])
        text = analyze(client, "обход", {"channels": []})
        self.assertIn("Сводка", text)
        self.assertEqual(client.calls, 1)

    def test_heuristic_when_llm_empty(self) -> None:
        client = ScriptedLLM([""])
        self.assertEqual(analyze(client, "обход", {"channels": []}), "")
        summary = heuristic_summary(fake_data())
        self.assertIn("Оперативная сводка", summary)
        self.assertIn("Каналов: 1", summary)
        self.assertIn("проблемных: 0", summary)
        self.assertIn("Дистрибуция: 1", summary)

    def test_compact_data_truncates(self) -> None:
        big = {"channels": [{"id": "x" * 100} for _ in range(100)]}
        self.assertLessEqual(len(compact_data(big, limit=200)), 200)

    def test_compact_data_keeps_all_tools(self) -> None:
        compact = compact_data(fake_data())
        self.assertIn("ai-news", compact)
        self.assertIn("content-factory:success", compact)
        self.assertIn("Mastodon:success", compact)

    def test_build_client_without_gemini_uses_pollinations(self) -> None:
        settings = Settings.load(load_env=False)
        saved = os.environ.pop("GEMINI_API_KEY", None)
        try:
            client = build_client(settings)
        finally:
            if saved is not None:
                os.environ["GEMINI_API_KEY"] = saved
        self.assertTrue(client.available)
        self.assertEqual(client.name, "pollinations")

    def test_fallback_client_skips_failed_provider(self) -> None:
        class Failing(LLMClient):
            def __init__(self):
                super().__init__(name="failing", available=True, config={})

            def _generate(self, prompt, system, max_tokens, temperature):
                raise RuntimeError("quota")

        good = ScriptedLLM(["ответ"])
        client = FallbackLLMClient([Failing(), good])
        self.assertTrue(client.available)
        self.assertIn("ответ", client.generate("prompt"))
        self.assertEqual(client.name, "scripted")


class DistributionToolTests(unittest.TestCase):
    class Resp:
        def __init__(self, payload):
            self.payload = payload

        def read(self, *args, **kwargs):
            import json as _json

            return _json.dumps(self.payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def test_distribution_marks_failures(self) -> None:
        import os
        from unittest import mock

        payload = {"workflow_runs": [{"conclusion": "failure", "created_at": "2026-11-09T09:00:00Z"}]}
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "test"}, clear=False), mock.patch(
            "urllib.request.urlopen", return_value=self.Resp(payload)
        ):
            data = tool_distribution({})
        self.assertEqual(len(data["platforms"]), 6)
        self.assertIn("Mastodon", data["failing"])

    def test_distribution_without_token(self) -> None:
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {}, clear=True):
            data = tool_distribution({})
        self.assertIn("error", data)


class OpsToolsTests(unittest.TestCase):
    def test_tools_registry_shape(self) -> None:
        for name, item in TOOLS.items():
            self.assertTrue(callable(item["fn"]), name)
            self.assertTrue(item["desc"], name)
        prompt = tools_prompt()
        for name in TOOLS:
            self.assertIn(name, prompt)

    def test_unknown_tool_returns_error(self) -> None:
        self.assertIn("error", call_tool("missing", {}))

    def test_channels_tool_uses_settings(self) -> None:
        settings = Settings.load(load_env=False)

        class FakeChannel:
            enabled = True
            id = "ai-news"
            title = "AI News"
            language = "en"
            posts_per_day = 15
            telegram_chat_id = "@AINEWS0007"

        with mock.patch(
            "content_factory.agents.tools.Settings.load", return_value=settings
        ), mock.patch(
            "content_factory.agents.tools.load_network_channels", return_value=[FakeChannel()]
        ):
            rows = call_tool("channels", {})
        self.assertEqual(rows[0]["id"], "ai-news")
        self.assertEqual(rows[0]["username"], "AINEWS0007")


if __name__ == "__main__":
    unittest.main()
