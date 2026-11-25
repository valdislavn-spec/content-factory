from __future__ import annotations

import pytest
import requests

from bot.broker import BrokerError, TinkoffBroker


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def post(self, *args, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _broker(session):
    broker = TinkoffBroker.__new__(TinkoffBroker)
    broker.base = "https://example.invalid/rest"
    broker.PREFIX = "/p."
    broker.session = session
    broker.timeout = 1
    return broker


def test_post_retries_network_errors(monkeypatch):
    monkeypatch.setattr("bot.broker.time.sleep", lambda _: None)
    session = FakeSession([
        requests.ConnectionError("reset"),
        requests.Timeout("slow"),
        FakeResponse(200, {"ok": True}),
    ])
    assert _broker(session)._post("S", "M", {}) == {"ok": True}
    assert session.calls == 3


def test_post_retries_transient_5xx(monkeypatch):
    monkeypatch.setattr("bot.broker.time.sleep", lambda _: None)
    session = FakeSession([
        FakeResponse(503, {"message": "down"}),
        FakeResponse(200, {"ok": True}),
    ])
    assert _broker(session)._post("S", "M", {}) == {"ok": True}
    assert session.calls == 2


def test_post_raises_after_exhausted_network_errors(monkeypatch):
    monkeypatch.setattr("bot.broker.time.sleep", lambda _: None)
    session = FakeSession([requests.ConnectionError("reset")] * 6)
    with pytest.raises(BrokerError):
        _broker(session)._post("S", "M", {})
