"""Тесты клиента Dify Workflow API и команды dify-apps (без сети)."""

from __future__ import annotations

import json
import os
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from content_factory.integrations.dify_workflow import (
    DifyWorkflowClient,
    DifyWorkflowError,
)

BASE = "https://api.dify.ai/v1"


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload).encode("utf-8")
        self.status = 200

    def read(self, *args, **kwargs) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:
        return False


def _http_error(status: int, payload: dict) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        BASE + "/workflows/run",
        status,
        "Error",
        hdrs=None,
        fp=__import__("io").BytesIO(json.dumps(payload).encode("utf-8")),
    )


class DifyWorkflowClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = DifyWorkflowClient("app-test-key", base_url=BASE, timeout=5)

    def _patch(self, payload):
        return mock.patch(
            "content_factory.integrations.dify_workflow.urllib.request.urlopen",
            return_value=FakeResponse(payload),
        )

    def test_info_and_parameters(self) -> None:
        with self._patch({"name": "Research", "mode": "workflow"}):
            info = self.client.info()
        self.assertEqual(info["mode"], "workflow")
        with self._patch(
            {
                "user_input_form": [
                    {"text-input": {"variable": "channel"}},
                    {"text-input": {"variable": "topic"}},
                ]
            }
        ):
            self.assertEqual(self.client.input_variables(), ["channel", "topic"])

    def test_run_returns_outputs(self) -> None:
        payload = {
            "task_id": "t1",
            "data": {
                "status": "succeeded",
                "outputs": {"draft": "English draft text"},
            },
        }
        with self._patch(payload):
            data = self.client.run({"channel": "tech", "topic": "AI"})
            self.assertEqual(self.client.outputs(data), {"draft": "English draft text"})
            self.assertEqual(
                self.client.run_text({"topic": "AI"}, output_key="draft"),
                "English draft text",
            )

    def test_empty_outputs_mentions_end_node(self) -> None:
        payload = {"data": {"status": "succeeded", "outputs": {}}}
        with self._patch(payload):
            with self.assertRaises(DifyWorkflowError) as ctx:
                self.client.run_text({"topic": "AI"})
        self.assertIn("End", str(ctx.exception))

    def test_missing_output_key_lists_available(self) -> None:
        payload = {"data": {"status": "succeeded", "outputs": {"text": "x"}}}
        with self._patch(payload):
            with self.assertRaises(DifyWorkflowError) as ctx:
                self.client.run_text({}, output_key="draft")
        message = str(ctx.exception)
        self.assertIn("draft", message)
        self.assertIn("text", message)

    def test_failed_status_raises(self) -> None:
        payload = {"data": {"status": "failed", "error": "boom", "outputs": {}}}
        with self._patch(payload):
            with self.assertRaises(DifyWorkflowError) as ctx:
                self.client.run({})
        self.assertIn("failed", str(ctx.exception))
        self.assertIn("boom", str(ctx.exception))

    def test_http_error_is_wrapped(self) -> None:
        error = _http_error(400, {"code": "app_unavailable", "message": "off"})
        with mock.patch(
            "content_factory.integrations.dify_workflow.urllib.request.urlopen",
            side_effect=error,
        ):
            with self.assertRaises(DifyWorkflowError) as ctx:
                self.client.info()
        self.assertIn("400", str(ctx.exception))
        self.assertIn("app_unavailable", str(ctx.exception))

    def test_request_uses_bearer_token_and_endpoint(self) -> None:
        with mock.patch(
            "content_factory.integrations.dify_workflow.urllib.request.urlopen",
            return_value=FakeResponse({"data": {"status": "succeeded", "outputs": {"a": "b"}}}),
        ) as urlopen:
            self.client.run({"topic": "x"})
        request = urlopen.call_args[0][0]
        self.assertEqual(request.full_url, BASE + "/workflows/run")
        self.assertEqual(request.headers.get("Authorization"), "Bearer app-test-key")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["inputs"], {"topic": "x"})
        self.assertEqual(body["response_mode"], "blocking")


if __name__ == "__main__":
    unittest.main()
