#!/usr/bin/env python3
"""Гео-лендинги каналов (бесплатная реклама/SEO) под GitHub Pages.

Генерирует по одной странице на канал с гео-ориентацией:
- EN-каналы  → США (аудитория US, время ET, американские источники);
- ES-каналы  → ЛатАм + Испания (México/Argentina/Colombia/Chile/España).

Страницы кладутся в `docs/channels/` (GitHub Pages отдаёт каталог `docs/`),
индекс — `docs/channels/index.html`, sitemap обновляется по `--sitemap`.

    ./.venv/bin/python scripts/build_geo_landing.py \
        --base-url https://valdislavn-spec.github.io/content-factory

Дальше: `git push`, дождаться сборки Pages и пинговать IndexNow
(`scripts/indexnow_ping.py` или прямой POST на api.indexnow.org).
"""
from __future__ import annotations

import argparse
import html
import sys
import urllib.parse
from datetime import date
from pathlib import Path
from typing import Dict, List

import yaml

ROOT = Path(__file__).resolve().parents[1]

# Каналы и их гео-позиционирование. Ключ — id канала в config/channels.*.yaml.
GEO: Dict[str, Dict[str, str]] = {
    "crypto-news": {
        "lang": "en",
        "region": "US",
        "place": "United States",
        "slug": "us-crypto-news-telegram",
        "title": "US Crypto News on Telegram — Bitcoin, Ethereum & Regulation",
        "h1": "US crypto news — Bitcoin, Ethereum and regulation",
        "lead": (
            "Bitcoin, Ethereum, ETF flows, SEC/CFTC regulation and market moves — "
            "a daily Telegram digest for US crypto readers. Sourced from CoinDesk, "
            "The Block, Decrypt, SEC and CFTC. No hype, no paid promotion."
        ),
        "inside": [
            "3–6 posts a day, 07:00–21:00 ET (US market hours)",
            "Market-moving headlines with links to the primary source",
            "US regulation: SEC, CFTC, ETF filings and enforcement",
            "Free channel — no ads, no paid signals",
        ],
        "for_whom": "US crypto holders, traders and builders who want the news without noise.",
        "sources": "CoinDesk · The Block · Decrypt · SEC · CFTC",
    },
    "ai-news": {
        "lang": "en",
        "region": "US",
        "place": "United States",
        "slug": "ai-news-telegram-us",
        "title": "AI News for US Readers — Telegram Channel",
        "h1": "AI news, models and policy — in Telegram",
        "lead": (
            "Model releases, products, funding rounds and US AI policy — a daily "
            "Telegram channel for people who follow AI. Sourced from TechCrunch, "
            "The Verge, MIT Technology Review, Wired, OpenAI, NVIDIA and Hugging Face."
        ),
        "inside": [
            "Daily AI headlines for a US audience",
            "Model releases, benchmarks and product launches",
            "US AI policy, chips and regulation",
            "Free channel — no ads, no sponsored posts",
        ],
        "for_whom": "Engineers, founders and analysts tracking AI in the US.",
        "sources": "TechCrunch · The Verge · MIT Technology Review · Wired · OpenAI · NVIDIA · Hugging Face",
    },
    "sport-news": {
        "lang": "en",
        "region": "US",
        "place": "United States",
        "slug": "us-sports-news-telegram",
        "title": "US Sports News on Telegram — NFL, NBA, MLB, NHL",
        "h1": "US sports headlines — NFL, NBA, MLB, NHL",
        "lead": (
            "Scores, trades, injuries and analysis across NFL, NBA, MLB, NHL and "
            "college football. Written for US fans; sourced from ESPN, CBS Sports, "
            "Sporting News, ProFootballTalk and MLB.com."
        ),
        "inside": [
            "Scores and results in US time zones",
            "Trades, injuries and roster moves",
            "NFL, NBA, MLB, NHL and college football",
            "Free channel — no ads",
        ],
        "for_whom": "US sports fans who want a fast, sourced daily rundown.",
        "sources": "ESPN · CBS Sports · Sporting News · ProFootballTalk · MLB.com",
    },
    "crypto-es": {
        "lang": "es",
        "region": "MX",
        "place": "México, Argentina, Colombia, Chile, España",
        "slug": "noticias-cripto-telegram",
        "title": "Noticias de Cripto en Español — Telegram",
        "h1": "Cripto y blockchain en español — Telegram",
        "lead": (
            "Bitcoin, Ethereum, mercados y regulación en español. Resúmenes diarios "
            "para México, Argentina, Colombia, Chile y España; fuentes: CriptoNoticias, "
            "BeInCrypto ES, CriptoTendencia y Observatorio Blockchain."
        ),
        "inside": [
            "6 publicaciones al día, horario de LatAm (UTC−5)",
            "Bitcoin, Ethereum, ETF y mercados",
            "Regulación en LatAm y España",
            "Canal gratuito — sin publicidad ni señales pagadas",
        ],
        "for_whom": "Lectores de México, Argentina, Colombia, Chile y España que siguen cripto en español.",
        "sources": "CriptoNoticias · BeInCrypto ES · CriptoTendencia · Observatorio Blockchain",
    },
    "tech-ai-es": {
        "lang": "es",
        "region": "MX",
        "place": "México, Argentina, Colombia, Chile, España",
        "slug": "noticias-ia-telegram",
        "title": "Noticias de IA en Español — Telegram",
        "h1": "Inteligencia artificial en español — Telegram",
        "lead": (
            "Modelos, productos, empresas y políticas de IA en español. Resúmenes "
            "diarios para LatAm y España; fuentes: Hipertextual, FayerWayer, ABC "
            "Tecnología, La Nación y El Financiero."
        ),
        "inside": [
            "Noticias de IA todos los días para LatAm y España",
            "Nuevos modelos, herramientas y lanzamientos",
            "Empresas, inversión y regulación de IA",
            "Canal gratuito — sin publicidad",
        ],
        "for_whom": "Profesionales y curiosos de LatAm y España que siguen la IA en español.",
        "sources": "Hipertextual · FayerWayer · ABC Tecnología · La Nación · El Financiero",
    },
    "futbol-es": {
        "lang": "es",
        "region": "MX",
        "place": "México, Argentina, Colombia, Chile, España",
        "slug": "futbol-deportes-telegram",
        "title": "Fútbol y Deportes en Español — Telegram",
        "h1": "Fútbol y deporte en español — Telegram",
        "lead": (
            "LaLiga, Liga MX, Argentina, MLS y Champions: resultados, fichajes y "
            "análisis en español. Fuentes: ESPN (es), Relevo, 90min y La Nación "
            "Deportes. Material para mayores de 18 años."
        ),
        "inside": [
            "Resultados y fichajes de LatAm y España",
            "LaLiga, Liga MX, Argentina, MLS y Champions",
            "Análisis y datos para aficionados",
            "Gratis — sin publicidad (contenido 18+)",
        ],
        "for_whom": "Aficionados al fútbol de México, Argentina, Colombia, Chile y España.",
        "sources": "ESPN (es) · Relevo · 90min · La Nación Deportes",
    },
}

_TEMPLATE = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:url" content="{canonical}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:locale" content="{og_locale}">
<meta name="twitter:card" content="summary">
<meta name="geo.region" content="{region}">
<meta name="geo.placename" content="{place}">
<link rel="alternate" hreflang="{lang}" href="{canonical}">
<link rel="alternate" hreflang="x-default" href="{hub}">
<script type="application/ld+json">
{jsonld}
</script>
<style>
:root{{color-scheme:light dark;--bg:#f6f7fb;--card:#fff;--text:#18202c;--muted:#5a6572;--accent:#2b6cb0;}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f141b;--card:#18202b;--text:#e8edf5;--muted:#9aa7b8;--accent:#7fb3e8;}}}}
*{{box-sizing:border-box}}body{{margin:0;font:16px/1.6 -apple-system,"Segoe UI",Roboto,Arial,sans-serif;background:var(--bg);color:var(--text)}}
.wrap{{max-width:720px;margin:0 auto;padding:48px 16px}}.card{{background:var(--card);border-radius:16px;padding:32px;box-shadow:0 6px 28px rgba(15,25,40,.08)}}
h1{{margin:0 0 8px;font-size:30px}}h2{{font-size:19px;margin:28px 0 8px}}.lead{{color:var(--muted);font-size:18px}}
ul{{padding-left:20px}}li{{margin:6px 0}}.muted{{color:var(--muted);font-size:14px}}
.cta{{display:inline-block;margin:22px 12px 6px 0;padding:14px 26px;border-radius:12px;background:var(--accent);color:#fff;text-decoration:none;font-weight:700}}
.secondary{{display:inline-block;margin:22px 0 6px;padding:14px 20px;border-radius:12px;border:1px solid var(--accent);color:var(--accent);text-decoration:none;font-weight:600}}
.share{{margin-top:26px;padding-top:18px;border-top:1px solid rgba(120,140,170,.25);font-size:14px;color:var(--muted)}}
.share a{{color:var(--accent);text-decoration:none;margin-right:14px}}footer{{color:var(--muted);font-size:13px;margin-top:26px}}
</style>
</head>
<body>
<div class="wrap"><div class="card">
<p class="muted">{badge}</p>
<h1>{h1}</h1>
<p class="lead">{lead}</p>
<a class="cta" href="{tg}">{cta_label}</a><a class="secondary" href="{hub}">{all_label}</a>
<h2>{inside_title}</h2>
<ul>{inside}</ul>
<h2>{who_title}</h2>
<p>{for_whom}</p>
<h2>{sources_title}</h2>
<p class="muted">{sources}</p>
<div class="share">{share_label}
<a href="https://t.me/share/url?url={canonical}&text={share_text}">Telegram</a>
<a href="https://twitter.com/intent/tweet?url={canonical}&text={share_text}">X / Twitter</a>
</div>
<footer>{footer}</footer>
</div></div>
</body>
</html>
"""

_INDEX = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Telegram channels by region — US and Latin America</title>
<meta name="description" content="Free Telegram channels for US readers (crypto, AI, sports) and for Latin America and Spain (cripto, IA, fútbol). Daily sourced news.">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:url" content="{canonical}">
<meta property="og:title" content="Telegram channels by region — US and Latin America">
<meta property="og:description" content="Free Telegram channels for US readers (crypto, AI, sports) and for Latin America and Spain (cripto, IA, fútbol).">
<style>
:root{{color-scheme:light dark;--bg:#f6f7fb;--card:#fff;--text:#18202c;--muted:#5a6572;--accent:#2b6cb0;}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f141b;--card:#18202b;--text:#e8edf5;--muted:#9aa7b8;--accent:#7fb3e8;}}}}
*{{box-sizing:border-box}}body{{margin:0;font:16px/1.6 -apple-system,"Segoe UI",Roboto,Arial,sans-serif;background:var(--bg);color:var(--text)}}
.wrap{{max-width:860px;margin:0 auto;padding:48px 16px}}h1{{font-size:30px;margin:0 0 6px}}.muted{{color:var(--muted)}}
h2{{font-size:17px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:34px 0 10px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}}
a.card{{display:block;background:var(--card);border-radius:14px;padding:18px;text-decoration:none;color:var(--text);box-shadow:0 4px 18px rgba(15,25,40,.07)}}
a.card strong{{display:block;font-size:17px;margin-bottom:4px}}a.card span{{color:var(--muted);font-size:14px}}
footer{{color:var(--muted);font-size:13px;margin-top:28px}}footer a{{color:var(--accent)}}
</style>
</head>
<body><div class="wrap">
<h1>Telegram channels by region</h1>
<p class="muted">Free, sourced daily news. English channels for US readers; Spanish channels for Latin America and Spain.</p>
<h2>United States — English</h2>
<div class="grid">{us_cards}</div>
<h2>Latinoamérica y España — Español</h2>
<div class="grid">{es_cards}</div>
<footer>All channels hub: <a href="{hub}">{hub}</a> · <a href="{tg}">Telegram</a></footer>
</div></body>
</html>
"""


def _esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _load_channels() -> List[dict]:
    channels: List[dict] = []
    for name in ("channels.en.yaml", "channels.es.yaml"):
        data = yaml.safe_load((ROOT / "config" / name).read_text(encoding="utf-8")) or {}
        for channel in data.get("channels") or []:
            if channel.get("id") in GEO:
                channels.append(channel)
    return channels


def _jsonld(geo: Dict[str, str], page: str, tg: str) -> str:
    import json

    data = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "Telegram channel network — crypto, AI and sports",
        "url": page.rsplit("/", 1)[0] + "/",
        "sameAs": [tg],
        "description": "Free Telegram channels with daily crypto, AI and sports news in English and Spanish.",
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def build(out: Path, base_url: str) -> Dict[str, List[str]]:
    base = base_url.rstrip("/")
    hub = base + "/"
    out.mkdir(parents=True, exist_ok=True)
    channels = _load_channels()
    written: List[str] = []
    us_cards: List[str] = []
    es_cards: List[str] = []

    for channel in channels:
        cid = channel["id"]
        geo = GEO[cid]
        page_url = base + "/channels/" + geo["slug"] + ".html"
        tg = channel.get("public_url") or ""
        is_es = geo["lang"] == "es"
        ctx = {
            "lang": geo["lang"],
            "region": geo["region"],
            "place": geo["place"],
            "title": _esc(geo["title"]),
            "description": _esc(geo["lead"]),
            "canonical": page_url,
            "og_locale": "es_ES" if is_es else "en_US",
            "hub": hub,
            "tg": _esc(tg),
            "jsonld": _jsonld(geo, page_url, tg),
            "badge": "EE. UU. · Telegram" if is_es else "United States · Telegram",
            "h1": _esc(geo["h1"]),
            "lead": _esc(geo["lead"]),
            "cta_label": "Abrir en Telegram" if is_es else "Open in Telegram",
            "all_label": "Todos los canales" if is_es else "All channels",
            "inside_title": "Qué recibes" if is_es else "What you get",
            "inside": "".join(f"<li>{_esc(x)}</li>" for x in geo["inside"]),
            "who_title": "Para quién" if is_es else "Who it's for",
            "for_whom": _esc(geo["for_whom"]),
            "sources_title": "Fuentes" if is_es else "Sources",
            "sources": _esc(geo["sources"]),
            "share_label": "Compartir:" if is_es else "Share:",
            "share_text": urllib.parse.quote(geo["title"]),
            "footer": (
                ("Canal gratuito · contenido 18+ · "
                 f'<a href="{base}/subscribe/es/">Resumen semanal por email</a>')
                if cid == "futbol-es"
                else (
                    ("Canal gratuito · sin publicidad · "
                     f'<a href="{base}/subscribe/es/">Resumen semanal por email</a>')
                    if is_es
                    else ("Free channel · no ads · "
                          f'<a href="{base}/subscribe/">Weekly email digest</a>')
                )
            ),
        }
        path = out / (geo["slug"] + ".html")
        path.write_text(_TEMPLATE.format(**ctx), encoding="utf-8")
        written.append(str(path))
        card = (
            f'<a class="card" href="{geo["slug"]}.html"><strong>{_esc(channel["title"])}</strong>'
            f'<span>{_esc(geo["h1"])}</span></a>'
        )
        (es_cards if is_es else us_cards).append(card)

    index_url = base + "/channels/"
    index = _INDEX.format(
        canonical=index_url,
        hub=hub,
        tg="https://t.me/HOOPY0007",
        us_cards="\n".join(us_cards),
        es_cards="\n".join(es_cards),
    )
    (out / "index.html").write_text(index, encoding="utf-8")
    written.append(str(out / "index.html"))
    return {"pages": written, "index": [index_url]}


def update_sitemap(sitemap: Path, base_url: str, out: Path) -> None:
    base = base_url.rstrip("/")
    urls = [base + "/", base + "/channels/"]
    for channel in _load_channels():
        urls.append(base + "/channels/" + GEO[channel["id"]]["slug"] + ".html")
    today = date.today().isoformat()
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url in urls:
        lines += [
            "  <url>",
            f"    <loc>{_esc(url)}</loc>",
            f"    <lastmod>{today}</lastmod>",
            "    <changefreq>weekly</changefreq>",
            "    <priority>0.9</priority>",
            "  </url>",
        ]
    lines.append("</urlset>")
    sitemap.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Гео-лендинги каналов (GitHub Pages)")
    parser.add_argument("--out", default="docs/channels", help="Каталог для страниц")
    parser.add_argument("--base-url", required=True, help="Базовый URL сайта")
    parser.add_argument("--sitemap", default="docs/sitemap.xml", help="Sitemap для обновления")
    args = parser.parse_args(argv)
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    result = build(out, args.base_url)
    sitemap = Path(args.sitemap)
    if not sitemap.is_absolute():
        sitemap = ROOT / sitemap
    update_sitemap(sitemap, args.base_url, out)
    print(f"Страниц: {len(result['pages'])} (+index), sitemap: {sitemap}")
    for page in result["pages"]:
        print("  •", page)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
