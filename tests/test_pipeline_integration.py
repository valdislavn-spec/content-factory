"""Интеграционный тест демо-режима (офлайн, через все модули).

Проверяет сквозной путь: демо-статьи → кластеризация → анализ → генерация →
dry-run публикация в outbox → SQLite → HTML/Markdown отчёт.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from content_factory.config import Settings
from content_factory.pipeline import run_demo


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def make_temp_project() -> tuple:
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    (root / "config").mkdir()
    (root / "samples").mkdir()
    shutil.copyfile(PROJECT_ROOT / "config" / "settings.yaml", root / "config" / "settings.yaml")
    shutil.copyfile(PROJECT_ROOT / "config" / "channels.yaml", root / "config" / "channels.yaml")
    shutil.copyfile(
        PROJECT_ROOT / "samples" / "demo_articles.json",
        root / "samples" / "demo_articles.json",
    )
    return tmp, root


class DemoIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp, cls.root = make_temp_project()
        cls.settings = Settings.load(root=cls.root)
        # Демо-тест герметичен: не зависит от того, на какой язык/каналы и
        # LLM-провайдера сейчас настроен реальный config/settings.yaml.
        cls.settings.raw.setdefault("app", {})
        cls.settings.raw["app"]["language"] = "ru"
        cls.settings.raw["app"]["channels_file"] = "config/channels.yaml"
        cls.settings.raw.setdefault("llm", {})["provider"] = "extractive"
        cls.settings.channels_path = cls.root / "config" / "channels.yaml"
        cls.result = run_demo(cls.settings, reset=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_all_six_channels(self) -> None:
        self.assertEqual(self.result["channels"], 6)

    def test_posts_generated(self) -> None:
        self.assertGreaterEqual(self.result["posts"], 6)
        self.assertGreaterEqual(self.result["published"], 6)

    def test_outbox_files(self) -> None:
        outbox = Path(self.result["outbox"])
        self.assertTrue(outbox.exists())
        files = list(outbox.rglob("*"))
        txt_files = [f for f in files if f.suffix == ".txt"]
        html_files = [f for f in files if f.suffix == ".html"]
        self.assertGreaterEqual(len(txt_files), 6)
        self.assertGreaterEqual(len(html_files), 6)
        sample = txt_files[0].read_text(encoding="utf-8")
        self.assertGreater(len(sample), 300)
        self.assertIn("http", sample)

    def test_demo_database(self) -> None:
        db_path = Path(self.settings.root) / "data" / "demo" / "demo.sqlite3"
        self.assertTrue(db_path.exists())
        from content_factory.storage import Storage

        with Storage(db_path) as storage:
            posts = storage.get_posts(days=30, limit=100)
            self.assertGreaterEqual(len(posts), 6)
            runs = storage.recent_runs(days=30)
            self.assertEqual(len(runs), 6)

    def test_report_files(self) -> None:
        reports = self.result.get("reports") or {}
        self.assertIn("html", reports)
        self.assertIn("md", reports)
        html_path = Path(reports["html"])
        md_path = Path(reports["md"])
        self.assertTrue(html_path.exists())
        self.assertTrue(md_path.exists())
        html = html_path.read_text(encoding="utf-8")
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("Технологии и ИИ", html)
        self.assertNotIn("cdn.", html)
        self.assertNotIn("<script src=", html)
        markdown = md_path.read_text(encoding="utf-8")
        self.assertIn("Контент-завод", markdown)

    def test_channels_config_untouched(self) -> None:
        payload = json.loads((PROJECT_ROOT / "samples" / "demo_articles.json").read_text(encoding="utf-8"))
        self.assertEqual(len(payload["articles"]), 18)


if __name__ == "__main__":
    unittest.main()
