"""Тесты импорта документов и источника ``docs``."""
import tempfile
import unittest
from pathlib import Path

from content_factory.config import Settings
from content_factory.models import SourceConfig
from content_factory.sources import available_types, get_adapter
from content_factory.sources.docs import DocsAdapter, _extract_title
from content_factory.utils import FetchError

SETTINGS = Settings.load()


class DocsAdapterTest(unittest.TestCase):
    def test_registered(self) -> None:
        self.assertIn("docs", available_types())
        self.assertIsInstance(get_adapter("docs"), DocsAdapter)

    def test_extract_title(self) -> None:
        self.assertEqual(_extract_title("# Заголовок\n\nТекст", Path("x.md")), "Заголовок")
        self.assertEqual(_extract_title("Первая строка\nвторая", Path("x.md")), "Первая строка")
        self.assertEqual(_extract_title("", Path("my_file_name.md")), "my file name")

    def test_fetch_markdown_and_text_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "first.md").write_text(
                "# Первый документ\n\nТекст первого документа.", encoding="utf-8"
            )
            (base / "second.txt").write_text("Второй документ\n\nТекст.", encoding="utf-8")
            source = SourceConfig(id="docs-test", type="docs", options={"dir": str(base)})
            articles = DocsAdapter().fetch(source, SETTINGS)
            self.assertEqual(len(articles), 2)
            self.assertEqual(
                {article.title for article in articles},
                {"Первый документ", "Второй документ"},
            )
            self.assertTrue(all(article.url.startswith("file://") for article in articles))
            self.assertTrue(all(article.source_id == "docs-test" for article in articles))
            self.assertTrue(all(article.text for article in articles))

    def test_max_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for index in range(5):
                (base / "doc{}.md".format(index)).write_text(
                    "# Док {}\n\nтекст".format(index), encoding="utf-8"
                )
            source = SourceConfig(
                id="docs-limit", type="docs", options={"dir": str(base), "max_items": 2}
            )
            self.assertEqual(len(DocsAdapter().fetch(source, SETTINGS)), 2)

    def test_missing_dir_raises(self) -> None:
        source = SourceConfig(
            id="docs-missing", type="docs", options={"dir": "/nonexistent-docs-dir-xyz"}
        )
        with self.assertRaises(FetchError):
            DocsAdapter().fetch(source, SETTINGS)

    def test_relative_dir_resolves_from_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "rel.md").write_text("# Относительный\n\nтекст", encoding="utf-8")
            source = SourceConfig(id="docs-rel", type="docs", options={"dir": tmp})
            self.assertEqual(len(DocsAdapter().fetch(source, SETTINGS)), 1)


if __name__ == "__main__":
    unittest.main()
