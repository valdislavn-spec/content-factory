#!/usr/bin/env python3
"""SoSoValue daily digest: spot BTC/ETH ETF flows + top crypto sectors.

Runs in two places without changes:

1. Dify Code (Python) node - paste this file, inputs arrive as the args dict:
       {"api_key": "...", "symbols": ["BTC", "ETH"], "country_code": "US",
        "top_sectors": 3}
   The node calls main(args) and receives one flat dict.
2. Import from tg_autopost.py (same directory) - build_digest(...).

Docs: https://sosovalue.com/ru/developer/docs
Auth: x-soso-api-key. v1 envelope: {code, message, data, details}.
"""
import json
import os
import time
from datetime import datetime, timedelta, timezone

try:  # Dify sandbox and normal servers both ship requests
    import requests
except ImportError:  # pragma: no cover - fallback keeps the node runnable
    requests = None
    import urllib.error
    import urllib.parse
    import urllib.request

BASE_URL = "https://openapi.sosovalue.com/openapi/v1"
TIMEOUT = 20
MAX_RETRIES = 3

SECTOR_NAMES = {
    "defi": "DeFi", "ai": "AI", "rwa": "RWA", "cefi": "CeFi",
    "layer1": "Layer 1", "mag7": "MAG7", "socialfi": "SocialFi",
    "depin": "DePIN", "meme": "Meme", "payfi": "PayFi",
    "layer2": "Layer 2", "gamefi": "GameFi", "nft": "NFT",
}


class SosoError(RuntimeError):
    def __init__(self, message, status=None, code=None):
        super().__init__(message)
        self.status = status
        self.code = code


def _sleep_seconds(headers, attempt):
    retry_after = (headers or {}).get("retry-after") or (headers or {}).get("Retry-After")
    try:
        if retry_after is not None:
            return max(0.0, float(retry_after))
    except (TypeError, ValueError):
        pass
    return min(2 ** attempt, 8)


def _get(path, params, api_key):
    """GET with retry on 429/503/504. Never retries 4xx or 500001 (per docs)."""
    if not api_key:
        raise SosoError("SOSO_API_KEY is not set", code=400101)
    url = BASE_URL + path
    last = None
    for attempt in range(MAX_RETRIES):
        try:
            if requests is not None:
                resp = requests.get(
                    url, params=params,
                    headers={"x-soso-api-key": api_key, "accept": "application/json"},
                    timeout=TIMEOUT,
                    verify=os.environ.get("SOSO_CA_BUNDLE") or True,
                )
                status = resp.status_code
                headers = {k.lower(): v for k, v in resp.headers.items()}
                try:
                    body = resp.json()
                except ValueError:
                    body = None
            else:
                query = ("?" + urllib.parse.urlencode(params)) if params else ""
                req = urllib.request.Request(
                    url + query,
                    headers={"x-soso-api-key": api_key, "accept": "application/json"},
                )
                try:
                    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                        status, headers = r.status, {k.lower(): v for k, v in r.headers.items()}
                        body = json.loads(r.read().decode("utf-8"))
                except urllib.error.HTTPError as exc:
                    status = exc.code
                    headers = {k.lower(): v for k, v in exc.headers.items()}
                    try:
                        body = json.loads(exc.read().decode("utf-8"))
                    except ValueError:
                        body = None
        except Exception as exc:  # network/timeout
            last = SosoError("network error: %s" % exc)
            if attempt == MAX_RETRIES - 1:
                raise last
            time.sleep(min(2 ** attempt, 8))
            continue

        if status == 200 and body and body.get("code") == 0:
            return body.get("data")
        code = (body or {}).get("code")
        message = (body or {}).get("message") or "HTTP %s" % status
        last = SosoError("%s (HTTP %s, code %s)" % (message, status, code), status, code)
        if status not in (429, 503, 504) or attempt == MAX_RETRIES - 1:
            raise last
        time.sleep(_sleep_seconds(headers, attempt))
    raise last


def _num(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def etf_block(symbol, country_code, api_key, days=7):
    """7-day net inflow, latest day inflow and AUM for one ETF symbol."""
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days + 10)  # buffer for T+1 gaps
    rows = _get(
        "/etfs/summary-history",
        {"symbol": symbol, "country_code": country_code,
         "start_date": start.isoformat(), "end_date": end.isoformat()},
        api_key,
    ) or []
    # Newest first; the newest row is T+1 and carries null flow fields.
    with_flow = [r for r in rows if _num(r.get("total_net_inflow")) is not None]
    window = with_flow[:days]
    net_7d = sum(_num(r.get("total_net_inflow"), 0.0) for r in window)
    aum = None
    for r in rows:
        aum = _num(r.get("total_net_assets"))
        if aum is not None:
            break
    cum = _num((with_flow[0] if with_flow else {}).get("cum_net_inflow"))
    streak = 0
    if window:
        sign = 1 if _num(window[0].get("total_net_inflow"), 0.0) >= 0 else -1
        for r in window:
            value = _num(r.get("total_net_inflow"), 0.0)
            if (value >= 0 and sign > 0) or (value < 0 and sign < 0):
                streak += sign
            else:
                break
    return {
        "symbol": symbol,
        "net_7d_usd": round(net_7d, 2),
        "net_1d_usd": round(_num(window[0].get("total_net_inflow"), 0.0), 2) if window else None,
        "aum_usd": round(aum, 2) if aum is not None else None,
        "cum_net_inflow_usd": round(cum, 2) if cum is not None else None,
        "streak_days": streak,
        "days_counted": len(window),
        "last_flow_date": window[0].get("date") if window else None,
        "latest_row_date": rows[0].get("date") if rows else None,
    }


def sector_block(api_key, top_n=3):
    """Top sectors ranked by 7-day ROI from the SSI index snapshots."""
    tickers = _get("/indices", None, api_key) or []
    rows = []
    for ticker in tickers:
        snap = _get("/indices/%s/market-snapshot" % ticker, None, api_key) or {}
        key = str(ticker).lower().replace("ssi", "")
        rows.append({
            "ticker": ticker,
            "name": SECTOR_NAMES.get(key, ticker),
            "roi_7d": _num(snap.get("roi_7d")),
            "roi_24h": _num(snap.get("change_pct_24h")),
            "roi_1m": _num(snap.get("roi_1m")),
            "price": _num(snap.get("price")),
        })
    rows = [r for r in rows if r["roi_7d"] is not None]
    rows.sort(key=lambda r: r["roi_7d"], reverse=True)
    return rows[:top_n], len(rows)


def _fetch_json(url, headers=None, retries=3):
    """Plain GET->JSON with the same retry policy, used for non-SoSoValue hosts."""
    last = None
    for attempt in range(retries):
        try:
            if requests is not None:
                resp = requests.get(url, headers=headers, timeout=TIMEOUT,
                                    verify=os.environ.get("SOSO_CA_BUNDLE") or True)
                if resp.status_code == 200:
                    return resp.json()
                last = SosoError("HTTP %s from %s" % (resp.status_code, url), resp.status_code)
                if resp.status_code not in (429, 503, 504):
                    raise last
            else:
                req = urllib.request.Request(url, headers=headers or {})
                with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                    return json.loads(r.read().decode("utf-8"))
        except SosoError:
            raise
        except Exception as exc:
            last = SosoError("network error: %s" % exc)
        time.sleep(min(2 ** attempt, 8))
    raise last


def sentiment_block(api_key):
    """Fear & Greed index plus the hottest sectors (social volume is not in the API)."""
    fgi_rows = _get("/analyses/fgi_indicator", {"limit": 8}, api_key) or []
    index = _num((fgi_rows[0] if fgi_rows else {}).get("crypto_fear_&_greed_index"))
    week_ago = _num((fgi_rows[7] if len(fgi_rows) > 7 else {}).get("crypto_fear_&_greed_index"))
    label = None
    if index is not None:
        if index < 25:
            label = "Extreme Fear"
        elif index < 45:
            label = "Fear"
        elif index <= 55:
            label = "Neutral"
        elif index <= 74:
            label = "Greed"
        else:
            label = "Extreme Greed"

    spotlight = _get("/currencies/sector-spotlight", None, api_key) or {}
    sectors = sorted(spotlight.get("sector") or [], key=lambda s: s.get("change_pct_24h") or -9, reverse=True)
    out = {
        "fear_greed_index": int(index) if index is not None else None,
        "fear_greed_label": label,
        "fear_greed_7d_ago": int(week_ago) if week_ago is not None else None,
        "fear_greed_change_7d": (int(index) - int(week_ago)) if (index is not None and week_ago is not None) else None,
    }
    for i, row in enumerate(sectors[:3], start=1):
        out["hot_sector_%d_name" % i] = row.get("name")
        out["hot_sector_%d_change_24h_pct" % i] = _pct(_num(row.get("change_pct_24h")))
        out["hot_sector_%d_dominance_pct" % i] = _pct(_num(row.get("marketcap_dom")))
    return out


def derivatives_block(api_key):
    """Funding rates, open interest and long/short ratio. Liquidation totals are not exposed."""
    funding = _get("/analyses/funding_rate", {"limit": 8}, api_key) or []
    latest = funding[0] if funding else {}
    avg7 = None
    values = [_num(r.get("binance")) for r in funding[:7]]
    values = [v for v in values if v is not None]
    if values:
        avg7 = sum(values) / len(values)

    oi = _get("/analyses/futures_open_interest", {"limit": 8}, api_key) or []
    oi_now = _num((oi[0] if oi else {}).get("all"))
    oi_then = _num((oi[-1] if len(oi) > 1 else {}).get("all"))
    oi_change = ((oi_now / oi_then) - 1) * 100 if (oi_now and oi_then) else None

    ls = _get("/analyses/binance_btcusdt_futures_long_short_ratio_1d", {"limit": 1}, api_key) or []
    ratio = _num((ls[0] if ls else {}).get("long/short_ratio"))

    return {
        "funding_binance_pct": round(_num(latest.get("binance")), 5) if latest else None,
        "funding_okx_pct": round(_num(latest.get("okx")), 5) if latest else None,
        "funding_bybit_pct": round(_num(latest.get("bybit")), 5) if latest else None,
        "funding_avg_7d_pct": round(avg7, 5) if avg7 is not None else None,
        "open_interest_usd": round(oi_now, 2) if oi_now else None,
        "open_interest_change_7d_pct": round(oi_change, 2) if oi_change is not None else None,
        "long_short_ratio": round(ratio, 3) if ratio is not None else None,
        "liquidations_24h_usd": None,  # not exposed by the SoSoValue API
    }


ECOSYSTEM_CHAINS = ("Ethereum", "Solana", "Base", "Sui", "Aptos")


def ecosystem_block(api_key, chains=ECOSYSTEM_CHAINS, source="auto"):
    """Per-chain TVL and 7-day growth.

    The SoSoValue chart /analyses/tvl_of_different_type_of_chain only has
    all/ethereum/layer_2/others and its last point was 2024-11-14, so per-chain
    numbers come from DefiLlama (clearly labelled by tvl_source).
    """
    out = {"tvl_source": None, "tvl_as_of": None, "tvl_sosovalue_as_of": None,
           "tvl_sosovalue_stale": None}
    try:
        rows = _get("/analyses/tvl_of_different_type_of_chain", {"limit": 1}, api_key) or []
        if rows:
            ts = _num(rows[0].get("timestamp"))
            if ts:
                as_of = datetime.fromtimestamp(ts / 1000, timezone.utc).date()
                out["tvl_sosovalue_as_of"] = as_of.isoformat()
                out["tvl_sosovalue_stale"] = (datetime.now(timezone.utc).date() - as_of).days > 3
    except SosoError:
        pass

    if source == "off":
        return out
    try:
        ranked = []
        latest_date = None
        for chain in chains:
            hist = _fetch_json("https://api.llama.fi/v2/historicalChainTvl/%s" % chain)
            if hist:
                day = datetime.fromtimestamp(hist[-1]["date"], timezone.utc).date().isoformat()
                latest_date = max(latest_date or day, day)
            now_tvl = _num(hist[-1].get("tvl")) if hist else None
            week_tvl = _num(hist[-8].get("tvl")) if len(hist) > 7 else None
            change = ((now_tvl / week_tvl) - 1) * 100 if (now_tvl and week_tvl) else None
            key = chain.lower().replace(" ", "_")
            out["tvl_%s_usd" % key] = round(now_tvl, 2) if now_tvl else None
            out["tvl_%s_7d_pct" % key] = round(change, 2) if change is not None else None
            if now_tvl:
                ranked.append((chain, change))
        out["tvl_source"] = "defillama"
        out["tvl_as_of"] = latest_date
        ranked = [r for r in ranked if r[1] is not None]
        if ranked:
            top = max(ranked, key=lambda r: r[1])
            out["tvl_top_growth_name"] = top[0]
            out["tvl_top_growth_7d_pct"] = round(top[1], 2)
    except SosoError:
        out["tvl_source"] = "unavailable"
    return out


def macro_block(api_key):
    """Liquidity/macro snapshot: SOFR, TGCR, ON-RRP, next FOMC, upcoming events."""
    rates = _get("/macro/rates", None, api_key) or []
    by_code = {str(r.get("code", "")).lower(): r for r in rates}

    def rate_value(code):
        row = by_code.get(code) or {}
        return _num(row.get("latest_value")), row.get("latest_date")

    sofr, sofr_date = rate_value("sofr")
    tgcr, _ = rate_value("tgcr")
    on_rrp, rrp_date = rate_value("on-rrp")

    fomc = _get("/macro/fomc-probabilities", None, api_key) or {}
    meetings = fomc.get("meetings") or []
    ranges = fomc.get("rate_ranges") or []
    next_date = top_range = None
    top_prob = None
    if meetings:
        meeting = meetings[0]
        next_date = meeting.get("meeting_date")
        probs = [_num(p, 0.0) or 0.0 for p in (meeting.get("probabilities") or [])]
        if probs:
            idx = probs.index(max(probs))
            top_prob = round(probs[idx], 1)
            top_range = ranges[idx] if idx < len(ranges) else None

    events = _get("/macro/events", None, api_key) or []
    today = datetime.now(timezone.utc).date().isoformat()
    upcoming = next((e for e in events if str(e.get("date", "")) >= today), None)
    event_date = upcoming.get("date") if upcoming else None
    event_names = (upcoming.get("events") or [])[:3] if upcoming else []

    return {
        "sofr_pct": sofr,
        "sofr_date": sofr_date,
        "tgcr_pct": tgcr,
        "on_rrp_usd": on_rrp,
        "on_rrp_date": rrp_date,
        "fomc_next_date": next_date,
        "fomc_top_range": top_range,
        "fomc_top_prob_pct": top_prob,
        "macro_next_date": event_date,
        "macro_next_events": ", ".join(event_names) if event_names else None,
    }


def _pct(value, digits=2):
    if value is None:
        return None
    return round(value * 100.0, digits)


def build_digest(api_key=None, symbols=("BTC", "ETH"), country_code="US", top_sectors=3):
    api_key = api_key or os.environ.get("SOSO_API_KEY", "")
    errors = []
    data = {}
    for symbol in symbols:
        try:
            block = etf_block(symbol.upper(), country_code.upper(), api_key)
        except SosoError as exc:
            errors.append("%s ETF: %s" % (symbol, exc))
            block = {"symbol": symbol.upper(), "net_7d_usd": None, "net_1d_usd": None,
                     "aum_usd": None, "cum_net_inflow_usd": None, "streak_days": 0, "days_counted": 0,
                     "last_flow_date": None, "latest_row_date": None}
        prefix = block["symbol"].lower() + "_etf"
        data[prefix + "_net_7d_usd"] = block["net_7d_usd"]
        data[prefix + "_net_1d_usd"] = block["net_1d_usd"]
        data[prefix + "_aum_usd"] = block["aum_usd"]
        data[prefix + "_cum_net_inflow_usd"] = block["cum_net_inflow_usd"]
        data[prefix + "_streak_days"] = block["streak_days"]
        data[prefix + "_days_counted"] = block["days_counted"]
        data[prefix + "_last_flow_date"] = block["last_flow_date"]
        data[prefix + "_latest_row_date"] = block["latest_row_date"]

    try:
        sectors, total = sector_block(api_key, top_sectors)
    except SosoError as exc:
        errors.append("sectors: %s" % exc)
        sectors, total = [], 0

    try:
        data.update(macro_block(api_key))
    except SosoError as exc:
        errors.append("macro: %s" % exc)
        data.update({"sofr_pct": None, "sofr_date": None, "tgcr_pct": None,
                     "on_rrp_usd": None, "on_rrp_date": None, "fomc_next_date": None,
                     "fomc_top_range": None, "fomc_top_prob_pct": None,
                     "macro_next_date": None, "macro_next_events": None})

    try:
        data.update(sentiment_block(api_key))
    except SosoError as exc:
        errors.append("sentiment: %s" % exc)

    try:
        data.update(derivatives_block(api_key))
    except SosoError as exc:
        errors.append("derivatives: %s" % exc)

    try:
        data.update(ecosystem_block(api_key, source=os.environ.get("TVL_SOURCE", "auto")))
    except SosoError as exc:
        errors.append("ecosystems: %s" % exc)

    data["data_gaps"] = ("social volume/sentiment not exposed by SoSoValue API; "
                         "24h liquidation totals not exposed; per-chain TVL via DefiLlama")

    btc7 = data.get("btc_etf_net_7d_usd")
    eth7 = data.get("eth_etf_net_7d_usd")
    data["etf_net_7d_usd"] = round((btc7 or 0) + (eth7 or 0), 2) if (btc7 is not None or eth7 is not None) else None
    data["sector_count"] = total
    for i in range(top_sectors):
        row = sectors[i] if i < len(sectors) else {}
        n = i + 1
        data["sector_%d_name" % n] = row.get("name")
        data["sector_%d_roi_7d_pct" % n] = _pct(row.get("roi_7d"))
        data["sector_%d_roi_24h_pct" % n] = _pct(row.get("roi_24h"))
        data["sector_%d_roi_1m_pct" % n] = _pct(row.get("roi_1m"))
        data["sector_%d_ticker" % n] = row.get("ticker")

    data["as_of_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data["errors"] = "; ".join(errors) if errors else None
    data["summary_text"] = _summary_text(data)
    return data


def _fmt_usd(value):
    if value is None:
        return "n/a"
    sign = "-" if value < 0 else ""
    v = abs(float(value))
    if v >= 1e9:
        return "%s$%.2fB" % (sign, v / 1e9)
    if v >= 1e6:
        return "%s$%.2fM" % (sign, v / 1e6)
    if v >= 1e3:
        return "%s$%.2fK" % (sign, v / 1e3)
    return "%s$%.0f" % (sign, v)


def _summary_text(d):
    lines = []
    for sym, label in (("btc", "BTC"), ("eth", "ETH")):
        net7 = d.get(sym + "_etf_net_7d_usd")
        net1 = d.get(sym + "_etf_net_1d_usd")
        aum = d.get(sym + "_etf_aum_usd")
        if net7 is None and aum is None:
            continue
        lines.append("%s spot ETF: 7d net %s, last day %s, AUM %s" % (
            label, _fmt_usd(net7), _fmt_usd(net1), _fmt_usd(aum)))
    for i in (1, 2, 3):
        name = d.get("sector_%d_name" % i)
        if not name:
            continue
        lines.append("Sector #%d %s: 7d %+.2f%%, 24h %+.2f%%, 1m %+.2f%%" % (
            i, name, d.get("sector_%d_roi_7d_pct" % i) or 0.0,
            d.get("sector_%d_roi_24h_pct" % i) or 0.0,
            d.get("sector_%d_roi_1m_pct" % i) or 0.0))
    if d.get("fear_greed_index") is not None:
        hot = ", ".join(
            "%s %+.2f%%" % (d.get("hot_sector_%d_name" % i), d.get("hot_sector_%d_change_24h_pct" % i) or 0.0)
            for i in (1, 2, 3) if d.get("hot_sector_%d_name" % i))
        lines.append("Sentiment: FGI %s (%s)%s%s" % (
            d["fear_greed_index"], d.get("fear_greed_label") or "n/a",
            " %+d за 7д" % d["fear_greed_change_7d"] if d.get("fear_greed_change_7d") is not None else "",
            " | " + hot if hot else ""))
    if d.get("funding_binance_pct") is not None:
        lines.append("Derivatives: funding Binance %.4f%%/8h, OI %s (%s%% 7d), L/S %s" % (
            d["funding_binance_pct"], _fmt_usd(d.get("open_interest_usd")),
            ("%+.2f" % d["open_interest_change_7d_pct"]) if d.get("open_interest_change_7d_pct") is not None else "n/a",
            d.get("long_short_ratio") if d.get("long_short_ratio") is not None else "n/a"))
    if d.get("tvl_source") == "defillama" and d.get("tvl_top_growth_name"):
        lines.append("TVL: fastest 7d growth %s %+.2f%%" % (
            d["tvl_top_growth_name"], d.get("tvl_top_growth_7d_pct") or 0.0))
    if d.get("sofr_pct") is not None:
        lines.append("Macro: SOFR %.2f%%, TGCR %.2f%%, ON-RRP %s" % (
            d["sofr_pct"], d.get("tgcr_pct") or 0.0, _fmt_usd(d.get("on_rrp_usd"))))
    if d.get("fomc_next_date"):
        lines.append("FOMC %s: %s at %.1f%%" % (
            d["fomc_next_date"], d.get("fomc_top_range") or "n/a", d.get("fomc_top_prob_pct") or 0.0))
    return " | ".join(lines)


def main(args=None, **kwargs):
    """Dify Code-node entry point.

    Works with either wiring:
      * one Object input variable named "args" -> main(args)
      * separate input variables            -> main(api_key=..., symbols=...)
    """
    merged = dict(kwargs)
    if isinstance(args, dict):
        merged.update(args)
    args = merged
    api_key = args.get("api_key") or args.get("soso_api_key") or os.environ.get("SOSO_API_KEY", "")
    symbols = args.get("symbols") or ["BTC", "ETH"]
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.split(",") if s.strip()]
    country = args.get("country_code") or "US"
    top_n = int(args.get("top_sectors") or 3)
    return build_digest(api_key=api_key, symbols=symbols, country_code=country, top_sectors=top_n)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="BTC,ETH")
    parser.add_argument("--country", default="US")
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--pretty", action="store_true")
    ns = parser.parse_args()
    result = main({"symbols": ns.symbols.split(","), "country_code": ns.country, "top_sectors": ns.top})
    print(json.dumps(result, indent=2 if ns.pretty else None, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Multilingual renderers for the content factory (EN / ES)
# ---------------------------------------------------------------------------

fmt_usd = _fmt_usd


def fmt_pct(value):
    if value is None:
        return "n/a"
    return "%+.2f%%" % float(value)


def fmt_date(value, fmt="%d.%m.%Y"):
    if not value:
        return "n/a"
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime(fmt)
    except ValueError:
        return str(value)

LANG = {
    "en": {
        "flows_title": "Institutional flows",
        "btc": "Bitcoin ETF", "eth": "Ethereum ETF", "d7": "7d", "yday": "yesterday",
        "aum": "AUM", "total7": "Total 7d", "outflow": "{n} outflow days",
        "inflow": "{n} inflow days", "sectors_title": "Sector indices",
        "top3": "Top 3 by 7-day return", "all_idx": "SSI indices",
        "macro_title": "Macro & liquidity", "calendar": "Calendar",
        "sent_title": "Sentiment & social", "fg": "Fear & Greed",
        "hot": "Hot sectors (24h)", "der_title": "Derivatives",
        "funding": "Binance funding", "oi": "Open interest", "ls": "Long/short",
        "liq": "24h liquidations: not published by the SoSoValue API",
        "eco_title": "Ecosystem TVL", "eco7": "7d", "top_growth": "Fastest 7d growth",
        "src": "Source: SoSoValue", "na": "n/a", "date_fmt": "%b %d, %Y",
    },
    "es": {
        "flows_title": "Flujos institucionales",
        "btc": "ETF de Bitcoin", "eth": "ETF de Ethereum", "d7": "7d", "yday": "ayer",
        "aum": "AUM", "total7": "Total 7d", "outflow": "{n} días de salida",
        "inflow": "{n} días de entrada", "sectors_title": "Índices sectoriales",
        "top3": "Top 3 por retorno 7d", "all_idx": "índices SSI",
        "macro_title": "Macro y liquidez", "calendar": "Calendario",
        "sent_title": "Sentimiento y social", "fg": "Miedo y codicia",
        "hot": "Sectores calientes (24h)", "der_title": "Derivados",
        "funding": "Funding Binance", "oi": "Interés abierto", "ls": "Long/short",
        "liq": "Liquidaciones 24h: la API de SoSoValue no las publica",
        "eco_title": "TVL de ecosistemas", "eco7": "7d", "top_growth": "Mayor crecimiento 7d",
        "src": "Fuente: SoSoValue", "na": "n/d", "date_fmt": "%d.%m.%Y",
    },
}


def _lang(lang):
    return LANG.get(str(lang or "en").lower(), LANG["en"])


def _streak(n, t):
    if not n:
        return ""
    return " · " + (t["outflow"].format(n=abs(n)) if n < 0 else t["inflow"].format(n=n))


def _when(value, t):
    if not value:
        return t["na"]
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime(t["date_fmt"])
    except ValueError:
        return str(value)


def render_flows(d, lang="en"):
    t = _lang(lang)
    return "\n".join([
        "<b>%s</b> · %s" % (t["flows_title"], _when(d.get("as_of_utc"), t)),
        "",
        "%s: %s %s%s" % (t["btc"], t["d7"], fmt_usd(d.get("btc_etf_net_7d_usd")),
                         _streak(d.get("btc_etf_streak_days"), t)),
        "  %s %s · %s %s" % (t["yday"], fmt_usd(d.get("btc_etf_net_1d_usd")),
                             t["aum"], fmt_usd(d.get("btc_etf_aum_usd"))),
        "%s: %s %s%s" % (t["eth"], t["d7"], fmt_usd(d.get("eth_etf_net_7d_usd")),
                         _streak(d.get("eth_etf_streak_days"), t)),
        "  %s %s · %s %s" % (t["yday"], fmt_usd(d.get("eth_etf_net_1d_usd")),
                             t["aum"], fmt_usd(d.get("eth_etf_aum_usd"))),
        "",
        "%s: <b>%s</b>" % (t["total7"], fmt_usd(d.get("etf_net_7d_usd"))),
    ])


def render_sectors(d, lang="en"):
    t = _lang(lang)
    lines = ["<b>%s</b> · %s" % (t["sectors_title"], _when(d.get("as_of_utc"), t)), "",
             "%s:" % t["top3"]]
    for i in (1, 2, 3):
        name = d.get("sector_%d_name" % i)
        if not name:
            continue
        lines.append("%d. %s — 7d <b>%s</b> · 24h %s · 1m %s" % (
            i, name, fmt_pct(d.get("sector_%d_roi_7d_pct" % i)),
            fmt_pct(d.get("sector_%d_roi_24h_pct" % i)),
            fmt_pct(d.get("sector_%d_roi_1m_pct" % i))))
    if d.get("sector_count"):
        lines += ["", "%s: %d" % (t["all_idx"], d["sector_count"])]
    return "\n".join(lines)


def render_macro(d, lang="en"):
    t = _lang(lang)
    lines = ["<b>%s</b> · %s" % (t["macro_title"], _when(d.get("as_of_utc"), t)), ""]
    if d.get("sofr_pct") is not None:
        lines.append("SOFR %.2f%% · TGCR %.2f%%" % (d["sofr_pct"], d.get("tgcr_pct") or 0.0))
    if d.get("on_rrp_usd") is not None:
        lines.append("ON-RRP %s (%s)" % (fmt_usd(d["on_rrp_usd"]), _when(d.get("on_rrp_date"), t)))
    if d.get("fomc_next_date"):
        lines.append("%s %s: %s bp — <b>%.1f%%</b>" % (
            "FOMC", _when(d["fomc_next_date"], t), d.get("fomc_top_range") or t["na"],
            d.get("fomc_top_prob_pct") or 0.0))
    if d.get("macro_next_events"):
        lines.append("%s %s: %s" % (t["calendar"], _when(d.get("macro_next_date"), t),
                                    d["macro_next_events"]))
    return "\n".join(lines)


def render_sentiment(d, lang="en"):
    t = _lang(lang)
    lines = ["<b>%s</b> · %s" % (t["sent_title"], _when(d.get("as_of_utc"), t)), ""]
    if d.get("fear_greed_index") is not None:
        change = d.get("fear_greed_change_7d")
        lines.append("%s: <b>%s</b> (%s)%s" % (
            t["fg"], d["fear_greed_index"], d.get("fear_greed_label") or t["na"],
            " %+d %s" % (change, "7d") if change is not None else ""))
    hot = []
    for i in (1, 2, 3):
        name = d.get("hot_sector_%d_name" % i)
        if name:
            hot.append("%s %s" % (name, fmt_pct(d.get("hot_sector_%d_change_24h_pct" % i))))
    if hot:
        lines += ["", "%s: %s" % (t["hot"], " · ".join(hot))]
    return "\n".join(lines)


def render_derivatives(d, lang="en"):
    t = _lang(lang)
    lines = ["<b>%s</b> · %s" % (t["der_title"], _when(d.get("as_of_utc"), t)), ""]
    if d.get("funding_binance_pct") is not None:
        lines.append("%s: <b>%.4f%%</b>/8h · avg 7d %.4f%%" % (
            t["funding"], d["funding_binance_pct"], d.get("funding_avg_7d_pct") or 0.0))
    if d.get("open_interest_usd") is not None:
        lines.append("%s: %s (%s %s)" % (
            t["oi"], fmt_usd(d["open_interest_usd"]),
            fmt_pct(d.get("open_interest_change_7d_pct")), t["d7"]))
    if d.get("long_short_ratio") is not None:
        lines.append("%s: <b>%.3f</b>" % (t["ls"], d["long_short_ratio"]))
    lines += ["", "<i>%s</i>" % t["liq"]]
    return "\n".join(lines)


ECOSYSTEM_KEYS = ("ethereum", "solana", "base", "sui", "aptos")


def render_ecosystems(d, lang="en"):
    t = _lang(lang)
    lines = ["<b>%s</b> · %s" % (t["eco_title"], _when(d.get("tvl_as_of"), t)), ""]
    rows = []
    for key in ECOSYSTEM_KEYS:
        tvl = d.get("tvl_%s_usd" % key)
        if tvl is None:
            continue
        name = key.capitalize() if key != "base" else "Base"
        rows.append((name, tvl, d.get("tvl_%s_7d_pct" % key)))
    rows.sort(key=lambda r: r[1], reverse=True)
    for name, tvl, change in rows:
        lines.append("%s: <b>%s</b> · %s %s" % (name, fmt_usd(tvl), t["eco7"], fmt_pct(change)))
    if d.get("tvl_top_growth_name"):
        lines += ["", "%s: <b>%s %s</b>" % (t["top_growth"], d["tvl_top_growth_name"],
                                            fmt_pct(d.get("tvl_top_growth_7d_pct")))]
    return "\n".join(lines)


RENDERERS = {
    "flows": render_flows,
    "sectors": render_sectors,
    "macro": render_macro,
    "sentiment": render_sentiment,
    "derivatives": render_derivatives,
    "ecosystems": render_ecosystems,
}


def render(theme, digest, lang="en", footer="", affiliate=""):
    renderer = RENDERERS.get(theme)
    if renderer is None:
        raise ValueError("unknown theme: %s" % theme)
    text = renderer(digest, lang)
    tail = []
    if affiliate:
        tail.append(affiliate)
    if footer:
        tail.append("<i>%s</i>" % footer)
    if tail:
        text = text + "\n\n" + "\n".join(tail)
    return text[:4000]



SUMMARY_LABELS = {
    "en": {
        "title": "Crypto daily", "flows": "ETF flows", "sectors": "Sectors",
        "macro": "Macro", "sentiment": "Sentiment", "derivatives": "Derivatives",
        "tvl": "TVL", "fgi": "F&G", "hot": "hot", "funding": "funding",
        "oi": "OI", "ls": "L/S", "fomc": "FOMC", "rrp": "ON-RRP",
    },
    "es": {
        "title": "Cripto diario", "flows": "Flujos ETF", "sectors": "Sectores",
        "macro": "Macro", "sentiment": "Sentimiento", "derivatives": "Derivados",
        "tvl": "TVL", "fgi": "M&G", "hot": "calientes", "funding": "funding",
        "oi": "IA", "ls": "L/S", "fomc": "FOMC", "rrp": "ON-RRP",
    },
}


FGI_ES = {"Extreme Fear": "Miedo extremo", "Fear": "Miedo", "Neutral": "Neutral",
          "Greed": "Codicia", "Extreme Greed": "Codicia extrema"}


def render_summary(d, lang="en", footer="", affiliate=""):
    """One compact post: every theme as a single line (fits 1200 chars)."""
    t = _lang(lang)
    lab = SUMMARY_LABELS.get(lang, SUMMARY_LABELS["en"])
    lines = ["<b>%s</b> · %s" % (lab["title"], _when(d.get("as_of_utc"), t)), ""]

    if d.get("btc_etf_net_7d_usd") is not None:
        lines.append("• %s: BTC %s%s, ETH %s; AUM %s / %s" % (
            lab["flows"], fmt_usd(d.get("btc_etf_net_7d_usd")),
            _streak(d.get("btc_etf_streak_days"), t),
            fmt_usd(d.get("eth_etf_net_7d_usd")),
            fmt_usd(d.get("btc_etf_aum_usd")), fmt_usd(d.get("eth_etf_aum_usd"))))

    sectors = []
    for i in (1, 2, 3):
        name = d.get("sector_%d_name" % i)
        if name:
            sectors.append("%s %s" % (name, fmt_pct(d.get("sector_%d_roi_7d_pct" % i))))
    if sectors:
        lines.append("• %s: %s" % (lab["sectors"], " · ".join(sectors)))

    macro = []
    if d.get("sofr_pct") is not None:
        macro.append("SOFR %.2f%%" % d["sofr_pct"])
    if d.get("on_rrp_usd") is not None:
        macro.append("%s %s" % (lab["rrp"], fmt_usd(d["on_rrp_usd"])))
    if d.get("fomc_next_date"):
        macro.append("%s %s %s %.0f%%" % (lab["fomc"], _when(d["fomc_next_date"], t),
                                          d.get("fomc_top_range") or "", d.get("fomc_top_prob_pct") or 0.0))
    if macro:
        lines.append("• %s: %s" % (lab["macro"], " · ".join(macro)))

    if d.get("fear_greed_index") is not None:
        hot = []
        for i in (1, 2, 3):
            name = d.get("hot_sector_%d_name" % i)
            if name:
                hot.append("%s %s" % (name, fmt_pct(d.get("hot_sector_%d_change_24h_pct" % i))))
        fgi_label = d.get("fear_greed_label") or t["na"]
        if lang == "es":
            fgi_label = FGI_ES.get(fgi_label, fgi_label)
        lines.append("• %s: %s %s (%s)%s" % (
            lab["sentiment"], lab["fgi"], d["fear_greed_index"], fgi_label,
            " · " + lab["hot"] + " " + ", ".join(hot) if hot else ""))

    deriv = []
    if d.get("funding_binance_pct") is not None:
        deriv.append("%s %.4f%%/8h" % (lab["funding"], d["funding_binance_pct"]))
    if d.get("open_interest_usd") is not None:
        deriv.append("%s %s (%s 7d)" % (lab["oi"], fmt_usd(d["open_interest_usd"]),
                                        fmt_pct(d.get("open_interest_change_7d_pct"))))
    if d.get("long_short_ratio") is not None:
        deriv.append("%s %.2f" % (lab["ls"], d["long_short_ratio"]))
    if deriv:
        lines.append("• %s: %s" % (lab["derivatives"], " · ".join(deriv)))

    tvl = []
    for key in ("ethereum", "solana", "sui"):
        if d.get("tvl_%s_usd" % key) is not None:
            tvl.append("%s %s (%s)" % (key.capitalize(), fmt_usd(d["tvl_%s_usd" % key]),
                                       fmt_pct(d.get("tvl_%s_7d_pct" % key))))
    if d.get("tvl_top_growth_name"):
        tvl.append("leader %s %s" % (d["tvl_top_growth_name"], fmt_pct(d.get("tvl_top_growth_7d_pct"))))
    if tvl:
        lines.append("• %s: %s" % (lab["tvl"], " · ".join(tvl)))

    text = "\n".join(lines)
    tail = [part for part in (affiliate, ("<i>%s</i>" % footer) if footer else "") if part]
    if tail:
        text += "\n\n" + "\n".join(tail)
    return text[:4000]

