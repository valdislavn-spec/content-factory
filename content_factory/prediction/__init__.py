"""Прогнозные рынки (Polymarket/Kalshi/Manifold/Metaculus) — публичные данные."""
from __future__ import annotations

from .market import FETCHERS, fetch_kalshi, fetch_manifold, fetch_markets, fetch_metaculus, fetch_polymarket

__all__ = [
    "FETCHERS",
    "fetch_kalshi",
    "fetch_manifold",
    "fetch_markets",
    "fetch_metaculus",
    "fetch_polymarket",
]
