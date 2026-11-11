"""Growth CLI + long-polling bot script (dry-run, без сети)."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

from content_factory.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]


class GrowthCliTest(unittest.TestCase):
    def test_parser_has_growth(self) -> None:
        args = build_parser().parse_args(["growth", "--days", "3"])
        self.assertEqual(args.func.__name__, "cmd_growth")
        self.assertEqual(args.days, 3.0)

    def test_growth_bot_dry_run(self) -> None:
        env = {
            **os.environ,
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_GROWTH_BOT_USERNAME": "test_bot",
        }
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "telegram-growth-bot.py"), "--dry-run"],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Growth-бот @test_bot", result.stdout)
        self.assertIn("start=https://t.me/test_bot?start=ai_news", result.stdout)


if __name__ == "__main__":
    unittest.main()
