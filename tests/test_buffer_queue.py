"""Tests for the Buffer daily queue (no network)."""

from scripts.buffer_queue import build_text, clip, hub_link

PIN = {
    "title": "Cheap Europe city breaks under $300",
    "description": "Budget city breaks in Europe: cheapest months, carry-on tips and booking windows.",
    "affiliate": True,
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
