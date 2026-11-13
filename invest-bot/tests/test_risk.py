from bot.risk import hard_loss_hit, loss_from_start, max_drawdown_pct


def test_loss_from_start():
    assert loss_from_start(99_000, 100_000) == 1_000
    assert loss_from_start(101_000, 100_000) == 0


def test_hard_loss_hit_at_cap():
    assert not hard_loss_hit(98_000, 100_000, 3_000)
    assert hard_loss_hit(97_000, 100_000, 3_000)
    assert not hard_loss_hit(1_000, 100_000, 0)


def test_drawdown():
    assert round(max_drawdown_pct(110_000, 99_000), 2) == 10.0
    assert max_drawdown_pct(0, 10) == 0
