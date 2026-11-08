"""Тесты публичного API BingX (без сети: urlopen подменяется)."""

from __future__ import annotations

import io
import json
import unittest
import urllib.error
from unittest import mock

from content_factory.integrations.bingx import (
    BingXClient,
    BingXError,
    _api_symbol,
    _display_symbol,
    build_market_note,
)


class FakeResponse:
    def __init__(self, payload, status: int = 200) -> None:
        self.payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.status = status

    def read(self, *args, **kwargs) -> bytes:  # noqa: D102
        return self.payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args) -> bool:
        return False


def _ticker_payload(symbol: str = "BTC-USDT", price: str = "76066.5") -> dict:
    return {
        "code": 0,
        "msg": "",
        "data": {
            "symbol": symbol,
            "lastPrice": price,
            "priceChangePercent": "0.30",
            "priceChange": "223.9",
            "highPrice": "76166.5",
            "lowPrice": "75535.2",
            "volume": "3405.53",
        },
    }


class SymbolHelperTests(unittest.TestCase):
    def test_api_symbol(self) -> None:
        self.assertEqual(_api_symbol("BTC/USDT"), "BTC-USDT")
        self.assertEqual(_api_symbol("btc-usdt"), "BTC-USDT")
        self.assertEqual(_display_symbol("BTC-USDT"), "BTC/USDT")


class BingXClientTests(unittest.TestCase):
    def test_ticker_normalization(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            return FakeResponse(_ticker_payload())

        client = BingXClient()
        with mock.patch(
            "content_factory.integrations.bingx.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            quote = client.ticker("BTC/USDT")
        self.assertIn("openApi/swap/v2/quote/ticker", captured["url"])
        self.assertIn("symbol=BTC-USDT", captured["url"])
        self.assertEqual(quote["symbol"], "BTC/USDT")
        self.assertAlmostEqual(quote["price"], 76066.5)
        self.assertAlmostEqual(quote["percent_change"], 0.30)
        self.assertEqual(quote["source"], "bingx")

    def test_klines(self) -> None:
        payload = {
            "code": 0,
            "data": [
                {"open": "75862.1", "close": "75944.0", "high": "75995.5",
                 "low": "75862.1", "volume": "160.4", "time": 1794135600000}
            ],
        }
        client = BingXClient()
        with mock.patch(
            "content_factory.integrations.bingx.urllib.request.urlopen",
            return_value=FakeResponse(payload),
        ):
            candles = client.klines("BTC/USDT", "1h", 1)
        self.assertEqual(len(candles), 1)
        self.assertAlmostEqual(candles[0]["close"], 75944.0)

    def test_api_error_code(self) -> None:
        client = BingXClient()
        with mock.patch(
            "content_factory.integrations.bingx.urllib.request.urlopen",
            return_value=FakeResponse({"code": 100400, "msg": "symbol invalid"}),
        ):
            with self.assertRaises(BingXError) as ctx:
                client.ticker("NOPE/USDT")
        self.assertIn("symbol invalid", str(ctx.exception))

    def test_http_error(self) -> None:
        client = BingXClient()
        error = urllib.error.HTTPError(
            "https://open-api.bingx.com", 429, "rate", {}, io.BytesIO(b"{}")
        )
        with mock.patch(
            "content_factory.integrations.bingx.urllib.request.urlopen", side_effect=error
        ):
            with self.assertRaises(BingXError) as ctx:
                client.ticker("BTC/USDT")
        self.assertIn("429", str(ctx.exception))

    def test_quotes_partial_errors(self) -> None:
        client = BingXClient()
        responses = [
            FakeResponse(_ticker_payload("BTC-USDT", "76000")),
            FakeResponse({"code": 100400, "msg": "invalid"}),
        ]
        with mock.patch(
            "content_factory.integrations.bingx.urllib.request.urlopen", side_effect=responses
        ):
            quotes = client.quotes(["BTC/USDT", "NOPE/USDT"])
        self.assertAlmostEqual(quotes[0]["price"], 76000.0)
        self.assertIn("error", quotes[1])

    def test_market_note(self) -> None:
        client = BingXClient()
        responses = [
            FakeResponse(_ticker_payload("BTC-USDT", "76000")),
            FakeResponse(_ticker_payload("ETH-USDT", "2225")),
            FakeResponse(_ticker_payload("SOL-USDT", "90")),
            FakeResponse(_ticker_payload("XRP-USDT", "1.0")),
        ]
        with mock.patch(
            "content_factory.integrations.bingx.urllib.request.urlopen", side_effect=responses
        ):
            note = build_market_note(client=client)
        self.assertTrue(note.startswith("Markets:"))
        self.assertIn("BTC", note)


if __name__ == "__main__":
    unittest.main()
