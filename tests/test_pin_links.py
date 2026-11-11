"""Ссылки пинов должны быть активными (не заглушками).

Проверяем офлайн-валидатор, резолвер партнёрских ссылок, артефакты батча
(``docs/assets/pins-v5``), CSV для Pinterest и legacy-батч ``qr-v2``.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from content_factory.integrations import partner_links as pl
from content_factory.channel_cards import TRAVEL_OFFERS

ROOT = Path(__file__).resolve().parents[1]
PINS_V5 = ROOT / "docs" / "assets" / "pins-v5"
QR_V2 = ROOT / "docs" / "assets" / "pins" / "qr-v2"
CSV_V5 = ROOT / "docs" / "pinterest-import-v5.csv"
SKIP = {"index.json", "meta.json", "qa-report.json"}


def v5_sidecars():
    if not PINS_V5.exists():
        pytest.skip("docs/assets/pins-v5 отсутствует")
    paths = [path for path in sorted(PINS_V5.rglob("*.json")) if path.name not in SKIP]
    if not paths:
        pytest.skip("нет sidecar-ов pins-v5")
    return paths


# ---------------------------------------------------------------------------
# Валидатор и резолвер
# ---------------------------------------------------------------------------


def test_validate_accepts_live_partner_links():
    for url in (
        "https://aviasales.tpk.ro/2ZW95Xpf",
        "https://localrent.tpk.ro/vGHu8Vuj",
        "https://valdislavn-spec.github.io/content-factory/",
    ):
        assert pl.validate_link(url) == []


def test_validate_rejects_placeholders_and_bad_schemes():
    bad = {
        "https://is.gd/BaliTrip": "заглушка",
        "https://v.gd/abc": "заглушка",
        "https://example.com/pin": "заглушка",
        "http://aviasales.tpk.ro/2ZW95Xpf": "https://",
        "": "пустая",
        "not a url": "https://",
        "https://example.com/with space": "пробел",
        "https://example.com/" + "x" * 600: "длиннее",
    }
    for url, fragment in bad.items():
        problems = pl.validate_link(url)
        assert problems, url
        assert any(fragment in problem for problem in problems), (url, problems)


def test_resolve_program_link_prefers_program_then_fallback():
    links = {"aviasales": "https://aviasales.tpk.ro/2ZW95Xpf"}
    fallback = "https://valdislavn-spec.github.io/content-factory/"
    assert pl.resolve_program_link("aviasales", links, fallback) == links["aviasales"]
    assert pl.resolve_program_link("unknown", links, fallback) == fallback
    assert pl.resolve_program_link("unknown", links, "") == ""


def test_config_links_are_active():
    links = pl.load_partner_links()
    for program in ("aviasales", "yesim", "localrent", "compensair"):
        assert program in links, program
        assert pl.validate_link(links[program]) == [], (program, links[program])


def test_live_check_reports_offline_placeholder_without_network():
    check = pl.check_link_live("https://is.gd/BaliTrip", timeout=1)
    assert check.ok is False
    assert "заглушка" in check.reason or "ссылка" in check.reason


# ---------------------------------------------------------------------------
# Артефакты v5
# ---------------------------------------------------------------------------


def test_v5_payload_links_are_active_https():
    for path in v5_sidecars():
        meta = json.loads(path.read_text(encoding="utf-8"))
        payload = meta.get("pin") or {}
        link = str(payload.get("link") or "")
        assert pl.validate_link(link) == [], (path.name, link)
        assert meta.get("image_url", "").startswith("https://"), path.name


def test_v5_image_urls_point_to_published_batch():
    for path in v5_sidecars():
        meta = json.loads(path.read_text(encoding="utf-8"))
        image_url = str(meta.get("image_url") or "")
        assert "/assets/pins-v5/" in image_url, (path.name, image_url)
        assert image_url.endswith(".png"), (path.name, image_url)


def test_photo_pin_definitions_use_programs_not_hardcoded_short_links():
    source = (ROOT / "scripts" / "build_photo_pins.py").read_text(encoding="utf-8")
    assert "is.gd" not in source
    assert '"program": "aviasales"' in source
    assert '"program": "localrent"' in source
    assert "validate_link" in source


def test_pinterest_csv_links_are_active():
    if not CSV_V5.exists():
        pytest.skip("docs/pinterest-import-v5.csv отсутствует")
    with CSV_V5.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows, "CSV пуст"
    for row in rows:
        assert row.get("Link"), row.get("Title")
        assert pl.validate_link(row["Link"]) == [], (row.get("Title"), row["Link"])
        assert pl.validate_link(row["Media URL"]) == [], row.get("Title")


# ---------------------------------------------------------------------------
# Legacy qr-v2 и channel cards
# ---------------------------------------------------------------------------


def test_qr_v2_meta_links_are_active():
    meta_path = QR_V2 / "meta.json"
    if not meta_path.exists():
        pytest.skip("qr-v2 отсутствует")
    entries = json.loads(meta_path.read_text(encoding="utf-8"))
    assert entries
    for entry in entries:
        assert pl.validate_link(entry.get("url", "")) == [], entry.get("slug")
        assert entry.get("program"), entry.get("slug")


def test_channel_card_travel_offers_have_real_links():
    assert TRAVEL_OFFERS
    for offer in TRAVEL_OFFERS:
        assert "is.gd" not in offer["display"], offer
        assert pl.validate_link(offer["url"]) == [], offer


def test_no_is_gd_left_in_pin_generators():
    for name in ("build_photo_pins.py", "build_qr_pins_v2.py", "generate_pins.py"):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "is.gd" not in source, name
