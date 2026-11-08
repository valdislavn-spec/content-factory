"""Live market line appended to channel posts.

For crypto channels the line looks like:

    📈 BTC $75,861 (+1.2%) · ETH $2,313 (−0.4%) · Kalshi: BTC $75,800–75,899 — 73¢

Prices come from CoinGecko (public, no key). The Kalshi part is optional and
uses the public Kalshi API (KXBTC series by default). Responses are cached on
disk for ``ttl`` seconds so a pipeline tick with several posts makes one call.

The line is best-effort: any network/API failure returns an empty string and
must never break publishing.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
DEFAULT_COINS = ("bitcoin", "ethereum", "solana")
COIN_LABELS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "binancecoin": "BNB",
    "ripple": "XRP",
    "dogecoin": "DOGE",
}
CACHE_TTL_SEC = 900
USER_AGENT = "content-factory-marketline/1.0"


def _http_json(url: str, timeout: float = 10.0) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _cache_path() -> Path:
    base = os.environ.get("CONTENT_FACTORY_DATA_DIR") or "data"
    return Path(base) / "cache" / "marketline.json"


def _read_cache(path: Path, ttl: int) -> Dict[str, Any]:
    try:
        if path.exists() and time.time() - path.stat().st_mtime <= ttl:
            return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 - cache must never break publishing
        pass
    return {}


def _write_cache(path: Path, data: Dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def format_usd(price: float) -> str:
    if price >= 1000:
        return "${:,.0f}".format(price)
    if price >= 1:
        return "${:,.2f}".format(price)
    return "${:,.4f}".format(price)


def format_change(change: Optional[float]) -> str:
    if change is None:
        return ""
    arrow = "▲" if change > 0 else ("▼" if change < 0 else "•")
    return " (%s%.1f%%)" % (arrow, abs(change))


def fetch_crypto_prices(
    coins: Sequence[str] = DEFAULT_COINS,
    timeout: float = 10.0,
    fetcher: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """CoinGecko simple price for the given coin ids."""
    ids = ",".join(coin for coin in coins if coin)
    url = "%s?ids=%s&vs_currencies=usd&include_24hr_change=true" % (COINGECKO_URL, urllib.parse.quote(ids))
    data = (fetcher or _http_json)(url)
    return data if isinstance(data, dict) else {}


_INTERESTING_TITLE_WORDS = (
    "bitcoin", "btc", "above", "below", "exceed", "cross", "hit", "over", "under", "reach",
)


def _interesting_btc_market(markets: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Pick a liquid price-target BTC market (not the boring intraday range)."""
    from .kalshi import market_volume, yes_price_cents

    best: Optional[Dict[str, Any]] = None
    best_volume = 0.0
    for market in markets:
        title = str(market.get("title") or "").strip()
        subtitle = str(market.get("yes_sub_title") or "").strip()
        haystack = (title + " " + subtitle).lower()
        if not any(word in haystack for word in ("bitcoin", "btc")):
            continue
        if not any(word in haystack for word in _INTERESTING_TITLE_WORDS[2:]):
            continue
        price = yes_price_cents(market)
        volume = market_volume(market)
        if price is None or not (1 <= price <= 99) or volume <= 0:
            continue
        if volume > best_volume:
            best, best_volume = market, volume
    return best


def kalshi_btc_line(
    series_tickers: Sequence[str] | str = ("KXBTCMAX100", "KXBTCABOVE100BY", "KXBTCABOVE85BY", "KXBTC"),
    timeout: float = 10.0,
    markets_fetcher: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
) -> str:
    """Short Kalshi line: a liquid BTC price-target market, else top-volume one."""
    if isinstance(series_tickers, str):
        series_tickers = (series_tickers,)
    tickers = [str(t).strip() for t in series_tickers if str(t).strip()]
    if not tickers:
        return ""

    def _default_fetch(ticker: str) -> List[Dict[str, Any]]:
        from .kalshi import KalshiClient

        return KalshiClient().markets(status="open", limit=100, series_ticker=ticker)

    fetch = markets_fetcher or _default_fetch
    collected: List[Dict[str, Any]] = []
    for ticker in tickers:
        try:
            collected.extend(fetch(ticker))
        except Exception:  # noqa: BLE001 - best effort
            continue
    if not collected:
        return ""
    from .kalshi import market_volume, yes_price_cents

    market = _interesting_btc_market(collected)
    if market is None:
        market = sorted(collected, key=market_volume, reverse=True)[0]
    label = _kalshi_label(market)
    price = yes_price_cents(market)
    if not label or price is None:
        return ""
    return "Kalshi: %s — %d¢" % (label, price)


def _kalshi_label(market: Dict[str, Any]) -> str:
    """Short but self-explanatory label: asset + target + deadline."""
    import re

    title = str(market.get("title") or "").strip()
    subtitle = str(market.get("yes_sub_title") or "").strip()
    haystack = title + " " + subtitle
    asset = "BTC" if re.search(r"bitcoin|btc", haystack, re.IGNORECASE) else ""
    match = re.search(r"\$[\d,.]+\s*[kKmM]?", haystack)
    target = match.group(0).replace(" ", "") if match else ""
    normalized_target = target.replace(",", "")
    target_in_subtitle = bool(target) and normalized_target in subtitle.replace(" ", "").replace(",", "")
    parts = [part for part in (asset, "" if target_in_subtitle else target) if part]
    label = " ".join(parts).strip()
    if subtitle:
        return "%s · %s" % (label, subtitle) if label else subtitle
    return label or title


def format_market_line(
    prices: Dict[str, Dict[str, Any]],
    coins: Sequence[str] = DEFAULT_COINS,
    extra: str = "",
) -> str:
    parts: List[str] = []
    for coin in coins:
        data = prices.get(coin) or {}
        try:
            price = float(data.get("usd"))
        except (TypeError, ValueError):
            continue
        change = data.get("usd_24h_change")
        try:
            change_value = float(change) if change is not None else None
        except (TypeError, ValueError):
            change_value = None
        label = COIN_LABELS.get(coin, str(coin)[:4].upper())
        parts.append("%s %s%s" % (label, format_usd(price), format_change(change_value)))
    if extra:
        parts.append(extra)
    return "📈 " + " · ".join(parts) if parts else ""


def insert_before_hashtags(text: str, line: str) -> str:
    """Insert the market line before the trailing hashtag block (or at the end)."""
    if not line:
        return text
    lines = str(text or "").rstrip().split("\n")
    index = len(lines)
    while index > 0:
        candidate = lines[index - 1].strip()
        if not candidate:
            index -= 1
            continue
        words = candidate.split()
        if candidate.startswith("#") and len(words) <= 12:
            index -= 1
            continue
        break
    if index < len(lines):
        head = "\n".join(lines[:index]).rstrip()
        tail = "\n".join(lines[index:]).strip("\n")
        return ("%s\n\n%s\n\n%s" % (head, line, tail)).strip()
    body = str(text or "").rstrip()
    return (body + "\n\n" + line).strip() if body else line


def build_market_line(
    config: Dict[str, Any],
    ttl: int = CACHE_TTL_SEC,
    price_fetcher: Optional[Callable[[str], Dict[str, Any]]] = None,
    markets_fetcher: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
    cache_path: Optional[Path] = None,
) -> str:
    """Build the line from a channel ``market_line`` config block."""
    if not isinstance(config, dict) or not config.get("enabled"):
        return ""
    coins = tuple(str(c).strip() for c in (config.get("coins") or DEFAULT_COINS) if str(c).strip())
    raw_series = config.get("kalshi_series") or ""
    if isinstance(raw_series, str):
        series_list = [raw_series.strip()] if raw_series.strip() else []
    else:
        series_list = [str(item).strip() for item in raw_series if str(item).strip()]
    series = ",".join(series_list)
    path = cache_path or _cache_path()
    cache = _read_cache(path, ttl)
    key = "|".join(coins) + "|" + series
    if cache.get("key") == key and cache.get("line"):
        return str(cache["line"])

    prices: Dict[str, Dict[str, Any]] = {}
    try:
        prices = fetch_crypto_prices(coins, fetcher=price_fetcher)
    except Exception:  # noqa: BLE001 - best effort
        prices = {}
    extra = kalshi_btc_line(series_list, markets_fetcher=markets_fetcher) if series_list else ""
    line = format_market_line(prices, coins=coins, extra=extra)
    if line:
        _write_cache(path, {"key": key, "line": line, "ts": int(time.time())})
    return line
