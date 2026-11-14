"""Лендинг и конфиг каналов не должны расходиться.

Регрессия: на странице могло стоять «6 каналов», когда в сети их пять
(или наоборот), а карточки вели на удалённый канал.
"""

from __future__ import annotations

from scripts.check_landing_channels import check, declared_counts, load_channels, parse_landing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_landing_matches_channel_config() -> None:
    result = check()
    assert result["ok"], result["problems"]


def test_every_channel_has_card_and_link() -> None:
    channels = load_channels()
    page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    cards = parse_landing(page)
    assert len(channels) == len(cards) == 7
    assert {c["url"] for c in channels} == {c["url"] for c in cards}


def test_declared_counts_match_reality() -> None:
    page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    total = len(load_channels())
    for label, value in declared_counts(page).items():
        assert value == total, f"{label}: {value} != {total}"
