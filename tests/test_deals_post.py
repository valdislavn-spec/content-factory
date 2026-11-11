import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.deals_post import (  # noqa: E402
    build_report,
    discount_percent,
    render_item,
    with_utm,
)


def _queue():
    return {
        "programs": {
            "sugargoo": {
                "name": "Sugargoo",
                "status": "ready",
                "link": "https://www.sugargoo.com/register?memberId=123",
                "utm_campaign": "deals_sugargoo",
            },
            "temu": {"name": "Temu", "status": "pending", "link": ""},
        },
        "items": [
            {
                "id": "a1",
                "channel": "tech-ai-es",
                "program": "sugargoo",
                "format": "A",
                "status": "ready",
                "title": "Auriculares",
                "price": "19 €",
                "old_price": "49 €",
                "hook": "Bluetooth 5.4",
            },
            {
                "id": "c1",
                "channel": "futbol-es",
                "program": "sugargoo",
                "format": "C",
                "status": "ready",
                "title": "Camiseta",
                "price": "15 €",
                "steps": "elige talla",
                "delivery": "12–20 días",
            },
            {
                "id": "p1",
                "channel": "tech-ai-es",
                "program": "temu",
                "format": "A",
                "status": "pending",
                "title": "pending",
                "price": "9 €",
            },
        ],
    }


def test_discount_percent():
    assert discount_percent("35 €", "12 €") == 66
    assert discount_percent(None, "12 €") is None
    assert discount_percent("10 €", "12 €") is None


def test_with_utm():
    link = with_utm("https://example.com/reg?memberId=1", "tech-ai-es", "deals_sugargoo")
    assert "utm_source=tg_tech_ai_es" in link
    assert "utm_medium=telegram" in link
    assert "utm_campaign=deals_sugargoo" in link


def test_render_format_a_es():
    queue = _queue()
    text = render_item(queue["items"][0], queue["programs"]["sugargoo"], shorten=False)
    assert text is not None
    assert "Precio: 49 € → 19 € (61%)" in text
    assert "Enlace de afiliado" in text
    assert "utm_campaign=deals_sugargoo" in text


def test_render_format_c():
    queue = _queue()
    text = render_item(queue["items"][1], queue["programs"]["sugargoo"], shorten=False)
    assert text is not None
    assert "vía agente" in text
    assert "elige talla" in text


def test_build_report_skips_pending():
    report = build_report(_queue(), shorten=False)
    ids = {post["id"] for post in report["posts"]}
    assert ids == {"a1", "c1"}
    assert any(row["id"] == "p1" for row in report["skipped"])
