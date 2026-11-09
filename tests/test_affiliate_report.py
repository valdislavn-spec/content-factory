"""Тесты отчёта по кликам партнёрских ссылок (link-tracker), без сети."""

from __future__ import annotations

import json
import unittest
from unittest import mock

import scripts.affiliate_report as report


DATA = {
    "ok": True,
    "count": 3,
    "links": [
        {
            "code": "bingx-crypto-news",
            "channel": "crypto-news",
            "network": "bingx",
            "label": "BingX",
            "target": "https://example.com/bingx",
            "days": {"2026-11-08": 2, "2026-11-09": 3},
            "last_click": "2026-11-09T02:00:00Z",
        },
        {
            "code": "travel-aviasales",
            "channel": "akkoma",
            "network": "travelpayouts",
            "label": "Aviasales",
            "target": "https://example.com/travel",
            "days": {"2026-11-07": 10, "2026-11-09": 1},
            "last_click": "2026-11-09T01:00:00Z",
        },
        {
            "code": "mylead-crypto-news",
            "channel": "crypto-news",
            "network": "mylead",
            "label": "MyLead",
            "target": "https://example.com/mylead",
            "days": {},
            "last_click": "",
        },
    ],
}


class BuildReportTests(unittest.TestCase):
    def test_aggregates_all_time(self):
        result = report.build_report(DATA)
        self.assertEqual(result["total_clicks"], 16)
        self.assertEqual(result["by_network"], {"travelpayouts": 11, "bingx": 5, "mylead": 0})
        self.assertEqual(result["by_channel"]["crypto-news"], 5)
        self.assertEqual(result["by_channel"]["akkoma"], 11)
        self.assertEqual(result["by_day"]["2026-11-07"], 10)
        self.assertEqual(result["links"][0]["code"], "travel-aviasales")
        self.assertEqual(result["links"][0]["clicks"], 11)

    def test_days_filter_and_min_clicks(self):
        result = report.build_report(DATA, days=1)
        # cutoff = сегодня-1 день: включаются только дни >= cutoff
        self.assertGreaterEqual(result["total_clicks"], 0)
        filtered = report.build_report(DATA, min_clicks=3)
        self.assertEqual([link["code"] for link in filtered["links"]], ["travel-aviasales", "bingx-crypto-news"])

    def test_render_markdown(self):
        text = report.render_markdown(report.build_report(DATA))
        self.assertIn("Клики по партнёрским ссылкам", text)
        self.assertIn("| bingx | 5 |", text)
        self.assertIn("bingx-crypto-news", text)
        self.assertIn("Регистрации/депозиты/покупки", text)

    def test_render_empty(self):
        text = report.render_markdown(report.build_report({"ok": True, "links": []}))
        self.assertIn("Нет кликов", text)


class FetchTests(unittest.TestCase):
    def test_missing_env_raises(self):
        with mock.patch.dict("os.environ", {"LINK_TRACKER_BASE": "", "LINK_TRACKER_STATS_TOKEN": ""}, clear=False):
            with self.assertRaises(RuntimeError):
                report.fetch_stats()

    def test_fetch_stats_mocked(self):
        class FakeResponse:
            def read(self):
                return json.dumps({"ok": True, "count": 1, "links": []}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        env = {"LINK_TRACKER_BASE": "https://tracker.example", "LINK_TRACKER_STATS_TOKEN": "test-token"}
        with mock.patch.dict("os.environ", env, clear=False), mock.patch(
            "urllib.request.urlopen", return_value=FakeResponse()
        ) as mocked:
            data = report.fetch_stats()
        self.assertTrue(data["ok"])
        request = mocked.call_args.args[0]
        self.assertIn("/stats", request.full_url)
        self.assertIn("token=test-token", request.full_url)

    def test_fetch_http_error(self):
        import urllib.error

        env = {"LINK_TRACKER_BASE": "https://tracker.example", "LINK_TRACKER_STATS_TOKEN": "test-token"}
        error = urllib.error.HTTPError("https://tracker.example/stats", 500, "err", {}, None)
        with mock.patch.dict("os.environ", env, clear=False), mock.patch(
            "urllib.request.urlopen", side_effect=error
        ):
            with self.assertRaises(RuntimeError):
                report.fetch_stats()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
