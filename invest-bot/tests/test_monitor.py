from __future__ import annotations

from datetime import datetime, timezone

from bot.monitor import append_snapshot, build_report, daily_rows, iter_snapshots


def _row(ts: str, equity: float, trades: int = 0, error: str = "") -> dict:
    return {
        "fetched_at": ts,
        "status": {
            "mode": "sandbox",
            "equity": equity,
            "start_equity": 100_000.0,
            "risk": {"trades_today": trades},
            "positions": [],
            "last_error": error,
        },
    }


def test_daily_rows_keep_last_snapshot_per_msk_day():
    rows = [
        _row("2026-11-24T08:00:00+00:00", 100_000.0),
        _row("2026-11-24T15:00:00+00:00", 99_900.0),
        _row("2026-11-25T15:00:00+00:00", 100_100.0),
    ]
    daily = daily_rows(rows)
    assert len(daily) == 2
    assert daily[0]["status"]["equity"] == 99_900.0


def test_report_has_daily_and_cumulative_pnl():
    rows = [
        _row("2026-11-23T15:00:00+00:00", 100_000.0),
        _row("2026-11-24T15:00:00+00:00", 99_900.0, trades=2, error="remote"),
        _row("2026-11-25T15:00:00+00:00", 100_100.0, trades=1),
    ]
    text = build_report(rows)
    assert "2026-11-24" in text
    assert "-100.00" in text
    assert "+200.00" in text
    assert "Доходность: **+0.100%**" in text
    assert "Сделок за день (сумма последних снимков): **3**" in text
    assert "Снимков с ошибкой: **1**" in text


def test_append_snapshot_dedupes_identical_status(tmp_path):
    data = {"mode": "sandbox", "equity": 100_000.0, "positions": []}
    path, first = append_snapshot(tmp_path, data, fetched_at=datetime(2026, 11, 25, tzinfo=timezone.utc))
    assert first is True
    path2, second = append_snapshot(tmp_path, data, fetched_at=datetime(2026, 11, 25, 1, tzinfo=timezone.utc))
    assert second is False
    assert path == path2
    assert len(path.read_text().splitlines()) == 1
    assert len(list(iter_snapshots(tmp_path))) == 1
