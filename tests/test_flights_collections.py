"""Тесты подборок дешёвых билетов (без сети): разбор витрин и рендер."""

import json
import re
from datetime import date, datetime

from content_factory import flights_collections as fc
from content_factory import flights_geo as geo

PAGE = """
<p style="color:#6b7280;margin:0 0 22px">Updated 11 Nov 2026, 18:54 UTC · prices in RUB</p>
<table><tbody>
<tr><td style="padding:10px 12px">CIT <span style="color:#9ca3af">(CIT)</span></td>
    <td style="padding:10px 12px;white-space:nowrap">2026-11-27 → 2026-11-27</td>
    <td style="padding:10px 12px">DV</td>
    <td style="padding:10px 12px;font-weight:600;white-space:nowrap">6 170 ₽<div style="color:#6b7280">≈ 31 000 ₸</div></td>
    <td style="padding:10px 12px"><a href="https://aviasales.tpk.ro/aaa" style="color:#2563eb">Book →</a></td></tr>
<tr><td style="padding:10px 12px">Istanbul <span style="color:#9ca3af">(IST)</span></td>
    <td style="padding:10px 12px;white-space:nowrap">2027-02-08 → 2027-02-16</td>
    <td style="padding:10px 12px">VF</td>
    <td style="padding:10px 12px;font-weight:600;white-space:nowrap">15 821 ₽</td>
    <td style="padding:10px 12px"><a href="https://aviasales.tpk.ro/bbb" style="color:#2563eb">Book →</a></td></tr>
<tr><td style="padding:10px 12px">Dushanbe <span style="color:#9ca3af">(DYU)</span></td>
    <td style="padding:10px 12px;white-space:nowrap">2026-12-30 → 2027-01-19</td>
    <td style="padding:10px 12px">SZ</td>
    <td style="padding:10px 12px;font-weight:600;white-space:nowrap">18 120 ₽</td>
    <td style="padding:10px 12px"><a href="https://aviasales.tpk.ro/ccc" style="color:#2563eb">Book →</a></td></tr>
<tr><td style="padding:10px 12px">Antalya <span style="color:#9ca3af">(AYT)</span></td>
    <td style="padding:10px 12px;white-space:nowrap">2026-11-16 → 2026-12-14</td>
    <td style="padding:10px 12px">DP</td>
    <td style="padding:10px 12px;font-weight:600;white-space:nowrap">25 949 ₽</td>
    <td style="padding:10px 12px"><a href="https://aviasales.tpk.ro/ddd" style="color:#2563eb">Book →</a></td></tr>
</tbody></table>
"""


def test_parse_page_extracts_deals():
    deals = fc.parse_page(PAGE, "ALA")
    assert len(deals) == 4
    assert [d.dest for d in deals] == ["CIT", "IST", "DYU", "AYT"]
    assert [d.price for d in deals] == [6170, 15821, 18120, 25949]
    assert deals[1].dep == date(2027, 2, 8)
    assert deals[1].ret == date(2027, 2, 16)
    assert deals[1].nights == 8
    assert deals[0].link.endswith("/aaa")


def test_parse_updated():
    assert fc.parse_updated(PAGE) == datetime(2026, 11, 11, 18, 54)


def test_city_names_come_from_dictionary():
    deals = fc.parse_page(PAGE, "ALA")
    assert deals[0].city == "Шымкент"  # раньше на витрине было «CIT (CIT)»
    assert deals[1].city == "Стамбул"
    assert geo.city_name("SCO", "en") == "Aktau"
    assert geo.city_name("ZZZ") == "ZZZ"  # неизвестный код не ломает вывод


def test_money_and_dates_ru():
    assert fc.money(6170) == "6 170 ₽"
    assert fc.fmt_dates(date(2027, 2, 8), date(2027, 2, 16)) == "8–16 февраля"
    assert fc.fmt_dates(date(2027, 1, 27), date(2027, 2, 2)) == "27 января – 2 февраля"
    assert fc.fmt_dates(date(2027, 1, 27), date(2027, 2, 2), short=True) == "27 янв – 2 фев"
    assert fc.fmt_dates(date(2026, 11, 27), date(2026, 11, 27)) == "27 ноября"
    assert fc.fmt_dates(date(2027, 1, 20), date(2027, 1, 27), short=True) == "20–27 янв"


def test_collections_have_no_empty_or_thin_sets():
    deals = fc.parse_page(PAGE, "ALA")
    cols = fc.build_collections(deals, min_deals=2)
    slugs = {c.slug for c in cols}
    assert "turciya" in slugs            # Стамбул + Анталья
    assert "na-nedelyu" in slugs          # Стамбул, Душанбе, Анталья — 7+ ночей
    assert "srednyaya-aziya" not in slugs  # только Душанбе — мало для страницы
    assert "po-kazahstanu" not in slugs    # только Шымкент — тоже мало
    assert "teplye-napravleniya" not in slugs
    for col in cols:
        assert col.count >= 2
        assert col.cheapest == min(d.price for d in col.deals)


def test_page_has_seo_and_affiliate_links():
    deals = fc.parse_page(PAGE, "ALA")
    cols = fc.build_collections(deals, min_deals=2)
    page = fc.render_page(cols[0], cols, datetime(2026, 11, 11, 18, 54))
    assert "<title>" in page and "<h1" in page
    assert '<link rel="canonical" href="https://valdislavn-spec.github.io/content-factory/collections/' in page
    assert '"@type": "BreadcrumbList"' in page
    assert '"@type": "ItemList"' in page
    assert page.count("aviasales.tpk.ro") >= len(cols[0].deals)
    assert "партнёр" in page.lower()


def test_page_jsonld_is_valid_json():
    deals = fc.parse_page(PAGE, "ALA")
    cols = fc.build_collections(deals, min_deals=2)
    page = fc.render_page(cols[0], cols, None)
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    assert blocks
    for block in blocks:
        json.loads(block)


def test_post_fits_telegram_and_has_links():
    deals = fc.parse_page(PAGE, "ALA")
    col = fc.build_collections(deals, min_deals=2)[0]
    post = fc.render_post(col, datetime(2026, 11, 11, 18, 54))
    assert len(post) <= fc.TELEGRAM_LIMIT
    assert "<b>" in post and "<a href=" in post
    assert "#реклама" in post
    assert "https://valdislavn-spec.github.io/content-factory/collections/" in post


def test_post_is_trimmed_for_long_collections():
    deals = [
        fc.Deal("ALA", code, 5000 + i * 100, date(2027, 1, 10), date(2027, 1, 17), "DV",
                "https://aviasales.tpk.ro/%d" % i)
        for i, code in enumerate(["IST", "TAS", "DYU", "BAK", "EVN", "AYT", "TBS", "CIT"])
    ]
    col = fc.Collection("test", "Тест", "Проверка", "✈️", deals)
    post = fc.render_post(col, None)
    assert len(post) <= fc.TELEGRAM_LIMIT
    assert post.count("aviasales.tpk.ro") <= 6  # 5 сделок + CTA


def test_sitemap_update_is_idempotent(tmp_path):
    sitemap = tmp_path / "sitemap.xml"
    sitemap.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset>\n</urlset>\n', encoding="utf-8")
    urls = ["https://example.com/collections/", "https://example.com/collections/turciya/"]
    assert fc.update_sitemap(sitemap, urls, date(2026, 11, 14)) == 2
    assert fc.update_sitemap(sitemap, urls, date(2026, 11, 14)) == 0
    xml = sitemap.read_text(encoding="utf-8")
    assert xml.count("<loc>https://example.com/collections/turciya/</loc>") == 1
    assert "<lastmod>2026-11-14</lastmod>" in xml
    assert xml.rstrip().endswith("</urlset>")


def test_pages_carry_analytics():
    deals = fc.parse_page(PAGE, "ALA")
    cols = fc.build_collections(deals, min_deals=2)
    page = fc.render_page(cols[0], cols, None)
    hub = fc.render_hub(cols, None)
    for html in (page, hub):
        assert "googletagmanager.com/gtag/js" in html
        assert "affiliate_click" in html  # клик по партнёрской ссылке виден в GA4
