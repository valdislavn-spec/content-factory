"""Health-check должен замечать ошибки соцсетей, а не только Telegram."""

from scripts.check_publish_health import analyze


def test_analyze_counts_social_publish_errors() -> None:
    log = """
2026-11-14 17:00:00 INFO content_factory.scheduler: Демон: одиночный проход завершён, слотов обработано 1
2026-11-14 17:00:01 INFO content_factory.pipeline: Пост abc опубликован (telegram)
2026-11-14 17:00:02 ERROR content_factory.pipeline: Не удалось опубликовать abc через mastodon: HTTP 403: login disabled
2026-11-14 17:00:03 ERROR content_factory.pipeline: Не удалось опубликовать abc через discord: HTTP 403: blocked
"""
    stats = analyze(log)

    assert stats["slots"] == 1
    assert stats["published"] == 1
    assert stats["publish_errors"] == 2
    assert len(stats["publish_error_samples"]) == 2


def test_analyze_does_not_count_source_errors_as_publication_errors() -> None:
    log = "Ошибка источника rss: timeout\nНе удалось опубликовать abc через telegram: HTTP 500"
    stats = analyze(log)

    assert stats["publish_errors"] == 1
    assert stats["source_errors"] == 1
