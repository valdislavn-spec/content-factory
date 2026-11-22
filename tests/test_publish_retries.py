"""Повторная публикация постов, не дошедших до Telegram."""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from content_factory.models import ChannelConfig, GeneratedPost, PublishResult, utcnow
from content_factory.pipeline import process_publish_retries
from content_factory.storage import Storage


class FakePublisher:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.calls = 0

    def publish(self, post, channel, settings):
        self.calls += 1
        if self.ok:
            return PublishResult(
                channel_id=channel.id,
                post_id=post.id,
                publisher="telegram",
                ok=True,
                external_id="42",
                url="https://t.me/test/42",
            )
        return PublishResult(
            channel_id=channel.id,
            post_id=post.id,
            publisher="telegram",
            ok=False,
            error="still failing",
        )


class PublishRetryTest(unittest.TestCase):
    def setUp(self) -> None:
        # Тесты не должны писать в реальную D1, даже если она настроена в shell.
        self.env_patch = mock.patch.dict(
            os.environ,
            {"CONTENT_FACTORY_STATE_URL": "", "CONTENT_FACTORY_STATE_TOKEN": ""},
            clear=False,
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.tmp.name) / "test.sqlite3")
        self.channel = ChannelConfig(id="test", title="Test")
        self.settings = SimpleNamespace(
            pipeline={
                "publish_retry_max_attempts": 5,
                "publish_retry_base_minutes": 5,
            }
        )
        self.post = GeneratedPost(
            id="retry-post",
            channel_id="test",
            cluster_id="cluster",
            format="digest",
            text="<b>Заголовок</b>\n\nТекст.",
        )
        self.storage.save_post(self.post)

    def tearDown(self) -> None:
        self.storage.close()
        self.tmp.cleanup()

    def test_due_retry_publishes_and_removes_from_queue(self) -> None:
        self.storage.enqueue_publish_retry(self.post, "telegram", "HTTP 500")
        publisher = FakePublisher(ok=True)
        with mock.patch("content_factory.pipeline.get_publisher", return_value=publisher):
            results = process_publish_retries(
                self.channel,
                self.settings,
                self.storage,
                now=utcnow() + timedelta(minutes=10),
            )

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].ok)
        self.assertEqual(publisher.calls, 1)
        self.assertEqual(self.storage.due_publish_retries("test"), [])

    def test_failed_retry_stays_until_max_attempts(self) -> None:
        self.storage.enqueue_publish_retry(self.post, "telegram", "HTTP 500")
        publisher = FakePublisher(ok=False)
        with mock.patch("content_factory.pipeline.get_publisher", return_value=publisher):
            # Сдвигаем срок, чтобы очередь была доступна в этом же тесте.
            due = self.storage.due_publish_retries(
                "test", now=utcnow() + timedelta(minutes=10)
            )
            self.assertEqual(len(due), 1)
            results = process_publish_retries(
                self.channel,
                self.settings,
                self.storage,
                now=utcnow() + timedelta(minutes=10),
            )

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        # Первая попытка была в enqueue(), затем fail_publish_retry().
        self.assertEqual(
            self.storage.due_publish_retries(
                "test", now=utcnow() + timedelta(days=1)
            )[0]["attempts"],
            2,
        )

    def test_failed_telegram_publish_is_enqueued(self) -> None:
        from content_factory.pipeline import publish_post

        publisher = FakePublisher(ok=False)
        with mock.patch("content_factory.pipeline.get_publisher", return_value=publisher):
            results = publish_post(
                self.post, self.channel, self.settings, self.storage, False
            )

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        queued = self.storage.due_publish_retries(
            "test", now=utcnow() + timedelta(minutes=10)
        )
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]["post_id"], "retry-post")

    def test_already_published_post_is_not_sent_twice(self) -> None:
        self.storage.mark_post_status(self.post.id, "published", "https://t.me/test/1")
        self.storage.enqueue_publish_retry(self.post, "telegram", "HTTP 500")
        publisher = FakePublisher(ok=True)
        with mock.patch("content_factory.pipeline.get_publisher", return_value=publisher):
            results = process_publish_retries(
                self.channel,
                self.settings,
                self.storage,
                now=utcnow() + timedelta(minutes=10),
            )
        self.assertEqual(results, [])
        self.assertEqual(publisher.calls, 0)
        self.assertEqual(self.storage.due_publish_retries("test"), [])
