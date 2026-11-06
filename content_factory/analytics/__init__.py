"""Сбор и визуализация аналитики контент-завода.

collector — метрики каналов (подписчики через Bot API, посты/источники/темы
из SQLite); report — самодостаточные HTML/Markdown-отчёты без внешних CDN.
"""
from __future__ import annotations

from .collector import (
    collect_all,
    collect_channel_metrics,
    collect_post_views,
    fetch_subscribers,
    top_sources_from_posts,
    top_terms_from_posts,
)
from .report import build_report, render_html, render_markdown, save_report

__all__ = [
    "collect_all",
    "collect_channel_metrics",
    "collect_post_views",
    "fetch_subscribers",
    "top_sources_from_posts",
    "top_terms_from_posts",
    "build_report",
    "render_html",
    "render_markdown",
    "save_report",
]
