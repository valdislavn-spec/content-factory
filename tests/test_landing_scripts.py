"""CLI-скрипты лендинга: сборка страниц и хэши для Cloudflare Pages."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts import build_landing, deploy_pages


class BuildLandingScriptTest(unittest.TestCase):
    def test_builds_six_pages_and_sitemap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "landing"
            code = build_landing.main(
                ["--out", str(out), "--base-url", "https://example.github.io/cf"]
            )
            self.assertEqual(code, 0)
            self.assertEqual(len(list(out.glob("*.html"))), 7)  # 6 каналов + index
            self.assertTrue((out / "sitemap.xml").is_file())
            self.assertIn("https://example.github.io/cf/ai-news.html", (out / "sitemap.xml").read_text(encoding="utf-8"))


class DeployPagesHelpersTest(unittest.TestCase):
    def test_collect_hashes_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.html").write_text("<h1>A</h1>", encoding="utf-8")
            (root / "sub").mkdir()
            (root / "sub" / "b.txt").write_text("b", encoding="utf-8")
            manifest, parts = deploy_pages.collect(root)
            self.assertEqual(set(manifest), {"a.html", "sub/b.txt"})
            self.assertEqual(len(parts), 2)
            self.assertEqual(len({sha for sha, _, _ in parts}), 2)


if __name__ == "__main__":
    unittest.main()
