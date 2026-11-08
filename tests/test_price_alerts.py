"""Тесты авто-алертов по цене (без сети и без Telegram)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

from content_factory.models import ChannelConfig, GeneratedPost, PublishResult
from content_factory.price_alerts import (
    AlertRule,
    PriceAlertEngine,
    check_rules,
    format_alert,
    load_rules,
)

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)


def _rule(**kwargs) -> AlertRule:
    base = {"symbol": "BTC/USDT", "above": 78000.0, "below": 74000.0, "cooldown_minutes": 360}
    base.update(kwargs)
    return AlertRule(**base)


def test_load_rules_and_keys() -> None:
    rules = load_rules(
        {"rules": [{"symbol": "btc-usdt", "above": 78000, "below": 74000, "cooldown_minutes": 60}]}
    )
    assert len(rules) == 1
    assert rules[0].symbol == "BTC/USDT"
    assert "BTC/USDT:above:78000" in rules[0].keys()


def test_cross_above_and_state_update() -> None:
    state: Dict[str, Any] = {"prices": {"BTC/USDT": {"price": 77000, "at": NOW.isoformat()}}}
    tickers = {"BTC/USDT": {"price": 78100, "percent_change": 2.0}}
    alerts = check_rules([_rule()], tickers, state, now=NOW)
    assert len(alerts) == 1
    assert alerts[0]["type"] == "above"
    assert alerts[0]["level"] == 78000.0
    assert state["prices"]["BTC/USDT"]["price"] == 78100


def test_no_alert_without_previous_price() -> None:
    state: Dict[str, Any] = {}
    alerts = check_rules([_rule()], {"BTC/USDT": {"price": 79000}}, state, now=NOW)
    assert alerts == []
    assert state["prices"]["BTC/USDT"]["price"] == 79000


def test_no_repeat_when_already_above() -> None:
    state: Dict[str, Any] = {"prices": {"BTC/USDT": {"price": 79000, "at": NOW.isoformat()}}}
    alerts = check_rules([_rule()], {"BTC/USDT": {"price": 79500}}, state, now=NOW)
    assert alerts == []


def test_cooldown_blocks_repeat() -> None:
    state: Dict[str, Any] = {
        "prices": {"BTC/USDT": {"price": 77000, "at": NOW.isoformat()}},
        "last_fired": {"BTC/USDT:above:78000": (NOW - timedelta(minutes=10)).isoformat()},
    }
    alerts = check_rules([_rule()], {"BTC/USDT": {"price": 78500}}, state, now=NOW)
    assert alerts == []


def test_cross_below() -> None:
    state: Dict[str, Any] = {"prices": {"BTC/USDT": {"price": 74500, "at": NOW.isoformat()}}}
    alerts = check_rules([_rule()], {"BTC/USDT": {"price": 73500}}, state, now=NOW)
    assert len(alerts) == 1
    assert alerts[0]["type"] == "below"
    assert alerts[0]["level"] == 74000.0


def test_move_percent() -> None:
    rule = _rule(above=None, below=None, move_percent=2.5, move_window_minutes=60, cooldown_minutes=60)
    state: Dict[str, Any] = {
        "prices": {"BTC/USDT": {"price": 76000, "at": (NOW - timedelta(minutes=30)).isoformat()}}
    }
    alerts = check_rules([rule], {"BTC/USDT": {"price": 78200}}, state, now=NOW)
    assert len(alerts) == 1
    assert alerts[0]["type"] == "move"
    assert alerts[0]["pct"] > 2.5


def test_format_alert_en_es_ru() -> None:
    alert = {"symbol": "BTC/USDT", "price": 78100.0, "percent_change": 2.1, "type": "above", "level": 78000.0}
    en = format_alert(alert, "en")
    assert "broke above $78,000" in en
    assert "$78,100.00" in en
    assert "#Bitcoin" in en
    es = format_alert(alert, "es")
    assert "superó los $78,000" in es
    ru = format_alert(alert, "ru")
    assert "пробил уровень" in ru


class FakePublisher:
    def __init__(self) -> None:
        self.posts: List[GeneratedPost] = []

    def publish(self, post, channel, settings) -> PublishResult:
        self.posts.append(post)
        return PublishResult(
            channel_id=channel.id,
            post_id=post.id,
            publisher="fake",
            ok=True,
            dry_run=True,
        )


def _channel(channel_id: str, language: str = "en") -> ChannelConfig:
    return ChannelConfig(
        id=channel_id,
        title=channel_id,
        topics=["crypto"],
        language=language,
        telegram_chat_id="@test",
    )


def test_engine_run_once_publishes_and_persists(tmp_path: Path) -> None:
    settings = SimpleNamespace(root=tmp_path, dry_run=True)
    channels = [_channel("crypto-news", "en"), _channel("crypto-es", "es")]
    prices = iter([77000.0, 78200.0, 78300.0])
    publisher = FakePublisher()
    engine = PriceAlertEngine(
        settings,
        {"channels": ["crypto-news", "crypto-es"], "rules": [{"symbol": "BTC/USDT", "above": 78000, "cooldown_minutes": 360}]},
        price_fetcher=lambda symbol: {"price": next(prices), "percent_change": 2.0},
        publisher_factory=lambda name, s: publisher,
        channels=channels,
        state_path=tmp_path / "state.json",
        dry_run=True,
    )
    assert engine.run_once() == []  # первый прогон только запоминает цену
    results = engine.run_once()  # пересечение 78000 → публикация в 2 канала
    assert len(results) == 2
    assert [p.channel_id for p in publisher.posts] == ["crypto-news", "crypto-es"]
    assert "broke above" in publisher.posts[0].text
    assert "superó los" in publisher.posts[1].text
    # третий прогон: уже выше, повтора нет
    assert engine.run_once() == []
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved["prices"]["BTC/USDT"]["price"] == 78300.0
