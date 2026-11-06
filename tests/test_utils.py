"""Тесты общих утилит (stdlib unittest, без сети)."""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from content_factory.utils import (
    extract_numbers,
    format_local,
    jaccard,
    normalize_space,
    normalize_url,
    parse_datetime,
    parse_hhmm,
    split_sentences,
    strip_html,
    tokenize,
    truncate,
    url_hash,
)


class UtilsTest(unittest.TestCase):
    def test_strip_html(self) -> None:
        html = "<p>Привет, <b>мир</b>!</p><script>alert('x')</script><style>.a{}</style>"
        self.assertEqual(strip_html(html), "Привет, мир!")

    def test_strip_html_plain_text(self) -> None:
        self.assertEqual(strip_html("Новость без тегов"), "Новость без тегов")

    def test_normalize_space(self) -> None:
        self.assertEqual(normalize_space("  а \n б\u00a0в  "), "а б в")

    def test_split_sentences(self) -> None:
        text = (
            "Учёные провели исследование. Оно показало интересные результаты! "
            "Что будет дальше? Пока неизвестно."
        )
        sentences = split_sentences(text)
        self.assertEqual(len(sentences), 4)
        self.assertTrue(sentences[0].startswith("Учёные"))

    def test_truncate_keeps_word_boundary(self) -> None:
        text = "Это довольно длинный текст, который нужно аккуратно обрезать по границе слова."
        result = truncate(text, 30)
        self.assertLessEqual(len(result), 31)
        self.assertTrue(result.endswith("…"))
        self.assertNotIn("обрез", result)

    def test_parse_datetime_rfc822(self) -> None:
        dt = parse_datetime("Sat, 18 Oct 2026 09:30:00 +0300")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.astimezone(timezone.utc).hour, 6)
        self.assertEqual(dt.tzinfo is not None, True)

    def test_parse_datetime_iso(self) -> None:
        dt = parse_datetime("2026-10-18T09:30:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 9)

    def test_parse_datetime_bad(self) -> None:
        self.assertIsNone(parse_datetime("не дата"))

    def test_normalize_url_and_hash(self) -> None:
        url = "https://Example.com/news/item/?utm_source=tg&id=5#anchor"
        normalized = normalize_url(url)
        self.assertEqual(normalized, "https://example.com/news/item?id=5")
        self.assertEqual(url_hash(url), url_hash("https://example.com/news/item?id=5"))
        self.assertNotEqual(url_hash(url), url_hash("https://example.com/news/item?id=6"))

    def test_format_local(self) -> None:
        dt = datetime(2026, 10, 18, 6, 0, tzinfo=timezone.utc)
        self.assertEqual(format_local(dt, 3), "18.10.2026 09:00")

    def test_parse_hhmm(self) -> None:
        self.assertEqual(parse_hhmm("09:05"), (9, 5))
        with self.assertRaises(ValueError):
            parse_hhmm("25:00")
        with self.assertRaises(ValueError):
            parse_hhmm("9")

    def test_tokenize_and_jaccard(self) -> None:
        a = tokenize("Российский рынок вырос на 5 процентов")
        b = tokenize("Рынок России вырос на пять процентов")
        self.assertTrue(set(a) & set(b))
        self.assertGreater(jaccard(a, b), 0.3)
        self.assertEqual(jaccard([], ["x"]), 0.0)

    def test_extract_numbers(self) -> None:
        text = "Выручка выросла на 12,5% до 3,4 млрд рублей, а инфляция — 7%."
        numbers = extract_numbers(text)
        self.assertGreaterEqual(len(numbers), 2)
        self.assertTrue(any("%" in n for n in numbers))


class DotenvTest(unittest.TestCase):
    def test_load_dotenv_does_not_override(self) -> None:
        from content_factory.utils import load_dotenv

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("CF_TEST_A=1\nCF_TEST_B=два\n# коммент\n", encoding="utf-8")
            os.environ.pop("CF_TEST_A", None)
            os.environ["CF_TEST_B"] = "старое"
            load_dotenv(path)
            self.assertEqual(os.environ.get("CF_TEST_A"), "1")
            self.assertEqual(os.environ.get("CF_TEST_B"), "старое")
            os.environ.pop("CF_TEST_A", None)
            os.environ.pop("CF_TEST_B", None)


if __name__ == "__main__":
    unittest.main()
