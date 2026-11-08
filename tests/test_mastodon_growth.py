"""Тесты программы роста Mastodon (без сети)."""

from __future__ import annotations

from scripts.mastodon_growth import age_hours, is_interesting_account


def test_age_hours_parses_utc() -> None:
    assert age_hours("2020-01-01T00:00:00.000Z") > 1000
    assert age_hours(None) > 1e8


def test_account_filter_accepts_active_human() -> None:
    config = {"follow": {"min_followers": 10, "min_statuses": 10, "max_followers": 100000, "require_bio": True}}
    account = {
        "bot": False,
        "locked": False,
        "followers_count": 120,
        "statuses_count": 500,
        "note": "Crypto analyst. Bitcoin, macro, on-chain data.",
    }
    assert is_interesting_account(account, config) is True


def test_account_filter_rejects_bot_locked_and_tiny() -> None:
    config = {"follow": {"min_followers": 10, "min_statuses": 10, "require_bio": True}}
    assert is_interesting_account({"bot": True, "followers_count": 100, "statuses_count": 100, "note": "x" * 20}, config) is False
    assert is_interesting_account({"locked": True, "followers_count": 100, "statuses_count": 100, "note": "x" * 20}, config) is False
    assert is_interesting_account({"followers_count": 2, "statuses_count": 100, "note": "x" * 20}, config) is False
    assert is_interesting_account({"followers_count": 100, "statuses_count": 3, "note": "x" * 20}, config) is False
    assert is_interesting_account({"followers_count": 100, "statuses_count": 100, "note": "short"}, config) is False
