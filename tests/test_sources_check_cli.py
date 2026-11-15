"""Strict-режим проверки источников."""

from types import SimpleNamespace
from unittest import mock

from content_factory import cli


def _run(source_result, strict=True):
    source = SimpleNamespace(name="test", type="rss", enabled=True)
    channel = SimpleNamespace(id="test", title="Test", sources=[source])
    args = SimpleNamespace(channel="all", strict=strict)
    with mock.patch.object(cli, "select_channels", return_value=[channel]), mock.patch(
        "content_factory.sources.check_source", return_value=source_result
    ):
        return cli.cmd_sources_check(args, None)


def test_strict_fails_on_broken_source():
    assert _run((False, "HTTP 500")) == 1


def test_strict_fails_on_empty_source():
    assert _run((True, "Источник доступен, но элементов не найдено")) == 1


def test_strict_passes_when_all_sources_return_items():
    assert _run((True, "Источник доступен, получено статей: 2")) == 0
