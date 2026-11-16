from types import SimpleNamespace

from bot.broker import TinkoffBroker


def test_sell_lots_are_converted_from_shares(monkeypatch):
    broker = TinkoffBroker.__new__(TinkoffBroker)
    broker.account_id = "acc"
    broker.instrument = lambda ticker: {"figi": "FIGI", "lot": 10}
    broker.positions = lambda: [{"ticker": "MTSS", "qty": 10, "avg_price": 184.1}]
    sent = {}

    def fake_post(service, method, payload):
        sent.update(payload)
        return {"orderId": "order-1", "executionReportStatus": "ORDER_EXECUTION_REPORT_STATUS_FILL"}

    broker._post = fake_post
    broker._wait_order = lambda *args, **kwargs: "FILL"
    broker._log = lambda *args, **kwargs: None
    broker.sell("MTSS", 184.25, "test", None)
    assert sent["quantity"] == "1"


def test_preferred_account_is_initialized():
    broker = TinkoffBroker("t.test", "sandbox", account_id="abc")
    assert broker.preferred_account_id == "abc"


def test_load_history_dir(tmp_path):
    import json
    from bot.backtest import load_history_dir

    payload = {
        "ticker": "TEST",
        "lot": 10,
        "candles": [
            {"ts": "2026-01-01T10:00:00+03:00", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
            {"ts": "2026-01-01T10:05:00+03:00", "open": 1.5, "high": 2, "low": 1, "close": 1.8, "volume": 120},
        ],
    }
    (tmp_path / "TEST_180d.json").write_text(json.dumps(payload))
    data, lots = load_history_dir(str(tmp_path))
    assert len(data["TEST"]) == 2
    assert lots["TEST"] == 10
