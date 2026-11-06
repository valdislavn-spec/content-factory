"""Тесты SQLite-хранилища (stdlib unittest, без сети)."""
from __future__ import annotations

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from content_factory.models import (
    Article,
    GeneratedPost,
    MetricSnapshot,
    PublishResult,
    RunResult,
    utcnow,
)
from content_factory.storage import Storage


def make_article(index: int = 1, source_id: str = "src", channel: str = "test") -> Article:
    return Article(
        id=f"article-{channel}-{source_id}-{index}",
        title=f"Тестовая новость {index}",
        url=f"https://example.com/news/{channel}/{source_id}/{index}",
        source_id=source_id,
        source_name=f"Источник {source_id}",
        published_at=utcnow() - timedelta(minutes=index),
        text="Текст новости. " * 20,
    )


class StorageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.sqlite3"
        self.storage = Storage(self.db_path)

    def tearDown(self) -> None:
        self.storage.close()
        self.tmp.cleanup()

    def test_articles_and_dedupe(self) -> None:
        articles = [make_article(1), make_article(2)]
        self.assertEqual(self.storage.save_articles("test", articles), 2)
        # Повторное сохранение не увеличивает счётчик.
        self.assertEqual(self.storage.save_articles("test", articles), 0)
        self.assertEqual(self.storage.filter_new_articles("test", articles), [])
        new_article = make_article(3)
        self.assertEqual(self.storage.filter_new_articles("test", [new_article]), [new_article])
        # Другой канал видит те же статьи как новые.
        self.assertEqual(len(self.storage.filter_new_articles("other", articles)), 2)
        self.assertGreaterEqual(self.storage.count_articles("test", days=1), 2)

    def test_post_lifecycle(self) -> None:
        post = GeneratedPost(
            id="post-1",
            channel_id="test",
            cluster_id="cluster-1",
            format="story",
            text="<b>Заголовок</b>\n\nТекст поста.",
            hashtags=["#тест"],
            sources=[{"title": "Новость", "url": "https://example.com/1", "source": "Пример"}],
        )
        self.assertTrue(self.storage.save_post(post))
        self.assertFalse(self.storage.save_post(post))  # дубликат по id
        titles = self.storage.recent_post_titles("test", hours=24)
        self.assertEqual(len(titles), 1)
        self.assertIn("Заголовок", titles[0])
        posts = self.storage.get_posts("test", days=1)
        self.assertEqual(posts[0]["hashtags"], ["#тест"])
        self.assertEqual(posts[0]["sources"][0]["source"], "Пример")
        self.assertFalse(self.storage.post_exists("post-2"))
        self.storage.mark_post_status("post-1", "published", "https://t.me/test/1")
        self.assertEqual(self.storage.get_posts("test", days=1)[0]["status"], "published")

    def test_publishes_and_runs(self) -> None:
        result = PublishResult(
            channel_id="test",
            post_id="post-1",
            publisher="dryrun",
            ok=True,
            dry_run=True,
        )
        self.storage.save_publish(result)
        self.storage.save_publish(
            PublishResult(
                channel_id="test",
                post_id="post-2",
                publisher="telegram",
                ok=False,
                error="нет токена",
            )
        )
        counts = self.storage.count_publishes("test", days=1)
        self.assertEqual(counts["total"], 2)
        self.assertEqual(counts["ok"], 1)
        self.assertEqual(counts["failed"], 1)
        self.assertEqual(counts["dry_run"], 1)

        run = RunResult(
            channel_id="test",
            articles_fetched=10,
            articles_new=5,
            clusters=3,
            posts_generated=2,
            posts_published=2,
            errors=["источник упал"],
            dry_run=True,
        ).finish()
        self.storage.save_run(run)
        runs = self.storage.recent_runs(days=1)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["errors"], ["источник упал"])
        self.assertEqual(runs[0]["posts_published"], 2)

    def test_metrics_and_stats(self) -> None:
        for index in range(3):
            self.storage.save_post(
                GeneratedPost(
                    id=f"post-{index}",
                    channel_id="test",
                    cluster_id=f"c-{index}",
                    format="digest" if index == 0 else "story",
                    text="Текст " * 40,
                )
            )
        self.storage.save_metrics(
            MetricSnapshot(
                channel_id="test",
                subscribers=1000,
                posts_total=3,
                posts_published=2,
                articles_total=5,
                top_sources=[{"source_name": "Пример", "count": 5}],
            )
        )
        latest = self.storage.latest_metrics("test")
        self.assertIsNotNone(latest)
        self.assertEqual(latest["subscribers"], 1000)
        stats = self.storage.channel_stats("test", days=1)
        self.assertEqual(stats["posts"], 3)
        self.assertEqual(stats["formats"].get("digest"), 1)
        global_stats = self.storage.global_stats(days=1)
        self.assertEqual(global_stats["posts"], 3)

    def test_empty_db(self) -> None:
        self.assertEqual(self.storage.count_articles(days=7), 0)
        self.assertEqual(self.storage.get_posts(days=7), [])
        self.assertIsNone(self.storage.latest_metrics("none"))
        self.assertEqual(self.storage.count_publishes(days=7)["total"], 0)
        self.assertEqual(self.storage.recent_runs(days=7), [])


if __name__ == "__main__":
    unittest.main()
