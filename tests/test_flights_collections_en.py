"""Tests for the English flight collections (no network)."""

import json
import re
from datetime import date, datetime

from content_factory import flights_collections as fc
from content_factory import flights_collections_en as en

DEALS = [
    fc.Deal("ALA", "CIT", 6170, date(2026, 11, 27), date(2026, 11, 27), "DV", "https://aviasales.tpk.ro/a"),
    fc.Deal("ALA", "NQZ", 7612, date(2027, 1, 26), date(2027, 1, 27), "DV", "https://aviasales.tpk.ro/b"),
    fc.Deal("ALA", "TAS", 10254, date(2027, 2, 11), date(2027, 2, 19), "HH", "https://aviasales.tpk.ro/c"),
    fc.Deal("MSQ", "IST", 21305, date(2026, 11, 30), date(2026, 12, 16), "DP", "https://aviasales.tpk.ro/d"),
]


def test_convert_to_usd_uses_rate():
    converted = en.convert_to_usd(DEALS, 0.0125)
    assert [d.price for d in converted] == [77, 95, 128, 266]
    assert converted[0].city == "Шымкент"  # geo name stays shared


def test_build_keeps_kazakhstan_departures_only():
    cols = en.build(en.convert_to_usd(DEALS, 0.0125), min_deals=1)
    all_origins = {d.origin for c in cols for d in c.deals}
    assert all_origins == {"ALA"}  # Минск в английский набор не попадает


def test_thresholds_are_usd():
    cols = {c.slug: c for c in en.build(en.convert_to_usd(DEALS, 0.0125), min_deals=1)}
    assert [d.price for d in cols["under-150"].deals] == [77, 95, 128]
    assert [d.price for d in cols["under-100"].deals] == [77, 95]


def test_money_and_dates():
    assert en.usd(75) == "$75"
    assert en.usd(1429) == "$1,429"
    assert en.fmt_dates(date(2027, 2, 11), date(2027, 2, 19)) == "11–19 Feb"
    assert en.fmt_dates(date(2027, 1, 27), date(2027, 2, 2)) == "27 Jan – 2 Feb"
    assert en.fmt_dates(date(2026, 11, 27), date(2026, 11, 27)) == "27 Nov"


def test_page_has_usd_and_no_roubles():
    cols = en.build(en.convert_to_usd(DEALS, 0.0125), min_deals=1)
    page = en.render_page(cols[0], cols, datetime(2026, 11, 12, 15, 4), 0.0125, "test")
    assert "<title>" in page and "<h1" in page
    assert "$" in page
    assert "₽" not in page  # цены только в долларах
    assert '"priceCurrency": "USD"' in page
    assert "RUB at 0.0125" in page  # курс раскрыт, а не спрятан
    assert "Kazakhstan" in page and "Казахстан" not in page  # страны по-английски
    assert 'hreflang' not in page  # не обещаем то, чего нет


def test_page_jsonld_is_valid():
    cols = en.build(en.convert_to_usd(DEALS, 0.0125), min_deals=1)
    page = en.render_page(cols[0], cols, None, 0.0125, "test")
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        json.loads(block)


def test_post_english_and_within_limit():
    cols = en.build(en.convert_to_usd(DEALS, 0.0125), min_deals=1)
    post = en.render_post(cols[0], datetime(2026, 11, 12, 15, 4))
    assert len(post) <= fc.TELEGRAM_LIMIT
    assert "#ad" in post
    assert "₽" not in post
    assert "/collections/en/" in post


def test_night_plural():
    cols = en.build(en.convert_to_usd(DEALS, 0.0125), min_deals=1)
    post = en.render_post(cols[0], datetime(2026, 11, 12, 15, 4))
    assert "1 night" in post and "1 nights" not in post


def test_fx_fallback_is_sane():
    rate, note = en.FALLBACK_RUB_USD, "fallback"
    assert 0.001 < rate < 0.1
    converted = en.convert_to_usd([DEALS[0]], rate)
    assert converted[0].price >= 1
