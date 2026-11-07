"""Тесты единого пульта scripts/unified.py (без сети)."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_SPEC = importlib.util.spec_from_file_location("unified_script", ROOT / "scripts" / "unified.py")
unified = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(unified)


def make_channel(channel_id: str, topics=None, language: str = "en", offset: int = 3):
    return SimpleNamespace(
        id=channel_id,
        title=channel_id,
        topics=topics or [],
        language=language,
        enabled=True,
        timezone_offset=offset,
        schedule=["09:00", "18:00"],
        posts_per_day=2,
        hashtags=["#test"],
        telegram_chat_id="",
    )


class UnifiedConfigTests(unittest.TestCase):
    def test_load_unified_config(self):
        config = unified.load_unified()
        self.assertIn("pipeline", config)
        self.assertEqual(config["pipeline"]["expected_posts_per_day"], 90)
        self.assertEqual(config["brain"]["engine"], "langgraph")
        self.assertTrue(config["trends"]["enabled"])
        self.assertIn("growth", config)
        self.assertIn("seo", config)

    def test_save_trends(self):
        payload = {"generated_at": "2026-11-07T00:00:00+00:00", "channels": {"a": ["x"]}}
        with tempfile.TemporaryDirectory() as tmp:
            path = unified.save_trends(payload, Path(tmp) / "nested" / "latest.json")
            self.assertTrue(path.exists())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), payload)


class ScheduleTests(unittest.TestCase):
    def test_next_slots_sorted_and_utc(self):
        now = datetime(2026, 11, 7, 5, 0, tzinfo=timezone.utc)  # 08:00 MSK
        channels = [make_channel("a", offset=3)]
        slots = unified.next_slots(channels, now=now, limit=2)
        self.assertEqual(len(slots), 2)
        self.assertEqual(slots[0][0], datetime(2026, 11, 7, 6, 0, tzinfo=timezone.utc))
        self.assertEqual(slots[1][0], datetime(2026, 11, 7, 15, 0, tzinfo=timezone.utc))
        self.assertLessEqual(slots[0][0], slots[1][0])

    def test_next_slots_rolls_to_tomorrow(self):
        # 20:00 MSK — все слоты на сегодня прошли, ближайший завтра 09:00 MSK
        now = datetime(2026, 11, 7, 17, 0, tzinfo=timezone.utc)
        channel = make_channel("a", offset=3, topics=["bitcoin"])
        slots = unified.next_slots([channel], now=now, limit=1)
        self.assertEqual(slots[0][0], datetime(2026, 11, 8, 6, 0, tzinfo=timezone.utc))


class TrendMatchTests(unittest.TestCase):
    def setUp(self):
        self.channels = [
            make_channel("crypto-news", ["bitcoin", "crypto", "blockchain"]),
            make_channel("ai-news", ["ai", "openai", "llm"]),
            make_channel("sport-news", ["nfl", "nba", "football"]),
            make_channel("crypto-es", ["bitcoin", "criptomoneda"], language="es"),
        ]

    def test_crypto_trend_matches_crypto_channels(self):
        matched = unified.match_channels("Bitcoin ETF approval", self.channels)
        self.assertIn("crypto-news", matched)
        self.assertNotIn("ai-news", matched)

    def test_ai_trend_matches_ai_channel(self):
        matched = unified.match_channels("OpenAI releases GPT model", self.channels)
        self.assertIn("ai-news", matched)
        self.assertNotIn("sport-news", matched)

    def test_sport_trend_matches_sport_channel(self):
        matched = unified.match_channels("NFL trade deadline", self.channels)
        self.assertIn("sport-news", matched)

    def test_short_hint_does_not_match_inside_words(self):
        self.assertFalse(unified._contains_hint("chairman", "ai"))
        self.assertTrue(unified._contains_hint("AI model", "ai"))


class DoctorTests(unittest.TestCase):
    def test_fail_exit_code(self):
        sections = [{"title": "x", "checks": [(unified.FAIL, "bad", "")]}]
        self.assertEqual(unified.doctor_exit_code(sections), 1)

    def test_warn_only_exit_code_zero(self):
        sections = [{"title": "x", "checks": [(unified.WARN, "warn", ""),
                                              (unified.PASS, "ok", "")]}]
        self.assertEqual(unified.doctor_exit_code(sections), 0)


class CliTests(unittest.TestCase):
    def test_parser_commands(self):
        parser = unified.build_parser()
        self.assertEqual(parser.parse_args(["doctor"]).command, "doctor")
        tick = parser.parse_args(["tick", "--publish"])
        self.assertTrue(tick.publish)
        trends = parser.parse_args(["trends", "--channel", "crypto-news", "--limit", "2"])
        self.assertEqual(trends.channel, "crypto-news")
        self.assertEqual(trends.limit, 2)


if __name__ == "__main__":
    unittest.main()
