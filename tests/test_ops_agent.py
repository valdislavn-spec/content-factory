"""Тесты операционного агента: loop, JSON-протокол, инструменты, фолбэк."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from content_factory.agents.ops_agent import (  # noqa: E402
    _extract_json,
    heuristic_summary,
    run_agent,
)
from content_factory.agents.tools import TOOLS, call_tool, tools_prompt  # noqa: E402
from content_factory.config import Settings  # noqa: E402
from content_factory.nlp.llm import LLMClient  # noqa: E402


class ScriptedLLM(LLMClient):
    def __init__(self, answers):
        super().__init__(name="scripted", available=True, config={})
        self.answers = list(answers)
        self.calls = 0

    def _generate(self, prompt, system, max_tokens, temperature):
        self.calls += 1
        return self.answers.pop(0) if self.answers else ""


class OpsAgentLoopTests(unittest.TestCase):
    def test_tool_then_finish(self) -> None:
        client = ScriptedLLM(
            [
                '{"action":"channels","args":{}}',
                '{"action":"finish","args":{"text":"Готово: 6 каналов"}}',
            ]
        )
        calls = []

        def runner(name, args):
            calls.append(name)
            return [{"id": "ai-news"}]

        text = run_agent(client, "сводка", tool_runner=runner)
        self.assertEqual(text, "Готово: 6 каналов")
        self.assertEqual(calls, ["channels"])
        self.assertEqual(client.calls, 2)

    def test_invalid_json_is_retried(self) -> None:
        client = ScriptedLLM(["не JSON", '{"action":"finish","args":{"text":"ок"}}'])
        text = run_agent(client, "задача", tool_runner=lambda name, args: {})
        self.assertEqual(text, "ок")

    def test_unknown_tool_reported_to_model(self) -> None:
        captured = {}

        def runner(name, args):
            return {}

        client = ScriptedLLM(
            ['{"action":"nope","args":{}}', '{"action":"finish","args":{"text":"итог"}}']
        )
        self.assertEqual(run_agent(client, "t", tool_runner=runner), "итог")

    def test_max_steps_falls_back_to_heuristic(self) -> None:
        answers = ['{"action":"channels","args":{}}'] * 10
        client = ScriptedLLM(answers)
        tools = {"channels": {"fn": lambda args: [], "desc": "x"}}
        with mock.patch(
            "content_factory.agents.ops_agent.heuristic_summary", return_value="heuristic"
        ):
            text = run_agent(client, "t", max_steps=2, tool_runner=lambda name, args: [])
        self.assertEqual(text, "heuristic")

    def test_extract_json_handles_fences(self) -> None:
        self.assertEqual(_extract_json('```json\n{"a":1}\n```'), {"a": 1})
        self.assertIsNone(_extract_json("ничего"))
        self.assertIsNone(_extract_json("[1,2]"))


class OpsToolsTests(unittest.TestCase):
    def test_tools_registry_shape(self) -> None:
        for name, item in TOOLS.items():
            self.assertTrue(callable(item["fn"]), name)
            self.assertTrue(item["desc"], name)
        prompt = tools_prompt()
        for name in TOOLS:
            self.assertIn(name, prompt)

    def test_unknown_tool_returns_error(self) -> None:
        result = call_tool("missing", {})
        self.assertIn("error", result)

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

    def test_heuristic_works_without_llm(self) -> None:
        tool_runner = lambda name, args: (  # noqa: E731
            [{"id": "a"}] if name == "channels" else ({} if name == "budget" else [])
        )
        text = heuristic_summary(tool_runner)
        self.assertIn("Оперативная сводка", text)
        self.assertIn("Каналов: 1", text)


if __name__ == "__main__":
    unittest.main()
