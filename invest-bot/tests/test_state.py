from __future__ import annotations

from datetime import datetime

from bot.config import Config
from bot.engine import Engine, MSK
from bot.state import StateStore


def test_state_store_roundtrip(tmp_path):
    path = tmp_path / "state.db"
    store = StateStore(path)
    store.set("risk_start_equity", 100_000.0)
    store.set("kill_switch", True)
    store.set("day", "2026-11-25")
    store.close()

    again = StateStore(path)
    assert again.get_float("risk_start_equity") == 100_000.0
    assert again.get_bool("kill_switch") is True
    assert again.get("day") == "2026-11-25"
    assert again.get_float("missing", 7.5) == 7.5
    again.close()


def test_engine_persists_day_baseline_and_trade_count(tmp_path):
    cfg = Config(
        mode="paper",
        tickers=("SBER",),
        start_equity=100_000.0,
        state_path=str(tmp_path / "engine.db"),
    )
    first = Engine(cfg)
    first.day = datetime.now(MSK).date().isoformat()
    first.day_start_equity = 99_000.0
    first.trades_today = 1
    first._save_state()

    second = Engine(cfg)
    assert second.day_start_equity == 99_000.0
    assert second.trades_today == 1
    assert second.risk_start_equity == 100_000.0
