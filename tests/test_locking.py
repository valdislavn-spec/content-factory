"""Single-instance locks: daemon/bot protection and token-derived names."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from content_factory.locking import FileLock, LockError, single_instance, telegram_lock_name

ROOT = Path(__file__).resolve().parents[1]


class FileLockTest(unittest.TestCase):
    def test_second_acquire_fails_until_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = FileLock(Path(tmp), "daemon")
            first.acquire()
            try:
                with self.assertRaises(LockError):
                    FileLock(Path(tmp), "daemon").acquire()
                first.release()
                with single_instance(Path(tmp), "daemon"):
                    pass
            finally:
                first.release()

    def test_lock_survives_second_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with single_instance(Path(tmp), "daemon"):
                code = (
                    "from content_factory.locking import LockError, single_instance;"
                    "import pathlib,sys;"
                    f"p=pathlib.Path({tmp!r});"
                    "\ntry:\n"
                    " with single_instance(p,'daemon'): print('acquired')\nexcept LockError: print('blocked')"
                )
                result = subprocess.run(
                    [sys.executable, "-c", code], cwd=str(ROOT),
                    capture_output=True, text=True, timeout=20,
                )
                self.assertEqual(result.stdout.strip(), "blocked", result.stderr)

    def test_token_name_does_not_leak_token(self) -> None:
        name = telegram_lock_name("123:secret-token")
        self.assertTrue(name.startswith("telegram-bot-"))
        self.assertNotIn("secret", name)
        self.assertEqual(name, telegram_lock_name("123:secret-token"))


if __name__ == "__main__":
    unittest.main()
