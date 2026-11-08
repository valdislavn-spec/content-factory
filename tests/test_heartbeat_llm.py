"""Heartbeat: строка расхода LLM и предупреждение о лимитах."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import heartbeat  # noqa: E402


class LlmUsageLineTest(unittest.TestCase):
    def test_reports_counts_and_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            data.mkdir()
            (data / "llm_usage_cloudflare.json").write_text(
                json.dumps({"date": "2026-11-08", "count": 95}), encoding="utf-8"
            )
            (data / "llm_usage_ollama_cloud.json").write_text(
                json.dumps({"date": "2026-11-08", "count": 40}), encoding="utf-8"
            )
            (data / "llm_tokens.json").write_text(
                json.dumps({"calls": 42, "prompt_tokens": 1000, "completion_tokens": 200}),
                encoding="utf-8",
            )
            old = os.getcwd()
            os.chdir(tmp)
            try:
                line = heartbeat.llm_usage_line()
            finally:
                os.chdir(old)
            self.assertIn("cloudflare 95/100", line)
            self.assertIn("ollama_cloud 40/250", line)
            self.assertIn("42 вызовов", line)
            self.assertIn("близко к лимиту", line)

    def test_no_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            os.chdir(tmp)
            try:
                line = heartbeat.llm_usage_line()
            finally:
                os.chdir(old)
            self.assertIn("нет данных", line)


if __name__ == "__main__":
    unittest.main()
