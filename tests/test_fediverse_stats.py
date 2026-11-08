"""Тесты отчёта Fediverse (Mastodon + Akkoma + tracker), без сети."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest import mock

from scripts.fediverse_stats import _fediverse_account, _tracker_stats, build_report, strip_html


class FakeResponse:
    def __init__(self, payload) -> None:
        import json

        self.payload = json.dumps(payload).encode()

    def read(self, *args, **kwargs) -> bytes:  # noqa: D102
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_strip_html() -> None:
    assert strip_html("<p>Hello <b>world</b> &amp; co</p>") == "Hello world & co"


def test_fediverse_account_filters_reblogs_and_sorts() -> None:
    account = {"id": "1", "acct": "test", "followers_count": 10, "following_count": 2, "statuses_count": 5}
    statuses = [
        {"id": "a", "url": "https://ex/a", "content": "<p>low</p>", "favourites_count": 1, "reblogs_count": 0, "replies_count": 0},
        {"id": "b", "url": "https://ex/b", "content": "<p>top</p>", "favourites_count": 3, "reblogs_count": 2, "replies_count": 1},
        {"id": "c", "reblog": {"id": "r"}, "content": "boost"},
    ]
    with mock.patch(
        "scripts.fediverse_stats._get",
        side_effect=[account, statuses],
    ):
        data = _fediverse_account("https://mastodon.social", "token")
    assert data is not None
    assert data["followers"] == 10
    assert [p["id"] for p in data["posts"]] == ["b", "a"]
    assert data["posts"][0]["text"] == "top"


def test_tracker_stats() -> None:
    payload = {
        "ok": True,
        "links": [
            {"code": "travel-airalo", "network": "travelpayouts", "total": 5},
            {"code": "bingx-default", "network": "bingx", "total": 2},
        ],
    }
    with mock.patch("scripts.fediverse_stats._get", return_value=payload):
        data = _tracker_stats("https://links.example.dev", "stats-token")
    assert data is not None
    assert data["total_clicks"] == 7


def test_build_report_contains_sections() -> None:
    mastodon = {
        "acct": "m",
        "followers": 4,
        "following": 0,
        "statuses": 20,
        "posts": [{"url": "https://ex/1", "text": "post", "favourites": 2, "reblogs": 1, "replies": 0}],
    }
    akkoma = {"acct": "a", "followers": 0, "following": 0, "statuses": 3, "posts": []}
    tracker = {"total_clicks": 7, "links": [{"code": "travel-airalo", "network": "travelpayouts", "total": 7}]}
    report = build_report(mastodon, akkoma, tracker, now=datetime(2026, 11, 8, tzinfo=timezone.utc))
    assert "# Fediverse" in report
    assert "Mastodon (@m)" in report
    assert "travel-airalo" in report
    assert "Всего кликов: **7**" in report
    assert "2026-11-08" in report


def test_build_report_handles_errors() -> None:
    report = build_report({"error": "boom"}, None, None)
    assert "ошибка: boom" in report
