"""Discord получает посты только из трёх английских каналов.

Иначе один webhook принимает ~64 сообщения в день из шести каналов и лента
превращается в свалку.
"""

from __future__ import annotations

from content_factory.config import Settings, load_channels


def test_discord_only_for_english_channels() -> None:
    settings = Settings.load(load_env=False)
    english = {ch.id for ch in load_channels(settings, path="config/channels.en.yaml")}
    spanish = {ch.id for ch in load_channels(settings, path="config/channels.es.yaml")}

    en_with_discord = {
        ch.id for ch in load_channels(settings, path="config/channels.en.yaml")
        if "discord" in ch.publisher_ids
    }
    es_with_discord = {
        ch.id for ch in load_channels(settings, path="config/channels.es.yaml")
        if "discord" in ch.publisher_ids
    }

    assert en_with_discord == english, "все английские каналы должны публиковаться в Discord"
    assert es_with_discord == set(), f"испанские каналы не должны идти в Discord: {sorted(es_with_discord & spanish)}"
