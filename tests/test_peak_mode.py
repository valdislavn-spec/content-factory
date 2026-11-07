"""Тесты пикового режима: ночь/день, микс форматов, парсер трендов."""
from content_factory.config import load_channels
from content_factory.pipeline import day_formats, slot_is_night, slot_phase
from content_factory.trends import parse_google_trends_rss


def _channel(channel_id: str, lang_path: str = "config/channels.en.yaml"):
    channels = load_channels(path=lang_path)
    return next(channel for channel in channels if channel.id == channel_id)


def test_night_and_day_slots():
    channel = _channel("ai-news")
    assert slot_is_night(channel, "23:40") is True
    assert slot_is_night(channel, "02:20") is True
    assert slot_is_night(channel, "06:00") is True
    assert slot_is_night(channel, "07:00") is False
    assert slot_is_night(channel, "09:00") is False
    assert slot_is_night(channel, "22:00") is False


def test_phases_and_peak_mix():
    channel = _channel("ai-news")
    assert slot_phase(channel, "08:00") == "peak"
    assert slot_phase(channel, "13:00") == "peak"
    assert slot_phase(channel, "20:00") == "peak"
    assert slot_phase(channel, "10:20") == "day"
    assert slot_phase(channel, "23:00") == "night"
    peak = day_formats(channel, "peak")
    day = day_formats(channel, "day")
    assert peak.count("interactive") >= day.count("interactive")
    assert peak.count("story") <= day.count("story")


def test_day_formats_mix_interleaved():
    channel = _channel("ai-news")
    formats = day_formats(channel)
    # пропорции 30/40/30 и форматы идут вперемешку, а не блоками
    assert formats[0] != formats[1] != formats[2]
    assert formats.count("analysis") >= formats.count("story")
    assert "interactive" in formats and "digest" not in formats


def test_night_max_chars_and_timezone():
    channel = _channel("ai-news")
    assert channel.timezone_offset == -5
    assert channel.night_max_chars == 900
    assert len(channel.schedule) == 16
    es_channel = _channel("futbol-es", "config/channels.es.yaml")
    assert es_channel.timezone_offset == -6


def test_google_trends_rss_parser_ignores_news_headlines():
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>
      <item><title>openai</title>
        <ht:news_item><ht:news_item_title>A very long news headline</ht:news_item_title></ht:news_item>
      </item>
      <item><title>nvidia</title></item>
    </channel></rss>"""
    values = parse_google_trends_rss(xml)
    assert values == ["openai", "nvidia"]
