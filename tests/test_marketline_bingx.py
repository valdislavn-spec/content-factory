"""Рыночная строка через BingX (без ключа) — без сети."""

from __future__ import annotations

from pathlib import Path

from content_factory.integrations.marketline import build_market_line


def test_bingx_price_source(tmp_path: Path, monkeypatch) -> None:
    def fake_bingx(coins, timeout=10.0, fetcher=None):
        return {
            "bitcoin": {"usd": 76000.0, "usd_24h_change": 1.5},
            "ethereum": {"usd": 2200.0, "usd_24h_change": -0.4},
        }

    monkeypatch.setattr(
        "content_factory.integrations.marketline.fetch_crypto_prices_bingx", fake_bingx
    )
    line = build_market_line(
        {"enabled": True, "price_source": "bingx", "coins": ["bitcoin", "ethereum"]},
        cache_path=tmp_path / "c.json",
    )
    assert line.startswith("📈")
    assert "BTC $76,000" in line
    assert "ETH $2,200" in line


def test_disabled_returns_empty(tmp_path: Path) -> None:
    assert build_market_line({"enabled": False}, cache_path=tmp_path / "c.json") == ""
