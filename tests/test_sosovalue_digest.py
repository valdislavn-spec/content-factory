"""Renderers and theme selection for the SoSoValue digest (no network)."""
import sys
from pathlib import Path

CF = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CF))
sys.path.insert(0, str(CF / "scripts"))

import sosovalue_digest as cli  # noqa: E402
from content_factory.sosovalue import render, RENDERERS  # noqa: E402

DIGEST = {
    "as_of_utc": "2026-11-28T14:58:24Z",
    "btc_etf_net_7d_usd": -3201224345.26, "btc_etf_net_1d_usd": -389031583.77,
    "btc_etf_aum_usd": 71338635414.82, "btc_etf_streak_days": -7,
    "eth_etf_net_7d_usd": -555222699.13, "eth_etf_net_1d_usd": -69271003.28,
    "eth_etf_aum_usd": 8701595218.22, "eth_etf_streak_days": -7,
    "etf_net_7d_usd": -3756447044.39, "sector_count": 13,
    "sector_1_name": "AI", "sector_1_roi_7d_pct": 0.86,
    "sector_1_roi_24h_pct": -0.02, "sector_1_roi_1m_pct": -20.45,
    "sofr_pct": 3.95, "tgcr_pct": 3.93, "on_rrp_usd": 3e8,
    "on_rrp_date": "2026-11-25", "fomc_next_date": "2026-12-09",
    "fomc_top_range": "400-425", "fomc_top_prob_pct": 98.4,
    "macro_next_date": "2026-11-30", "macro_next_events": "PMI, JOLTs",
    "fear_greed_index": 10, "fear_greed_label": "Extreme Fear",
    "fear_greed_change_7d": -2, "hot_sector_1_name": "RWA",
    "hot_sector_1_change_24h_pct": 4.5,
    "funding_binance_pct": 0.00707, "funding_avg_7d_pct": 0.00637,
    "open_interest_usd": 40138362198.0, "open_interest_change_7d_pct": -1.75,
    "long_short_ratio": 3.002, "liquidations_24h_usd": None,
    "tvl_source": "defillama", "tvl_as_of": "2026-11-28",
    "tvl_ethereum_usd": 36.09e9, "tvl_ethereum_7d_pct": 4.06,
    "tvl_solana_usd": 4.55e9, "tvl_solana_7d_pct": 0.07,
    "tvl_sui_usd": 404.29e6, "tvl_sui_7d_pct": 21.63,
    "tvl_top_growth_name": "Sui", "tvl_top_growth_7d_pct": 21.63,
}


def test_every_theme_renders_in_both_languages():
    for theme in RENDERERS:
        for lang in ("en", "es"):
            text = render(theme, DIGEST, lang=lang)
            assert text and len(text) <= 4000
            assert "<b>" in text
            assert "None" not in text


def test_flows_numbers_and_streak():
    text = render("flows", DIGEST, lang="en")
    assert "-$3.20B" in text and "$71.34B" in text
    assert "7 outflow days" in text


def test_ecosystems_sorted_by_tvl_and_top_growth():
    text = render("ecosystems", DIGEST, lang="es")
    assert text.index("Ethereum") < text.index("Sui")
    assert "Sui +21.63%" in text


def test_unknown_theme_raises():
    try:
        render("nope", DIGEST)
    except ValueError as exc:
        assert "nope" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_select_themes_by_hour_and_explicit():
    config = {"themes": [
        {"key": "flows", "hour_utc": 7, "channels": ["crypto-news"]},
        {"key": "sectors", "hour_utc": 9, "channels": ["crypto-news"]},
    ]}

    class Args:
        theme = "flows"
        all = False

    assert [t["key"] for t in cli.select_themes(config, Args)] == ["flows"]

    class AllArgs:
        theme = ""
        all = True

    assert len(cli.select_themes(config, AllArgs)) == 2


def test_summary_is_one_compact_post():
    from content_factory.sosovalue import render_summary
    for lang in ("en", "es"):
        text = render_summary(DIGEST, lang=lang, footer="src")
        assert len(text) <= 1200, (lang, len(text))
        assert text.count("•") == 6, text
        assert "10" in text and "Sui" in text

