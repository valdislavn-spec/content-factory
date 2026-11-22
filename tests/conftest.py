"""Общая изоляция тестов от реальных внешних сервисов."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def disable_remote_state(monkeypatch):
    """Не позволяем тестам писать в боевую Cloudflare D1."""
    monkeypatch.delenv("CONTENT_FACTORY_STATE_URL", raising=False)
    monkeypatch.delenv("CONTENT_FACTORY_STATE_TOKEN", raising=False)
