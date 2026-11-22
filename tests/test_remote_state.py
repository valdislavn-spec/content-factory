"""D1 state/queue client tests without network."""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from unittest import mock

from content_factory.remote_state import RemoteState, RemoteStateError


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class RemoteStateTest(unittest.TestCase):
    def test_disabled_without_credentials(self) -> None:
        remote = RemoteState()
        self.assertFalse(remote.enabled)
        with self.assertRaises(RemoteStateError):
            remote.queue_due("test")

    @mock.patch("content_factory.remote_state.urllib.request.urlopen")
    def test_queue_due_builds_authenticated_request(self, urlopen) -> None:
        urlopen.return_value = FakeResponse(
            {"ok": True, "rows": [{"post_id": "p1", "publisher": "telegram"}]}
        )
        remote = RemoteState("https://example.test", "secret-token")
        rows = remote.queue_due(
            "test", limit=5, now=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        self.assertEqual(rows[0]["post_id"], "p1")
        request = urlopen.call_args.args[0]
        self.assertIn("/api/v1/queue/due?", request.full_url)
        self.assertEqual(request.headers["Authorization"], "Bearer secret-token")
        self.assertEqual(request.headers["User-agent"], "content-factory-state/1.0")

    @mock.patch("content_factory.remote_state.urllib.request.urlopen")
    def test_put_state_and_health_tick(self, urlopen) -> None:
        urlopen.side_effect = [FakeResponse({"ok": True}), FakeResponse({"ok": True})]
        remote = RemoteState("https://example.test", "token")
        remote.put_state("schedule_state", {"done": {}})
        remote.health_tick("test", last_post_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(urlopen.call_count, 2)
        first_body = json.loads(urlopen.call_args_list[0].args[0].data.decode())
        self.assertEqual(first_body["state"], {"done": {}})
        second_body = json.loads(urlopen.call_args_list[1].args[0].data.decode())
        self.assertEqual(second_body["channel_id"], "test")
