"""Тесты интеграции Similarweb: разбор ответа без сети и форматтеры отчёта."""
from __future__ import annotations

import unittest
from unittest import mock

from content_factory.integrations import similarweb


SAMPLE_PAYLOAD = {
    "Engagements": {
        "BounceRate": 0.4731,
        "PagePerVisit": 2.87,
        "Visits": 12_345_678,
        "TimeOnSite": 184.5,
    },
    "GlobalRank": {"Rank": 1234},
    "CountryRank": {"Rank": 56},
    "CategoryRank": {"Rank": 17},
    "Category": "news_and_media",
    "TopCountryShares": [
        {"Country": 840, "Value": 0.31},
        {"Country": 826, "Value": 0.12},
        {"Country": 276, "Value": 0.05},
    ],
    "TrafficSources": {"Direct": 0.44, "Search": 0.38, "Social": 0.11, "Mail": 0.03},
    "EstimatedMonthlyVisits": {"2026-09-01": 11_000_000, "2026-10-01": 12_345_678},
}


class NormalizeDomainTest(unittest.TestCase):
    def test_strips_scheme_www_path(self) -> None:
        self.assertEqual(similarweb.normalize_domain("https://www.CoinDesk.com/rss?x=1"), "coindesk.com")
        self.assertEqual(similarweb.normalize_domain("espn.com/"), "espn.com")
        self.assertEqual(similarweb.normalize_domain(""), "")

    def test_endpoint_contains_domain(self) -> None:
        self.assertIn("domain=coindesk.com", similarweb.endpoint("coindesk.com"))


class ParsePayloadTest(unittest.TestCase):
    def test_parses_main_metrics(self) -> None:
        row = similarweb.parse_payload("coindesk.com", SAMPLE_PAYLOAD)
        self.assertEqual(row["domain"], "coindesk.com")
        self.assertEqual(row["visits"], 12_345_678)
        self.assertEqual(row["global_rank"], 1234)
        self.assertEqual(row["country_rank"], 56)
        self.assertAlmostEqual(row["bounce_rate"], 0.4731)
        self.assertAlmostEqual(row["pages_per_visit"], 2.87)
        self.assertAlmostEqual(row["time_on_site"], 184.5)
        self.assertEqual(row["category"], "news_and_media")
        self.assertEqual([item["country"] for item in row["top_countries"]], [840, 826, 276])
        self.assertAlmostEqual(row["traffic_sources"]["Direct"], 0.44)

    def test_falls_back_to_monthly_visits(self) -> None:
        payload = {"EstimatedMonthlyVisits": {"2026-09-01": 1000, "2026-10-01": 2000}}
        row = similarweb.parse_payload("example.com", payload)
        self.assertEqual(row["visits"], 2000)

    def test_tolerates_unknown_shape(self) -> None:
        row = similarweb.parse_payload("example.com", {})
        self.assertIsNone(row["visits"])
        self.assertIsNone(row["global_rank"])
        self.assertEqual(row["top_countries"], [])

    def test_rank_accepts_number(self) -> None:
        row = similarweb.parse_payload("example.com", {"GlobalRank": 77})
        self.assertEqual(row["global_rank"], 77)


class FetchDomainTest(unittest.TestCase):
    def test_success(self) -> None:
        with mock.patch.object(similarweb, "_http_get_json", return_value=SAMPLE_PAYLOAD):
            row = similarweb.fetch_domain("https://www.coindesk.com/")
        self.assertNotIn("error", row)
        self.assertEqual(row["domain"], "coindesk.com")

    def test_network_error_is_captured(self) -> None:
        with mock.patch.object(similarweb, "_http_get_json", side_effect=RuntimeError("HTTP 403")):
            row = similarweb.fetch_domain("coindesk.com")
        self.assertEqual(row["domain"], "coindesk.com")
        self.assertIn("403", row["error"])

    def test_empty_domain(self) -> None:
        row = similarweb.fetch_domain("")
        self.assertIn("error", row)


class FormatTest(unittest.TestCase):
    def test_markdown_table(self) -> None:
        rows = [similarweb.parse_payload("coindesk.com", SAMPLE_PAYLOAD)]
        text = similarweb.format_markdown(rows)
        self.assertIn("| coindesk.com |", text)
        self.assertIn("12 345 678", text)
        self.assertIn("47.3%", text)

    def test_markdown_with_errors(self) -> None:
        text = similarweb.format_markdown([{"domain": "x.com", "error": "HTTP 403"}])
        self.assertIn("403", text)
        self.assertIn("GitHub Actions", text)

    def test_telegram_short(self) -> None:
        rows = [similarweb.parse_payload("coindesk.com", SAMPLE_PAYLOAD)]
        text = similarweb.format_telegram(rows)
        self.assertIn("coindesk.com", text)


if __name__ == "__main__":
    unittest.main()
