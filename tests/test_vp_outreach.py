"""Тесты рассылки ВП: генерация сообщений и чтение трекера."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import vp_outreach  # noqa: E402


class BuildMessageTest(unittest.TestCase):
    def test_en_low_views_offer_1_to_1(self):
        row = {"partner": "@x", "avg_views": ""}
        text = vp_outreach.build_message(row, "en")
        self.assertIn("1:1", text)
        self.assertIn("HOOPY0007", text)

    def test_en_big_views_offer_2_to_1(self):
        row = {"partner": "@x", "avg_views": "600"}
        text = vp_outreach.build_message(row, "en")
        self.assertIn("2:1", text)

    def test_es_message_mentions_channel_and_18(self):
        text = vp_outreach.build_message({"partner": "@x"}, "es")
        self.assertIn("ES Sports Analytics", text)
        self.assertIn("18+", text)
        self.assertIn("SPORTSAnalytics007", text)


class LoadRowsTest(unittest.TestCase):
    def test_es_targets_are_usernames(self):
        rows = vp_outreach.load_rows("es", 3)
        self.assertTrue(rows)
        self.assertLessEqual(len(rows), 3)
        for row in rows:
            self.assertTrue(row["_target"].startswith("@"))
            self.assertEqual(row.get("region", "").upper(), "ES")

    def test_en_targets_present(self):
        rows = vp_outreach.load_rows("en", 5)
        self.assertTrue(rows)
        for row in rows:
            self.assertTrue(row["_target"].startswith("@"))


if __name__ == "__main__":
    unittest.main()
