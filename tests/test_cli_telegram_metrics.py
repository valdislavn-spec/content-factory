"""CLI: команда telegram-metrics подключена к парсеру."""

from __future__ import annotations

import unittest

from content_factory.cli import build_parser


class TelegramMetricsCliTest(unittest.TestCase):
    def test_parser_has_telegram_metrics(self) -> None:
        args = build_parser().parse_args(
            ["telegram-metrics", "--channel", "ai-news", "--limit", "5"]
        )
        self.assertEqual(args.func.__name__, "cmd_telegram_metrics")
        self.assertEqual(args.channel, "ai-news")
        self.assertEqual(args.limit, 5)

    def test_parser_defaults(self) -> None:
        args = build_parser().parse_args(["telegram-metrics"])
        self.assertEqual(args.channel, "all")
        self.assertEqual(args.limit, 30)


if __name__ == "__main__":
    unittest.main()
