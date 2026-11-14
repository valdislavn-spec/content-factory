"""Карточка поста: заголовок без служебной шапки, тело без дублей и обрывков."""

from __future__ import annotations

from types import SimpleNamespace as NS

from content_factory.cards import _digest_body, _extract_source, _guess_headline, render_post_card

DIGEST = (
    "🏆 Digest · Nov 12, 2026\n\n"
    "📌 2026 NFL midseason award rankings: MVP picks, top rookies, OPOY, DPOY, coaches — "
    "The article lists midseason award rankings for the 2026NFL through Week 9, covering MVP, top rookies… ESPN / NFL\n\n"
    "📈 For Week 9, Next Gen Stats outpaced the McAfee alt cast again — Next Gen Stats alt cast had "
    "more viewers than the McAfee alt cast for Week 9. Pro Football Talk\n"
)


def test_headline_has_no_service_header() -> None:
    headline = _guess_headline(DIGEST)
    assert "Digest" not in headline
    assert "Nov 12" not in headline
    assert headline.startswith("2026 NFL midseason award")
    assert len(headline) <= 80


def test_headline_keeps_news_not_summary_tail() -> None:
    assert "The article lists" not in _guess_headline(DIGEST)


def test_source_extracted() -> None:
    assert _extract_source(DIGEST) == "ESPN / NFL"


def test_digest_body_items_are_clean() -> None:
    body = _digest_body(DIGEST, "ESPN / NFL")
    items = body.split("\n")
    assert 1 <= len(items) <= 3
    assert all(item.startswith("— ") for item in items)
    assert "2026NFL" not in body          # склейка цифры и слова
    assert "ESPN / NFL" not in body       # источник не дублируется в теле
    assert "Pro Football Talk" not in body


def test_card_render_has_no_service_text(tmp_path) -> None:
    post = NS(plain_text=DIGEST, meta={"format": "digest"}, headline="", title="", hashtags=["#NFL"], id="demo")
    channel = NS(id="sport-news", language="en", title="US Sports News", telegram_username="SPORTNews0007")
    path = render_post_card(post, channel, NS(data_dir=str(tmp_path)))
    assert path is not None and path.exists() and path.stat().st_size > 20_000


def test_card_button_points_to_source() -> None:
    import json as _json
    from content_factory.publishers.telegram import TelegramPublisher

    post = NS(html='Смотрите <a href="https://www.coindesk.com/markets/x">источник</a>', text="", meta={})
    channel = NS(language="en", public_url="https://t.me/HOOPY0007")
    markup = TelegramPublisher._card_reply_markup(post, channel)
    assert markup, "кнопка должна появиться"
    data = _json.loads(markup)
    button = data["inline_keyboard"][0][0]
    assert button["url"] == "https://www.coindesk.com/markets/x"
    assert button["text"] == "Read the source"


def test_card_button_falls_back_to_channel() -> None:
    import json as _json
    from content_factory.publishers.telegram import TelegramPublisher

    post = NS(html="Текст без ссылок", text="", meta={})
    channel = NS(language="es", public_url="https://t.me/TechnologiesNews01")
    data = _json.loads(TelegramPublisher._card_reply_markup(post, channel))
    assert data["inline_keyboard"][0][0]["url"] == "https://t.me/TechnologiesNews01"
    assert data["inline_keyboard"][0][0]["text"] == "Abrir el canal"


def test_card_button_skips_telegram_links() -> None:
    from content_factory.publishers.telegram import TelegramPublisher

    post = NS(html='<a href="https://t.me/HOOPY0007/123">пост</a> <a href="https://example.com/a">статья</a>', text="", meta={})
    channel = NS(language="ru", public_url="https://t.me/HOOPY0007")
    import json as _json
    data = _json.loads(TelegramPublisher._card_reply_markup(post, channel))
    assert data["inline_keyboard"][0][0]["url"] == "https://example.com/a"
