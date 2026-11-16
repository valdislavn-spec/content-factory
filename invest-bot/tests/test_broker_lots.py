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
