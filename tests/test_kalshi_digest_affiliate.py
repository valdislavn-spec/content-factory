"""Tests for the once-a-day affiliate line in the Kalshi digest."""

from datetime import datetime, timezone

from scripts.kalshi_digest import affiliate_line

CONFIG = {
    "affiliate": {
        "enabled": True,
        "url": "https://kalshi.com/r/TEST",
        "disclosure": "Ad",
        "once_per_day": True,
        "daily_hour_utc": 12,
        "text_en": "🔗 Trade on Kalshi: {url} · {disclosure}",
        "text_es": "🔗 Opera en Kalshi: {url} · {disclosure}",
    }
}


def test_affiliate_only_during_daily_hour():
    at_12 = datetime(2026, 11, 8, 12, 15, tzinfo=timezone.utc)
    at_21 = datetime(2026, 11, 8, 21, 15, tzinfo=timezone.utc)
    assert affiliate_line(CONFIG, "en", at_12) == "🔗 Trade on Kalshi: https://kalshi.com/r/TEST · Ad"
    assert affiliate_line(CONFIG, "en", at_21) == ""


def test_affiliate_language_and_disabled():
    at_12 = datetime(2026, 11, 8, 12, 15, tzinfo=timezone.utc)
    assert affiliate_line(CONFIG, "es", at_12).startswith("🔗 Opera en Kalshi")
    assert affiliate_line({"affiliate": {"enabled": False, "url": "x"}}, "en", at_12) == ""
    assert affiliate_line({"affiliate": {"enabled": True, "url": ""}}, "en", at_12) == ""
    assert affiliate_line({}, "en", at_12) == ""
