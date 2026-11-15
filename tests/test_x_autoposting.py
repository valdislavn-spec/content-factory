"""Конфигурация X-автопостинга: один аккаунт — один канал."""

from __future__ import annotations

from content_factory.config import Settings, load_channels


def test_x_is_enabled_only_for_crypto_news() -> None:
    settings = Settings.load(load_env=False)
    channels = load_channels(settings, path="config/channels.en.yaml")
    with_x = {ch.id for ch in channels if "x" in ch.publisher_ids}

    assert with_x == {"crypto-news"}, (
        "X free tier ~500 постов/мес; один аккаунт @NValdislav должен "
        f"обслуживать только crypto-news, а не {sorted(with_x)}"
    )
