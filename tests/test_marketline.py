"""Tests for the live market line (no network access)."""

from pathlib import Path

from content_factory.integrations.marketline import (
    build_market_line,
    format_change,
    format_market_line,
    format_usd,
    insert_before_hashtags,
)

PRICES = {
    "bitcoin": {"usd": 75861.42, "usd_24h_change": 1.24},
    "ethereum": {"usd": 2313.5, "usd_24h_change": -0.42},
    "solana": {"usd": 0.9876, "usd_24h_change": 0.0},
}
KALSHI_MARKETS = [
    {
        "ticker": "KXBTC-26NOV08-B75800",
        "title": "Bitcoin price range on Nov 8, 2026?",
        "yes_sub_title": "$75,800 to 75,899.99",
        "yes_bid_dollars": "0.73",
        "volume_fp": "10015",
    }
]


def test_format_usd():
    assert format_usd(75861.42) == "$75,861"
    assert format_usd(2313.5) == "$2,314"
    assert format_usd(1.5) == "$1.50"
    assert format_usd(0.9876) == "$0.9876"


def test_format_change():
    assert format_change(1.24) == " (▲1.2%)"
    assert format_change(-0.42) == " (▼0.4%)"
    assert format_change(0.0) == " (•0.0%)"
    assert format_change(None) == ""


def test_format_market_line():
    line = format_market_line(PRICES, coins=("bitcoin", "ethereum", "solana"))
    assert line.startswith("📈 ")
    assert "BTC $75,861 (▲1.2%)" in line
    assert "ETH $2,314 (▼0.4%)" in line
    assert "SOL $0.9876" in line


def test_insert_before_hashtags():
    text = "Body text\n\n#Bitcoin #Crypto"
    result = insert_before_hashtags(text, "📈 BTC $1")
    assert result == "Body text\n\n📈 BTC $1\n\n#Bitcoin #Crypto"

    text = "Body only"
    assert insert_before_hashtags(text, "📈 BTC $1") == "Body only\n\n📈 BTC $1"
    assert insert_before_hashtags(text, "") == text


def test_kalshi_line_prefers_price_target_market():
    seen = []

    def markets_fetcher(ticker: str):
        seen.append(ticker)
        if ticker == "KXBTCMAX100":
            return [
                {
                    "ticker": "KXBTCMAX100-26-DEC",
                    "title": "When will Bitcoin cross $100k again?",
                    "yes_sub_title": "Before January 2027",
                    "yes_bid_dollars": "0.12",
                    "volume_fp": "40000",
                }
            ]
        return KALSHI_MARKETS

    from content_factory.integrations.marketline import kalshi_btc_line

    line = kalshi_btc_line(("KXBTCMAX100", "KXBTC"), markets_fetcher=markets_fetcher)
    assert line == "Kalshi: BTC $100k · Before January 2027 — 12¢"
    assert "KXBTCMAX100" in seen


def test_build_market_line_with_cache(tmp_path: Path):
    calls = {"prices": 0, "kalshi": 0}

    def price_fetcher(url: str):
        calls["prices"] += 1
        return PRICES

    def markets_fetcher(ticker: str):
        calls["kalshi"] += 1
        return KALSHI_MARKETS

    cache = tmp_path / "marketline.json"
    config = {"enabled": True, "coins": ["bitcoin", "ethereum"], "kalshi_series": ["KXBTC"]}
    line = build_market_line(config, price_fetcher=price_fetcher, markets_fetcher=markets_fetcher, cache_path=cache)
    assert "BTC $75,861" in line
    assert "Kalshi: $75,800 to 75,899.99 — 73¢" in line
    # second call is served from cache
    line2 = build_market_line(config, price_fetcher=price_fetcher, markets_fetcher=markets_fetcher, cache_path=cache)
    assert line2 == line
    assert calls == {"prices": 1, "kalshi": 1}


def test_build_market_line_disabled_and_failures(tmp_path: Path):
    assert build_market_line({"enabled": False}, cache_path=tmp_path / "c.json") == ""

    def broken(url: str):
        raise RuntimeError("network down")

    line = build_market_line(
        {"enabled": True, "coins": ["bitcoin"]},
        price_fetcher=broken,
        cache_path=tmp_path / "c.json",
    )
    assert line == ""
