from __future__ import annotations


def loss_from_start(equity: float, start_equity: float) -> float:
    """Realized+unrealized loss versus the risk baseline (positive = loss)."""
    return max(0.0, float(start_equity) - float(equity))


def max_drawdown_pct(peak_equity: float, equity: float) -> float:
    if peak_equity <= 0:
        return 0.0
    return max(0.0, (float(peak_equity) - float(equity)) / float(peak_equity) * 100.0)


def hard_loss_hit(equity: float, start_equity: float, max_total_loss_rub: float) -> bool:
    """True when the hard loss budget is exhausted.

    This stops NEW risk. It intentionally does not force-close positions: with
    ALLOW_LOSS_EXIT=0 an open loss stays open, so the only true no-loss state is
    MODE=paper/sandbox or TRADING_ENABLED=0.
    """
    if max_total_loss_rub <= 0:
        return False
    return loss_from_start(equity, start_equity) >= max_total_loss_rub
