"""Tests for the Buffer daily queue (no network)."""

from scripts.buffer_queue import build_assets, build_text, clip, hub_link

CONFIG = {
    "niches": {
        "travel": {
            "emoji": "🧳",
            "hashtags": ["#travel", "#budgettravel", "#citybreak"],
            "cta": "Full guide:",
            "question": "Which city is on your list this year?",
        }
    }
}

PIN = {
    "title": "Cheap Europe city breaks under $300",
    "description": "Budget city breaks in Europe: cheapest months, carry-on tips and booking windows.",
    "affiliate": True,
    "niche": "travel",
}
CHANNEL_X = {"service": "twitter", "max_chars": 280, "utm": {"utm_source": "x"}}
CHANNEL_BSKY = {"service": "bluesky", "max_chars": 300, "utm": {"utm_source": "bsky"}}
CHANNEL_FB = {"service": "facebook", "max_chars": 5000, "utm": {"utm_source": "facebook"}}
HUB = "https://valdislavn-spec.github.io/content-factory/"


def test_hub_link_utm():
    assert hub_link(HUB, {"utm_source": "x"}) == HUB + "?utm_source=x"
    assert hub_link(HUB, {}) == HUB


def test_clip():
    assert clip("a b c", 100) == "a b c"
    assert len(clip("word " * 100, 50)) <= 50


def test_x_text_fits_280():
    text = build_text(PIN, CHANNEL_X, HUB)
    assert len(text) <= 280
    assert "utm_source=x" in text
    assert text.endswith("Ad")


def test_bluesky_text_fits_300():
    text = build_text(PIN, CHANNEL_BSKY, HUB)
    assert len(text) <= 300
    assert "utm_source=bsky" in text


def test_facebook_keeps_description():
    text = build_text(PIN, CHANNEL_FB, HUB)
    assert "Budget city breaks" in text
    assert "utm_source=facebook" in text


def test_x_has_no_hashtags_and_hook_first():
    text = build_text(PIN, CHANNEL_X, HUB, CONFIG)
    assert len(text) <= 280
    assert "#" not in text
    assert text.splitlines()[0] == "Cheap Europe city breaks under $300"


def test_bluesky_emoji_and_tags():
    text = build_text(PIN, CHANNEL_BSKY, HUB, CONFIG)
    assert len(text) <= 300
    assert text.startswith("🧳 ")
    assert "#travel" in text
    assert text.count("#") <= 3


def test_facebook_bullets_and_question():
    text = build_text(PIN, CHANNEL_FB, HUB, CONFIG)
    assert "• " in text
    assert "Which city is on your list this year?" in text
    assert "utm_source=facebook" in text


def test_facebook_long_description_keeps_two_bullets():
    pin = dict(PIN)
    pin["description"] = (
        "Bali in 7 days: what it really costs, where to save, "
        "and when to go to avoid peak season prices."
    )
    text = build_text(pin, CHANNEL_FB, HUB, CONFIG)
    assert text.count("• ") >= 2


def test_unknown_service_falls_back():
    channel = {"service": "mastodon", "max_chars": 500, "utm": {"utm_source": "m"}}
    text = build_text(PIN, channel, HUB, CONFIG)
    assert len(text) <= 500


def test_assets_from_pin_image():
    pin = dict(PIN)
    pin["image_url"] = "https://example.com/article.png"
    assert build_assets(pin) == [{"image": {"url": "https://example.com/article.png"}}]
    pin["image_url"] = ""
    assert build_assets(pin) == []


def test_short_links_and_channel(monkeypatch):
    calls = []

    def fake_shorten(url):
        calls.append(url)
        return "https://tinyurl.com/" + str(len(calls))

    monkeypatch.setattr("scripts.buffer_queue.shorten_url", fake_shorten)
    config = dict(CONFIG)
    config["links"] = {"shorten": True, "channel_default": "https://t.me/HOOPY0007"}
    config["niche_channels"] = {"travel": "https://t.me/AINEWS0007"}
    text = build_text(PIN, CHANNEL_X, HUB, config)
    assert "https://tinyurl.com/" in text
    assert "Telegram: https://t.me/AINEWS0007" in text
    assert "Guide: https://tinyurl.com/" in text
    # сокращаются статья и канал; канал короткий, поэтому остаётся t.me-ссылка
    assert calls, "shortener должен вызываться для ссылки на статью"


def test_image_does_not_break_text_fit():
    pin = dict(PIN)
    pin["image_url"] = "https://example.com/article.png"
    text = build_text(pin, CHANNEL_BSKY, HUB, CONFIG)
    assert len(text) <= 300
