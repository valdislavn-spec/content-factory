"""Тесты интеграции Twelve Data (без сети: urlopen подменяется)."""

from __future__ import annotations

import io
import json
import os
import unittest
import urllib.error
from unittest import mock

from content_factory.integrations.twelvedata import (
    DEFAULT_CRYPTO_SYMBOLS,
    TwelveDataClient,
    TwelveDataError,
    build_market_note,
    format_snapshot,
)

_ENV_KEY = "TWELVEDATA_API_KEY"


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


def http_error(code: int, body: dict) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.twelvedata.com", code, "error", {}, io.BytesIO(json.dumps(body).encode())
    )


class TwelveDataClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.pop(_ENV_KEY, None)
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        if self._saved is None:
            os.environ.pop(_ENV_KEY, None)
        else:
            os.environ[_ENV_KEY] = self._saved

    def test_missing_api_key(self) -> None:
        client = TwelveDataClient(api_key="")
        with self.assertRaises(TwelveDataError) as ctx:
            client.quote("BTC/USD")
        self.assertIn("TWELVEDATA_API_KEY", str(ctx.exception))

    def test_quote_normalization(self) -> None:
        payload = {
            "symbol": "BTC/USD",
            "name": "Bitcoin / US Dollar",
            "exchange": "Coinbase",
            "currency": "USD",
            "datetime": "2026-11-08",
            "timestamp": 1794096000,
            "close": "75625.12",
            "previous_close": "80440.00",
            "change": "-4814.88",
            "percent_change": "-5.99",
            "is_market_open": True,
            "status": "ok",
        }
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            return FakeResponse(payload)

        client = TwelveDataClient(api_key="test-key")
        with mock.patch(
            "content_factory.integrations.twelvedata.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            quote = client.quote("BTC/USD")
        self.assertIn("quote", captured["url"])
        self.assertIn("apikey=test-key", captured["url"])
        self.assertEqual(quote["symbol"], "BTC/USD")
        self.assertAlmostEqual(quote["price"], 75625.12)
        self.assertAlmostEqual(quote["percent_change"], -5.99)
        self.assertTrue(quote["is_market_open"])

    def test_api_error_payload(self) -> None:
        client = TwelveDataClient(api_key="bad")
        with mock.patch(
            "content_factory.integrations.twelvedata.urllib.request.urlopen",
            return_value=FakeResponse({"status": "error", "code": 401, "message": "Invalid API key"}),
        ):
            with self.assertRaises(TwelveDataError) as ctx:
                client.quote("BTC/USD")
        self.assertIn("Invalid API key", str(ctx.exception))

    def test_http_error(self) -> None:
        client = TwelveDataClient(api_key="k")
        with mock.patch(
            "content_factory.integrations.twelvedata.urllib.request.urlopen",
            side_effect=http_error(429, {"message": "rate limit"}),
        ):
            with self.assertRaises(TwelveDataError) as ctx:
                client.price("BTC/USD")
        self.assertIn("429", str(ctx.exception))

    def test_price_and_series(self) -> None:
        client = TwelveDataClient(api_key="k")
        responses = [
            FakeResponse({"price": "2250.55"}),
            FakeResponse(
                {
                    "meta": {"symbol": "ETH/USD"},
                    "values": [
                        {"datetime": "2026-11-08 10:00:00", "open": "2200", "high": "2300",
                         "low": "2190", "close": "2250.55", "volume": "1200"}
                    ],
                    "status": "ok",
                }
            ),
        ]
        with mock.patch(
            "content_factory.integrations.twelvedata.urllib.request.urlopen",
            side_effect=responses,
        ):
            self.assertAlmostEqual(client.price("ETH/USD"), 2250.55)
            candles = client.time_series("ETH/USD", "1h", 1)
        self.assertEqual(len(candles), 1)
        self.assertAlmostEqual(candles[0]["close"], 2250.55)

    def test_quotes_contain_errors_per_symbol(self) -> None:
        client = TwelveDataClient(api_key="k")
        responses = [
            FakeResponse({"symbol": "BTC/USD", "close": "100", "percent_change": "1.5"}),
            FakeResponse({"status": "error", "code": 400, "message": "bad symbol"}),
        ]
        with mock.patch(
            "content_factory.integrations.twelvedata.urllib.request.urlopen",
            side_effect=responses,
        ):
            quotes = client.quotes(["BTC/USD", "NOPE"])
        self.assertAlmostEqual(quotes[0]["price"], 100.0)
        self.assertIn("error", quotes[1])


class FormatSnapshotTests(unittest.TestCase):
    def test_snapshot_text(self) -> None:
        quotes = [
            {"symbol": "BTC/USD", "price": 75625.12, "percent_change": -5.99},
            {"symbol": "ETH/USD", "price": 2225.0, "percent_change": -7.96},
            {"symbol": "SOL/USD", "price": 90.5, "percent_change": 1.2},
        ]
        text = format_snapshot(quotes)
        self.assertIn("₿ BTC", text)
        self.assertIn("Ξ ETH", text)
        self.assertIn("−5.99%", text)
        self.assertIn("+1.20%", text)
        self.assertIn(" · ", text)

    def test_snapshot_skips_errors_and_limits(self) -> None:
        quotes = [
            {"symbol": "BTC/USD", "price": None, "error": "no data"},
            {"symbol": "ETH/USD", "price": 2000.0, "percent_change": 0.0},
            {"symbol": "SOL/USD", "price": 90.0, "percent_change": 1.0},
        ]
        text = format_snapshot(quotes, max_items=1)
        self.assertIn("ETH", text)
        self.assertNotIn("BTC", text)
        self.assertNotIn("SOL", text)

    def test_empty(self) -> None:
        self.assertEqual(format_snapshot([]), "")

    def test_build_market_note(self) -> None:
        client = TwelveDataClient(api_key="k")
        responses = [
            FakeResponse({"symbol": "BTC/USD", "close": "75000", "percent_change": "2.0"}),
            FakeResponse({"symbol": "ETH/USD", "close": "2200", "percent_change": "-1.0"}),
            FakeResponse({"symbol": "SOL/USD", "close": "90", "percent_change": "0.5"}),
            FakeResponse({"symbol": "XRP/USD", "close": "1.0", "percent_change": "0.0"}),
        ]
        with mock.patch(
            "content_factory.integrations.twelvedata.urllib.request.urlopen",
            side_effect=responses,
        ):
            note = build_market_note(client=client)
        self.assertTrue(note.startswith("Markets:"))
        self.assertIn("BTC", note)
        self.assertEqual(len(DEFAULT_CRYPTO_SYMBOLS), 4)


if __name__ == "__main__":
    unittest.main()
