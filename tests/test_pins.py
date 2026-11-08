"""Tests for the Pinterest pin factory (Pillow required; skipped if unavailable)."""

import pytest

pytest.importorskip("PIL")

from content_factory.integrations.pins import (  # noqa: E402
    DISCLOSURE,
    PinSpec,
    load_specs,
    render_pin,
)


def test_load_specs_from_config():
    specs = load_specs("config/pins.yaml")
    assert len(specs) >= 7
    assert specs[0].niche == "travel"
    assert specs[0].headline
    assert specs[0].cta


def test_pinterest_payload_limits():
    spec = PinSpec(
        niche="travel",
        headline="Europe for under $300",
        subtitle="Cheap city breaks",
        link="https://example.com/r/travel",
        title="Europe city breaks under $300",
        description="Budget city breaks and flight deals.",
    )
    payload = spec.pinterest_payload("123456", "https://cdn.example/pin.png")
    assert payload["board_id"] == "123456"
    assert len(payload["title"]) <= 100
    assert len(payload["description"]) <= 500
    assert payload["link"].startswith("https://")
    assert payload["media_source"]["source_type"] == "image_url"


def test_render_pin_dimensions(tmp_path):
    spec = PinSpec(
        niche="travel",
        headline="Bali on a budget",
        subtitle="7 days, beaches and rice terraces",
        bullets=["$35–60/day", "Avoid July–August"],
        cta="Read the guide",
        accent="#2ECC71",
        disclosure=DISCLOSURE,
    )
    image = render_pin(spec, "assets/fonts")
    assert image.size == (1000, 1500)
    path = tmp_path / "pin.png"
    image.save(path)
    assert path.stat().st_size > 20_000


def test_payload_has_no_link_when_affiliate_missing():
    spec = PinSpec(niche="ai", headline="AI tools that save time")
    payload = spec.pinterest_payload("1", "https://cdn.example/p.png")
    assert "link" not in payload or payload["link"] == ""
