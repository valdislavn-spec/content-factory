"""Reddit-дайджест: заголовок, текст и дневной бюджет."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import reddit_digest  # noqa: E402

from content_factory.models import Article  # noqa: E402


def _article(title: str, source: str = "Test", n: int = 1) -> Article:
    return Article(
        id=f"a{n}",
        title=title,
        url=f"https://example.com/{n}",
        source_id="s",
        source_name=source,
        published_at=datetime.now(timezone.utc),
        text="text",
    )


class DigtestTest(unittest.TestCase):
    def test_build_post_title_and_text(self):
        articles = [_article("Bitcoin hits new high", n=1), _article("Nvidia earnings beat", n=2)]
        post = reddit_digest.build_post(articles, "USNewsWire")
        self.assertEqual(post.meta["reddit_title"], "US brief: Bitcoin hits new high + 1 more")
        self.assertIn("• Bitcoin hits new high", post.text)
        self.assertIn("Sources:", post.text)
        self.assertIn("https://example.com/1", post.text)

    def test_title_respects_reddit_limit(self):
        articles = [_article("x" * 400, n=1)]
        post = reddit_digest.build_post(articles, "USNewsWire")
        self.assertLessEqual(len(post.meta["reddit_title"]), 300)

    def test_budget_left_and_spend(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = reddit_digest.BUDGET
            reddit_digest.BUDGET = Path(tmp) / "usage.json"
            try:
                self.assertEqual(reddit_digest.budget_left(3), 3)
                reddit_digest.spend_budget()
                reddit_digest.spend_budget()
                self.assertEqual(reddit_digest.budget_left(3), 1)
                reddit_digest.spend_budget()
                self.assertEqual(reddit_digest.budget_left(3), 0)
                data = json.loads(reddit_digest.BUDGET.read_text(encoding="utf-8"))
                self.assertEqual(data["count"], 3)
            finally:
                reddit_digest.BUDGET = old


if __name__ == "__main__":
    unittest.main()
