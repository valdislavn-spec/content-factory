"""Спреды/тоталы в дайджесте Polymarket и фиксированный утренний слот."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from scripts import polymarket_digest as digest


def market(question, url, probability=None, volume=0.0, outcomes=None, prices=None):
    return {
        "question": question,
        "url": url,
        "probability": probability,
        "volume_24h": volume,
        "outcomes": outcomes,
        "outcomePrices": prices,
    }


class SpreadLinesTest(unittest.TestCase):
    def test_spread_line_rendered(self):
        markets = [market("Spread: Rams (-2.5)", "https://polymarket.com/market/g-spread", 0.52, 500)]
        lines = digest.spread_lines(markets, "Packers vs. Rams", 1)
        self.assertEqual(len(lines), 1)
        self.assertIn("↳ spread", lines[0])
        self.assertIn("Rams (-2.5)", lines[0])
        self.assertIn("52%", lines[0])

    def test_spread_from_other_game_ignored(self):
        markets = [market("Spread: Bills (-7.5)", "https://polymarket.com/market/x-spread", 0.3, 900)]
        self.assertEqual(digest.spread_lines(markets, "Packers vs. Rams", 1), [])

    def test_spread_limit_respected(self):
        markets = [
            market("Spread: Rams (-2.5)", "https://polymarket.com/market/a", 0.52, 500),
            market("Spread: Rams (-3.5)", "https://polymarket.com/market/b", 0.40, 100),
        ]
        self.assertEqual(len(digest.spread_lines(markets, "Packers vs. Rams", 1)), 1)


class TotalLinesTest(unittest.TestCase):
    def test_total_uses_over_probability(self):
        markets = [market("Packers vs. Rams: O/U 45.5", "https://polymarket.com/market/t", 0.4, 0,
                          ["Over", "Under"], ["0.4", "0.6"])]
        lines = digest.total_lines(markets, "Packers vs. Rams", 1)
        self.assertEqual(len(lines), 1)
        self.assertIn("↳ total", lines[0])
        self.assertIn("O/U 45.5", lines[0])
        self.assertIn("Over 40%", lines[0])

    def test_partial_and_team_totals_skipped(self):
        markets = [
            market("Packers vs. Rams: 1Q O/U 10.5", "https://polymarket.com/market/q", 0.5, 10,
                   ["Over", "Under"], ["0.5", "0.5"]),
            market("Packers Team Total: O/U 23.5", "https://polymarket.com/market/tt", 0.5, 10,
                   ["Over", "Under"], ["0.5", "0.5"]),
        ]
        self.assertEqual(digest.total_lines(markets, "Packers vs. Rams", 2), [])

    def test_total_requires_outcomes(self):
        markets = [market("Packers vs. Rams: O/U 45.5", "https://polymarket.com/market/t", None, 0)]
        self.assertEqual(digest.total_lines(markets, "Packers vs. Rams", 1), [])


class RotationTest(unittest.TestCase):
    def test_fixed_slot_excluded_from_rotation(self):
        config = {"digests": [
            {"channel": "crypto-news", "language": "en"},
            {"channel": "sport-news", "language": "en", "fixed_hour_utc": 13},
        ]}
        args = SimpleNamespace(channel="", rotate=True, now=None)
        picked = digest.pick_entries(config, args)
        self.assertEqual([entry["channel"] for entry in picked], ["crypto-news"])

    def test_fixed_slot_still_available_by_name(self):
        config = {"digests": [{"channel": "sport-news", "language": "en", "fixed_hour_utc": 13}]}
        args = SimpleNamespace(channel="sport-news", rotate=True, now=None)
        self.assertEqual(len(digest.pick_entries(config, args)), 1)


if __name__ == "__main__":
    unittest.main()
