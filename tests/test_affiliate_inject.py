"""Партнёрские блоки в автопостах: правило 1:N, ротация, раскрытие, отключение."""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory import affiliate_inject as ai  # noqa: E402
from content_factory.affiliates import AffiliateError, load_registry  # noqa: E402


@pytest.fixture()
def state(tmp_path):
    return tmp_path / "autopost_state.json"


def test_every_n_rule(state):
    results = []
    for _ in range(5):
        text, meta = ai.maybe_inject("Новость про рынок", "ai-news", state_path=state)
        results.append(meta)
    assert results[:4] == [None, None, None, None]
    assert results[4] is not None
    assert results[4]["index"] == 5


def test_block_contains_tracked_link_and_disclosure(state):
    texts = []
    for _ in range(5):
        text, meta = ai.maybe_inject("Пост", "ai-news", state_path=state)
        texts.append((text, meta))
    text, meta = texts[-1]
    assert "🤝 Partners" in text
    assert "utm_source=tg_ai_en" in meta["url"]
    assert "affiliate link" in meta["disclosure"].lower()


def test_counter_persists_between_calls(state):
    ai.maybe_inject("x", "crypto-news", state_path=state)
    ai.maybe_inject("x", "crypto-news", state_path=state)
    assert ai.peek_index("crypto-news", state_path=state) == 2
    saved = json.loads(state.read_text())
    assert saved["channels"]["crypto-news"]["posts"] == 2


def test_rotation_between_programs(state):
    picked = []
    for _ in range(15):
        _, meta = ai.maybe_inject("Пост", "ai-news", state_path=state)
        if meta:
            picked.append(meta["program"])
    assert len(picked) == 3
    assert len(set(picked)) >= 2, picked
    assert picked[0] != picked[1], picked


def test_unknown_channel_is_passthrough(state):
    text, meta = ai.maybe_inject("Пост", "no-such-channel", state_path=state)
    assert text == "Пост"
    assert meta is None


def test_existing_block_not_duplicated(state):
    text, _ = ai.maybe_inject("Пост", "ai-news", state_path=state, force=True)
    again, meta = ai.maybe_inject(text, "ai-news", state_path=state, force=True)
    assert again == text
    assert meta is None


def test_disabled_by_env(state, monkeypatch):
    monkeypatch.setenv("AFFILIATE_AUTOPOST", "0")
    for _ in range(5):
        text, meta = ai.maybe_inject("Пост", "ai-news", state_path=state)
        assert meta is None


def test_registry_has_ready_programs_for_public_channels():
    registry = load_registry(ai.REGISTRY_PATH)
    for channel in ("crypto-news", "ai-news", "sport-news"):
        assert registry.ready_programs(channel), channel
