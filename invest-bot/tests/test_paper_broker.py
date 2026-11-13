import os
import tempfile
from datetime import datetime

from bot.broker import PaperBroker, MSK


def test_buy_sell_pnl():
    path = os.path.join(tempfile.mkdtemp(), "state.db")
    b = PaperBroker(path, start_equity=100_000, fee=0.0)
    now = datetime.now(MSK)
    fill = b.buy("SBER", price=100.0, budget=10_000, reason="test", ts=now)
    assert fill and fill["qty"] == 100
    assert b.cash() == 90_000
    assert b.position("SBER")["qty"] == 100
    b.sell("SBER", price=110.0, reason="test", ts=now)
    assert b.position("SBER") is None
    assert b.cash() == 101_000
    trades = b.trades()
    assert trades[0]["side"] == "SELL" and trades[0]["pnl"] == 1_000
