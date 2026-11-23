"""Regression tests for tracked travel CTAs and attribution plumbing."""

from __future__ import annotations

import json
from pathlib import Path

from content_factory.integrations.tracked_links import guide_code, pin_code, tracker_url


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def test_tracker_url_keeps_attribution_params():
    url = tracker_url("tf-guide-01-europe-for-under-300", epik="abc", click_id="xyz", utm_source="pinterest")
    assert url.startswith("https://links-tracker.valdislav-n.workers.dev/r/tf-guide-01-europe-for-under-300?")
    assert "epik=abc" in url
    assert "click_id=xyz" in url
    assert "utm_source=pinterest" in url


def test_stable_codes():
    assert guide_code("01-europe-for-under-300") == "tf-guide-01-europe-for-under-300"
    assert pin_code("01-europe-for-under-300") == "tf-pin-01-europe-for-under-300"


def test_us_landing_has_only_tracked_partner_links():
    text = (DOCS / "flight-hotel-us" / "index.html").read_text(encoding="utf-8")
    assert text.count("/r/us-") >= 50
    assert "tpk.ro" not in text
    assert "cf-attribution.js" in text
    assert 'data-next="thanks/"' in text
    assert "click_id" in text


def test_thanks_page_downloads_pdf_without_leaving_site():
    text = (DOCS / "flight-hotel-us" / "thanks" / "index.html").read_text(encoding="utf-8")
    assert "URL.createObjectURL" in text
    assert 'id="pdf-download"' in text
    assert "/r/us-kiwitaxi" in text
    assert "tpk.ro" not in text


def test_travel_articles_use_tracked_cta_and_attribution_script():
    text = (DOCS / "travel" / "europe-under-300.html").read_text(encoding="utf-8")
    assert "/r/tf-guide-01-europe-for-under-300" in text
    assert "cf-attribution.js" in text
    assert "/go/" not in text


def test_pinterest_blog_pages_have_tracked_links():
    for name in (
        "cheap-city-breaks-europe-2026.html",
        "flexible-dates-cheaper-flights.html",
        "how-to-find-cheap-flights-2026.html",
        "train-bus-plane-europe-compare.html",
    ):
        text = (DOCS / "travel-finds" / "blog" / name).read_text(encoding="utf-8")
        assert "cf-attribution.js" in text
        assert "tpk.ro" not in text
        assert "/r/tf-blog-" in text or name == "train-bus-plane-europe-compare.html"


def test_affiliate_pin_sidecars_and_csv_use_tracker():
    pins = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (DOCS / "assets" / "pins").glob("*.json")
        if path.name != "index.json"
    ]
    for pin in pins:
        if pin.get("affiliate"):
            assert "/r/tf-pin-" in (pin.get("pin") or {}).get("link", "")
    csv_text = (DOCS / "pinterest-import.csv").read_text(encoding="utf-8")
    assert "/r/tf-pin-" in csv_text
    assert "/go/" not in csv_text
