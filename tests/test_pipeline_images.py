"""Тесты подстановки картинки статьи в пост (sendPhoto в Telegram)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from content_factory.models import Article, GeneratedPost, StoryCluster
from content_factory.pipeline import _attach_image

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def _article(meta=None) -> Article:
    return Article(
        id="a1",
        title="AI news",
        url="https://example.com/a1",
        source_id="worldnews",
        source_name="World News API",
        published_at=NOW,
        text="Text",
        meta=meta or {},
    )


def _cluster(*articles) -> StoryCluster:
    return StoryCluster(id="c1", title="AI news", articles=list(articles))


def _post(meta=None) -> GeneratedPost:
    return GeneratedPost(
        id="p1",
        channel_id="tech-ai",
        cluster_id="c1",
        format="story",
        text="Post",
        meta=dict(meta or {}),
    )


class AttachImageTests(unittest.TestCase):
    def test_takes_image_from_article_meta(self):
        post = _post()
        _attach_image(post, _cluster(_article({"image": "https://cdn.example.com/a.jpg"})))
        self.assertEqual(post.meta["image_url"], "https://cdn.example.com/a.jpg")

    def test_does_not_override_existing_image(self):
        post = _post({"image_url": "https://cdn.example.com/dify.jpg"})
        _attach_image(post, _cluster(_article({"image": "https://cdn.example.com/a.jpg"})))
        self.assertEqual(post.meta["image_url"], "https://cdn.example.com/dify.jpg")

    def test_ignores_invalid_and_uses_next_article(self):
        post = _post()
        _attach_image(
            post,
            _cluster(
                _article({"image": "not-a-url"}),
                _article({"image_url": "https://cdn.example.com/b.png"}),
            ),
        )
        self.assertEqual(post.meta["image_url"], "https://cdn.example.com/b.png")

    def test_no_image_meta_is_safe(self):
        post = _post()
        _attach_image(post, _cluster(_article()))
        self.assertNotIn("image_url", post.meta)
        _attach_image(None, None)  # не падает

    def test_image_from_article_without_meta(self):
        post = _post()
        _attach_image(post, _cluster(_article()))
        self.assertNotIn("image_url", post.meta)


if __name__ == "__main__":
    unittest.main()
