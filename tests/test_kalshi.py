"""Tests for the Kalshi integration (no network access)."""

import base64

import pytest

from content_factory.integrations.kalshi import (
    KalshiClient,
    build_digest,
    close_date,
    market_url,
    market_volume,
    select_markets,
    yes_price_cents,
)

MARKETS = [
    {
        "ticker": "KXBTC-26DEC-BTC100",
        "title": "Will Bitcoin be above $100,000 in December?",
        "series_ticker": "KXBTC",
        "yes_bid_dollars": "0.42",
        "volume_fp": "125000.5",
        "close_time": "2026-12-31T15:00:00Z",
    },
    {
        "ticker": "KXETH-26DEC-ETH4K",
        "title": "Ethereum above $4,000 in December?",
        "series_ticker": "KXETH",
        "yes_bid": 18,
        "volume_fp": "400000",
        "close_time": "2026-12-31T15:00:00Z",
    },
    {
        "ticker": "KXNFLX",
        "title": "Super Bowl winner",
        "series_ticker": "KXNFL",
        "yes_bid_dollars": "0.05",
        "volume_fp": "9000",
    },
]


def test_yes_price_cents_prefers_dollars():
    assert yes_price_cents(MARKETS[0]) == 42
    assert yes_price_cents(MARKETS[1]) == 18
    assert yes_price_cents({}) is None


def test_market_volume_and_close_date():
    assert market_volume(MARKETS[0]) == 125000.5
    assert market_volume({}) == 0.0
    assert close_date(MARKETS[0]) == "31 Dec"
    assert close_date({}) == ""


def test_market_url_uses_series():
    assert market_url(MARKETS[0]) == "https://kalshi.com/markets/kxbtc"
    assert market_url({}) == "https://kalshi.com/markets"


def test_select_markets_filters_and_sorts():
    selected = select_markets(MARKETS, keywords=["bitcoin"], min_volume=1000)
    assert [m["ticker"] for m in selected] == ["KXBTC-26DEC-BTC100"]
    selected = select_markets(MARKETS, keywords=["bitcoin", "ethereum"], min_volume=1000, max_items=2)
    assert [m["ticker"] for m in selected] == ["KXETH-26DEC-ETH4K", "KXBTC-26DEC-BTC100"]
    assert select_markets(MARKETS, keywords=["zebra"]) == []


def test_build_digest_layout():
    text = build_digest(
        select_markets(MARKETS, keywords=["bitcoin", "ethereum"], min_volume=1000),
        title="Crypto prediction markets",
        language="en",
        max_items=2,
    )
    assert text.startswith("Crypto prediction markets")
    assert "YES 18¢" in text
    assert "vol 400,000" in text
    assert "https://kalshi.com/markets" in text
    assert "Not investment advice" in text
    assert "Ad ·" not in text


def test_build_digest_spanish_and_affiliate():
    text = build_digest(MARKETS[:1], title="Mercados", language="es", affiliate_url="https://kalshi.com/r/abc")
    assert "No es consejo de inversión" in text
    assert "Ad · https://kalshi.com/r/abc" in text


def test_client_fetches_markets_with_fetcher():
    calls = []

    def fake_fetch(url, headers, timeout):
        calls.append((url, headers))
        return {"markets": MARKETS}

    client = KalshiClient(fetcher=fake_fetch)
    markets = client.markets(limit=5)
    assert len(markets) == 3
    assert "status=open" in calls[0][0]
    assert "limit=5" in calls[0][0]
    assert calls[0][1] == {}  # public request, no auth headers


def test_signed_headers_with_ed25519():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except Exception as error:  # noqa: BLE001 - optional dependency / broken local wheel
        pytest.skip("cryptography unavailable: %s" % error)

    private = Ed25519PrivateKey.generate()
    pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    def fake_fetch(url, headers, timeout):
        return {"ok": True, "headers": headers}

    client = KalshiClient(key_id="test-key", private_key_pem=pem, fetcher=fake_fetch)
    response = client.request("GET", "/trade-api/v2/portfolio/balance")
    headers = response["headers"]
    assert headers["KALSHI-ACCESS-KEY"] == "test-key"
    assert headers["KALSHI-ACCESS-TIMESTAMP"].isdigit()
    message = (headers["KALSHI-ACCESS-TIMESTAMP"] + "GET/trade-api/v2/portfolio/balance").encode()
    signature = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
    private.public_key().verify(signature, message)  # raises on bad signature
