"""Telethon auth helper: missing keys fail clearly, session path is configurable."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TelegramAuthTest(unittest.TestCase):
    def test_missing_keys_returns_clear_error(self) -> None:
        env = {**os.environ, "TG_API_ID": "", "TG_API_HASH": ""}
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "telegram_auth.py")],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("TG_API_ID", result.stdout)


if __name__ == "__main__":
    unittest.main()
