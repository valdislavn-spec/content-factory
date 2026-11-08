"""Регрессия: смешанные naive/aware даты не должны ронять кластеризацию."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from content_factory.config import Settings, load_channels
from content_factory.models import Article, StoryCluster
from content_factory.pipeline import build_clusters


def _article(title: str, published_at: datetime) -> Article:
    return Article(
        id=title,
        title=title,
        url=f"https://example.com/{title}",
        source_id="test",
        source_name="Test",
        published_at=published_at,
        text="Test article about artificial intelligence and models.",
        language="en",
    )


def test_story_cluster_accepts_mixed_datetimes() -> None:
    naive = datetime(2026, 11, 8, 12, 0)
    aware = datetime(2026, 11, 8, 13, 0, tzinfo=timezone.utc)
    cluster = StoryCluster(id="c1", title="Test", articles=[_article("a", naive), _article("b", aware)])
    assert cluster.first_published is not None
    assert cluster.first_published.tzinfo is not None
    assert cluster.last_published is not None
    assert cluster.last_published.tzinfo is not None


def test_build_clusters_accepts_naive_published_at() -> None:
    settings = Settings.load()
    channel = next(c for c in load_channels(settings, path="config/channels.en.yaml") if c.id == "ai-news")
    now = datetime.now(timezone.utc)
    articles = [_article("naive", (now - timedelta(hours=2)).replace(tzinfo=None))]
    clusters = build_clusters(channel, articles, settings, now=now)
    assert clusters
    assert clusters[0].score >= 0
