from bot.indicators import ema, rsi


def test_ema_seed_and_trend():
    values = [float(i) for i in range(1, 31)]
    out = ema(values, 9)
    assert out[7] is None
    assert out[8] == sum(values[:9]) / 9
    assert out[-1] is not None and out[-1] < values[-1]


def test_rsi_bounds_and_uptrend():
    values = [float(i) for i in range(1, 40)]
    out = rsi(values, 14)
    assert out[-1] is not None
    assert 0 <= out[-1] <= 100
    assert out[-1] > 70
