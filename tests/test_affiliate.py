"""Тесты реферальной строки в постах."""

from __future__ import annotations

from unittest import mock

from content_factory.integrations.affiliate import (
    build_affiliate_line,
    resolve_link,
    should_show,
)

CONFIG = {
    "enabled": True,
    "link": "https://bingxdao.com/invite/WYYEGK/",
    "every_n_posts": 3,
    "disclaimer": "Ad · not available in the US, UK.",
}


def test_build_en_line() -> None:
    line = build_affiliate_line(CONFIG, language="en", channel_id="crypto-news")
    assert line.startswith("🤝 Trade crypto on BingX")
    assert "https://bingxdao.com/invite/WYYEGK/" in line
    assert "Ad · not available" in line


def test_build_es_line() -> None:
    line = build_affiliate_line(CONFIG, language="es")
    assert "Opera con cripto" in line
    assert "https://bingxdao.com/invite/WYYEGK/" in line


def test_custom_texts_override() -> None:
    config = {**CONFIG, "texts": {"en": "Partner: {link}"}}
    line = build_affiliate_line(config, language="en")
    assert line.split("\n")[0] == "Partner: https://bingxdao.com/invite/WYYEGK/"


def test_disabled_or_missing_link() -> None:
    assert build_affiliate_line({"enabled": False, "link": "https://x.io/r/1"}) == ""
    assert build_affiliate_line({"enabled": True, "link": ""}) == ""
    assert build_affiliate_line({"enabled": True, "link": "javascript:alert(1)"}) == ""


def test_env_override_per_channel() -> None:
    with mock.patch.dict(
        "os.environ",
        {"AFFILIATE_LINK_CRYPTO_NEWS": "https://bingx.com/r/env", "AFFILIATE_LINK": "https://fallback.io/r"},
        clear=False,
    ):
        assert resolve_link(CONFIG, "crypto-news") == "https://bingx.com/r/env"
        assert resolve_link(CONFIG, "other") == "https://fallback.io/r"
    # без env — ссылка из конфига
    assert resolve_link(CONFIG, "crypto-news") == "https://bingxdao.com/invite/WYYEGK/"


def test_should_show_frequency() -> None:
    assert should_show(0, 3) is True
    assert should_show(1, 3) is False
    assert should_show(3, 3) is True
    assert should_show(5, 0) is True
