"""Тесты Dify-провайдера: фабрика, payload и разбор SSE (unittest, без сети)."""

from __future__ import annotations

import io
import json
import os
import unittest
import urllib.error
from types import SimpleNamespace
from unittest import mock

from content_factory.config import ConfigError, _validate_settings
from content_factory.nlp.llm import DifyLLM, get_llm

DIFY_URL = "https://api.dify.ai/v1/chat-messages"


def _sse(*events) -> bytes:
    """Собирает тело SSE-ответа Dify из словарей-событий."""
    chunks = []
    for event in events:
        chunks.append("data: " + json.dumps(event, ensure_ascii=False) + "\n\n")
    return "".join(chunks).encode("utf-8")


class FakeResponse:
    """Минимальный ответ urlopen: итерируется по строкам, знает headers."""

    def __init__(self, body: bytes, content_type: str = "text/event-stream") -> None:
        self._lines = body.splitlines(keepends=True)
        self.headers = {"Content-Type": content_type}
        self.closed = False

    def __iter__(self):
        return iter(self._lines)

    def read(self) -> bytes:
        return b"".join(self._lines)

    def close(self) -> None:
        self.closed = True


def _http_error(status: int, payload: dict) -> urllib.error.HTTPError:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return urllib.error.HTTPError(
        DIFY_URL, status, "Bad Request", hdrs=None, fp=io.BytesIO(body)
    )


class DifyClientTest(unittest.TestCase):
    def _client(self, **config) -> DifyLLM:
        base = {"timeout": 10}
        base.update(config)
        with mock.patch.dict(
            os.environ,
            {"DIFY_API_KEY": "app-test-key", "DIFY_BASE_URL": ""},
            clear=False,
        ):
            return DifyLLM(base)

    def _generate(self, client: DifyLLM, prompt: str = "текст", system: str = "система"):
        with mock.patch.dict(
            os.environ, {"DIFY_API_KEY": "app-test-key", "DIFY_BASE_URL": ""}, clear=False
        ):
            return client.generate(prompt, system=system)

    # -- фабрика ---------------------------------------------------------
    def test_factory_without_key_is_unavailable(self):
        with mock.patch.dict(
            os.environ,
            {"DIFY_API_KEY": "", "DIFY_BASE_URL": ""},
            clear=False,
        ):
            llm = get_llm(SimpleNamespace(llm={"provider": "dify"}))
        self.assertEqual(llm.name, "dify")
        self.assertFalse(llm.available)
        self.assertEqual(llm.generate("любой промпт"), "")

    def test_factory_with_key_builds_client(self):
        settings = SimpleNamespace(
            llm={
                "provider": "dify",
                "timeout": 42,
                "dify": {"app_mode": "chat", "base_url": "https://example.com/v1"},
            }
        )
        with mock.patch.dict(
            os.environ,
            {"DIFY_API_KEY": "app-key", "DIFY_BASE_URL": ""},
            clear=False,
        ):
            llm = get_llm(settings)
        self.assertEqual(llm.name, "dify")
        self.assertTrue(llm.available)
        self.assertEqual(llm.base_url, "https://example.com/v1")
        self.assertEqual(llm.app_mode, "chat")
        self.assertEqual(llm.timeout, 42)

    def test_unknown_app_mode_falls_back_to_chat(self):
        client = self._client(app_mode="weird")
        self.assertEqual(client.app_mode, "chat")

    # -- chat-messages ---------------------------------------------------
    def test_chat_stream_merges_chunks_and_sends_system(self):
        body = _sse(
            {"event": "message", "answer": "При"},
            {"event": "message", "answer": "вет, мир"},
            {"event": "message_end", "metadata": {}},
        )
        response = FakeResponse(body)
        client = self._client()
        with mock.patch(
            "content_factory.nlp.llm.urllib.request.urlopen", return_value=response
        ) as urlopen:
            text = self._generate(client)
        self.assertEqual(text, "Привет, мир")
        request = urlopen.call_args[0][0]
        self.assertEqual(request.full_url, DIFY_URL)
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["query"], "система\n\nтекст")
        self.assertEqual(payload["response_mode"], "streaming")
        self.assertEqual(payload["user"], "content-factory")
        self.assertEqual(payload["inputs"], {})
        self.assertEqual(request.headers.get("Authorization"), "Bearer app-test-key")
        self.assertTrue(response.closed)

    def test_agent_app_uses_final_message_instead_of_chunks(self):
        body = _sse(
            {"event": "agent_message", "answer": "Чер"},
            {"event": "agent_message", "answer": "новик"},
            {"event": "message", "answer": "Черновик готов."},
            {"event": "message_end"},
        )
        client = self._client()
        with mock.patch(
            "content_factory.nlp.llm.urllib.request.urlopen",
            return_value=FakeResponse(body),
        ):
            self.assertEqual(self._generate(client), "Черновик готов.")

    def test_agent_app_without_final_message_joins_agent_chunks(self):
        body = _sse(
            {"event": "agent_message", "answer": "Го"},
            {"event": "agent_message", "answer": "тово"},
            {"event": "message_end"},
        )
        client = self._client()
        with mock.patch(
            "content_factory.nlp.llm.urllib.request.urlopen",
            return_value=FakeResponse(body),
        ):
            self.assertEqual(self._generate(client), "Готово")

    def test_message_replace_overwrites_answer(self):
        body = _sse(
            {"event": "message", "answer": "плохой"},
            {"event": "message_replace", "answer": "хороший"},
            {"event": "message_end"},
        )
        client = self._client()
        with mock.patch(
            "content_factory.nlp.llm.urllib.request.urlopen",
            return_value=FakeResponse(body),
        ):
            self.assertEqual(self._generate(client), "хороший")

    def test_system_can_be_disabled(self):
        body = _sse(
            {"event": "message", "answer": "ок"},
            {"event": "message_end"},
        )
        client = self._client(include_system=False)
        with mock.patch(
            "content_factory.nlp.llm.urllib.request.urlopen",
            return_value=FakeResponse(body),
        ) as urlopen:
            self.assertEqual(self._generate(client), "ок")
        payload = json.loads(urlopen.call_args[0][0].data.decode("utf-8"))
        self.assertEqual(payload["query"], "текст")

    def test_custom_inputs_are_passed(self):
        body = _sse(
            {"event": "message", "answer": "ок"},
            {"event": "message_end"},
        )
        client = self._client(inputs={"channel": "tech-ai"})
        with mock.patch(
            "content_factory.nlp.llm.urllib.request.urlopen",
            return_value=FakeResponse(body),
        ) as urlopen:
            self._generate(client)
        payload = json.loads(urlopen.call_args[0][0].data.decode("utf-8"))
        self.assertEqual(payload["inputs"], {"channel": "tech-ai"})

    # -- ошибки ----------------------------------------------------------
    def test_error_event_returns_empty_and_marks_client_unavailable(self):
        body = _sse({"event": "error", "code": "provider_quota_exceeded", "message": "no quota"})
        client = self._client()
        with mock.patch(
            "content_factory.nlp.llm.urllib.request.urlopen",
            return_value=FakeResponse(body),
        ):
            with self.assertLogs("content_factory.nlp.llm", level="WARNING"):
                self.assertEqual(self._generate(client), "")
        self.assertFalse(client.available)

    def test_http_error_returns_empty_and_includes_dify_error(self):
        client = self._client()
        error = _http_error(400, {"code": "not_chat_app", "message": "Please check app mode"})
        with mock.patch(
            "content_factory.nlp.llm.urllib.request.urlopen", side_effect=error
        ):
            with self.assertLogs("content_factory.nlp.llm", level="WARNING") as logs:
                self.assertEqual(self._generate(client), "")
        self.assertFalse(client.available)
        joined = "\n".join(logs.output)
        self.assertIn("not_chat_app", joined)
        self.assertIn("app_mode", joined)

    def test_stream_without_message_end_is_rejected(self):
        body = _sse({"event": "message", "answer": "обрезано"})
        client = self._client()
        with mock.patch(
            "content_factory.nlp.llm.urllib.request.urlopen",
            return_value=FakeResponse(body),
        ):
            with self.assertLogs("content_factory.nlp.llm", level="WARNING") as logs:
                self.assertEqual(self._generate(client), "")
        self.assertIn("message_end", "\n".join(logs.output))

    def test_json_blocking_response_is_accepted(self):
        # Прокси/сервер может проигнорировать streaming и вернуть обычный JSON.
        response = FakeResponse(
            json.dumps({"answer": "json-ответ"}, ensure_ascii=False).encode("utf-8"),
            content_type="application/json",
        )
        client = self._client()
        with mock.patch(
            "content_factory.nlp.llm.urllib.request.urlopen", return_value=response
        ):
            self.assertEqual(self._generate(client), "json-ответ")

    # -- completion-messages (Text Generator) ----------------------------
    def test_completion_app_mode_sends_query_inside_inputs(self):
        body = _sse(
            {"event": "message", "answer": "готово"},
            {"event": "message_end"},
        )
        client = self._client(app_mode="completion")
        with mock.patch(
            "content_factory.nlp.llm.urllib.request.urlopen",
            return_value=FakeResponse(body),
        ) as urlopen:
            self.assertEqual(self._generate(client), "готово")
        request = urlopen.call_args[0][0]
        self.assertEqual(request.full_url, "https://api.dify.ai/v1/completion-messages")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["inputs"], {"query": "система\n\nтекст"})
        self.assertNotIn("query", payload)

    def test_completion_app_legacy_query_field(self):
        body = _sse(
            {"event": "message", "answer": "готово"},
            {"event": "message_end"},
        )
        client = self._client(app_mode="completion", query_input="")
        with mock.patch(
            "content_factory.nlp.llm.urllib.request.urlopen",
            return_value=FakeResponse(body),
        ) as urlopen:
            self._generate(client)
        payload = json.loads(urlopen.call_args[0][0].data.decode("utf-8"))
        self.assertEqual(payload["query"], "система\n\nтекст")


class DifyConfigValidationTest(unittest.TestCase):
    def test_dify_provider_and_mode_are_allowed(self):
        _validate_settings({"llm": {"provider": "dify", "dify": {"app_mode": "chat"}}})
        _validate_settings(
            {"llm": {"provider": "dify", "dify": {"app_mode": "completion"}}}
        )

    def test_unknown_dify_app_mode_is_rejected(self):
        with self.assertRaises(ConfigError):
            _validate_settings(
                {"llm": {"provider": "dify", "dify": {"app_mode": "workflow"}}}
            )

    def test_unknown_provider_still_rejected(self):
        with self.assertRaises(ConfigError):
            _validate_settings({"llm": {"provider": "difyy"}})


if __name__ == "__main__":
    unittest.main()
