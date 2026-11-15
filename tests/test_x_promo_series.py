"""Тесты серии промо-постов для X."""

from __future__ import annotations

from datetime import date, time

from pathlib import Path

from scripts.x_promo_series import load_series, schedule_times, x_weighted_length



def test_x_weighted_length_shortens_urls() -> None:
    text = "Read https://example.com/very/long/path now"
    assert x_weighted_length(text) == len("Read " + "x" * 23 + " now")


def test_series_posts_fit_x_limit() -> None:
    posts = load_series(Path("config/x_promo_series.yaml"))
    assert len(posts) == 11
    for post in posts:
        assert int(post["weighted_len"]) <= 280
        assert "https://" in post["text"]


def test_schedule_two_slots_per_day() -> None:
    slots = schedule_times(date(2030, 1, 1), [time(16), time(22)], 4)
    assert [slot.date() for slot in slots] == [date(2030, 1, 1), date(2030, 1, 1), date(2030, 1, 2), date(2030, 1, 2)]
