#!/usr/bin/env python3
"""Генератор лендингов товарных партнёрок (docs/deals/*.html).

Читает `data/deals/landing.yaml` (программы и товары) и генерирует статические
страницы: хаб, отдельная страница под каждую партнёрку и отдельная страница под
каждый товар. Деплой — GitHub Pages из папки `docs/` этого репозитория:

    https://valdislavn-spec.github.io/content-factory/deals/

    ./.venv/bin/python scripts/deals_landing.py
    ./.venv/bin/python scripts/deals_landing.py --out docs/deals --check
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data" / "deals" / "landing.yaml"
DEFAULT_OUT = ROOT / "docs" / "deals"

CSS = """
:root{--bg:#0b1220;--card:#121b2e;--card-hover:#17233c;--text:#e8eefc;--muted:#93a4c4;--accent:#4f8cff;--border:#22304d;--good:#46d39a;--warn:#ffb454}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1060px;margin:0 auto;padding:24px 18px 64px}
.nav{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:28px;flex-wrap:wrap}
.brand{font-weight:800;letter-spacing:.5px}
.nav .links{display:flex;gap:16px;flex-wrap:wrap;font-size:14px;color:var(--muted)}
h1{font-size:32px;line-height:1.2;margin:0 0 10px}
h2{font-size:22px;margin:34px 0 14px}
.lead{color:var(--muted);max-width:720px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px;margin-top:18px}
.card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:18px;display:flex;flex-direction:column;gap:10px;transition:background .15s}
.card:hover{background:var(--card-hover)}
.badge{display:inline-block;font-size:12px;color:var(--muted);border:1px solid var(--border);border-radius:999px;padding:2px 10px;width:fit-content}
.badge.live{color:var(--good);border-color:#1f5c46}
.badge.pending{color:var(--warn);border-color:#5c4620}
.card h3{margin:0;font-size:18px}
.price{font-size:22px;font-weight:800}
.price s{font-size:14px;color:var(--muted);font-weight:400;margin-left:8px}
.cta{display:inline-block;margin-top:auto;background:var(--accent);color:#fff;font-weight:700;padding:12px 16px;border-radius:12px;text-align:center}
.cta:hover{text-decoration:none;filter:brightness(1.08)}
.cta.disabled{background:#2a3550;color:var(--muted);cursor:default}
.desc{color:var(--muted);font-size:14px}
.panel{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:20px;margin-top:18px}
.foot{margin-top:44px;color:var(--muted);font-size:13px;border-top:1px solid var(--border);padding-top:18px}
.crumbs{font-size:14px;color:var(--muted);margin-bottom:16px}
.crumbs a{color:var(--muted)}
"""


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _num(text: str) -> float | None:
    m = re.search(r"\d+(?:[.,]\d+)?", str(text or "").replace(" ", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


def discount(old: str, price: str) -> int | None:
    a, b = _num(old), _num(price)
    if not a or not b or b >= a:
        return None
    return int(round((1 - b / a) * 100))


def with_utm(url: str, program: str) -> str:
    """Добавляет UTM простой строкой, не трогая уже закодированные партнёрские параметры."""
    if not url or "utm_source=" in url:
        return url
    suffix = (
        "utm_source=deals_page&utm_medium=landing&utm_campaign=deals_"
        + urllib.parse.quote(str(program or ""), safe="")
    )
    joiner = "&" if "?" in url else "?"
    return url + joiner + suffix


def page(title: str, description: str, canonical: str, body: str, base: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{esc(canonical)}">
<link rel="canonical" href="{esc(canonical)}">
<meta name="robots" content="index,follow">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="nav">
  <div class="brand">DEALS FACTORY</div>
  <nav class="links">
    <a href="{esc(base + '/deals/')}">Ofertas</a>
    <a href="{esc(base + '/')}">Canales</a>
  </nav>
</header>
{body}
<footer class="foot">
  <p>Enlaces de afiliado: podemos recibir una comisión si compras a través de ellos. Los precios pueden cambiar.</p>
  <p>© Deals Factory · <a href="{esc(base + '/')}">Nuestros canales de Telegram</a></p>
</footer>
</div>
</body>
</html>
"""


def product_card(p: Dict[str, Any], program: Dict[str, Any], base: str) -> str:
    disc = discount(p.get("old_price", ""), p.get("price", ""))
    old = f'<s>{esc(p["old_price"])}</s>' if p.get("old_price") else ""
    pct = f' <span class="desc">−{disc}%</span>' if disc else ""
    url = with_utm(str(p.get("url") or ""), str(p.get("program") or ""))
    detail = f'{base}/deals/p-{esc(p.get("id"))}.html'
    return f"""<article class="card">
  <span class="badge">{esc(p.get("badge_es") or p.get("program"))}</span>
  <h3><a href="{esc(detail)}">{esc(p.get("title_es"))}</a></h3>
  <div class="price">{esc(p.get("price"))}{old}{pct}</div>
  <div class="desc">{esc(p.get("subtitle_es"))}</div>
  <a class="cta" href="{esc(url)}" rel="nofollow sponsored noopener" target="_blank">Pedir ahora</a>
</article>"""


def program_card(prog: Dict[str, Any], base: str) -> str:
    status = str(prog.get("status") or "pending")
    label = "Disponible" if status == "live" else "Próximamente"
    cls = "live" if status == "live" else "pending"
    detail = f'{base}/deals/{esc(prog.get("slug"))}.html'
    cta = (
        f'<a class="cta" href="{esc(detail)}">{esc(prog.get("cta_es") or "Ver ofertas")}</a>'
        if status == "live"
        else '<span class="cta disabled">Próximamente</span>'
    )
    return f"""<article class="card">
  <span class="badge {cls}">{label}</span>
  <h3><a href="{esc(detail)}">{esc(prog.get("name"))}</a></h3>
  <div class="desc">{esc(prog.get("tagline_es"))}</div>
  {cta}
</article>"""


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build(data: Dict[str, Any], out: Path) -> List[Path]:
    base = str(data.get("site_base") or "").rstrip("/")
    programs: List[Dict[str, Any]] = data.get("programs") or []
    products: List[Dict[str, Any]] = data.get("products") or []
    by_program: Dict[str, List[Dict[str, Any]]] = {}
    for p in products:
        by_program.setdefault(str(p.get("program")), []).append(p)
    written: List[Path] = []

    # хаб
    hub_cards = "\n".join(program_card(prog, base) for prog in programs)
    live_products = "\n".join(
        product_card(p, next((x for x in programs if x.get("slug") == p.get("program")), {}), base)
        for p in products
        if str(p.get("program")) in {str(x.get("slug")) for x in programs if str(x.get("status")) == "live"}
    )
    body = f"""<h1>{esc(data.get("title"))}</h1>
<p class="lead">{esc(data.get("description"))}</p>
<h2>Programas</h2>
<div class="grid">{hub_cards}</div>
<h2>Ofertas de la semana</h2>
<div class="grid">{live_products}</div>"""
    path = out / "index.html"
    write(path, page(str(data.get("title")), str(data.get("description")), base + "/deals/", body, base))
    written.append(path)

    # страницы программ
    for prog in programs:
        slug = str(prog.get("slug"))
        prods = by_program.get(slug, [])
        cards = "\n".join(product_card(p, prog, base) for p in prods)
        if not cards:
            cards = '<p class="desc">Pronto añadiremos ofertas de esta tienda.</p>'
        body = f"""<p class="crumbs"><a href="{esc(base + '/deals/')}">Ofertas</a> / {esc(prog.get("name"))}</p>
<h1>{esc(prog.get("name"))} — ofertas</h1>
<p class="lead">{esc(prog.get("description_es"))}</p>
<p class="desc">{esc(prog.get("commission_es"))}</p>
<div class="grid">{cards}</div>"""
        if str(prog.get("status")) != "live" and prog.get("cta_url"):
            body += f'<div class="panel"><p class="desc">La integración está en curso. Следите за обновлениями в наших каналах.</p></div>'
        path = out / f"{slug}.html"
        desc = str(prog.get("tagline_es") or prog.get("name"))
        write(path, page(f'{prog.get("name")} — ofertas y hallazgos', desc, f"{base}/deals/{slug}.html", body, base))
        written.append(path)

    # страницы товаров
    for p in products:
        prog = next((x for x in programs if x.get("slug") == p.get("program")), {})
        disc = discount(p.get("old_price", ""), p.get("price", ""))
        url = with_utm(str(p.get("url") or ""), str(p.get("program") or ""))
        related = [
            product_card(x, prog, base)
            for x in by_program.get(str(p.get("program")), [])
            if x.get("id") != p.get("id")
        ][:4]
        related_html = f'<h2>Más de {esc(prog.get("name"))}</h2><div class="grid">{"".join(related)}</div>' if related else ""
        old = f'<s>{esc(p["old_price"])}</s>' if p.get("old_price") else ""
        pct = f' <span class="desc">−{disc}%</span>' if disc else ""
        status = str(prog.get("status") or "pending")
        cta = (
            f'<a class="cta" href="{esc(url)}" rel="nofollow sponsored noopener" target="_blank">{esc(prog.get("cta_es") or "Pedir ahora")}</a>'
            if status == "live" and url
            else '<span class="cta disabled">Pronto</span>'
        )
        body = f"""<p class="crumbs"><a href="{esc(base + '/deals/')}">Ofertas</a> / <a href="{esc(base + '/deals/' + str(prog.get('slug')) + '.html')}">{esc(prog.get("name"))}</a> / {esc(p.get("title_es"))}</p>
<h1>{esc(p.get("title_es"))}</h1>
<div class="panel">
  <div class="price">{esc(p.get("price"))}{old}{pct}</div>
  <p class="desc">{esc(p.get("subtitle_es"))}</p>
  {cta}
</div>
{related_html}"""
        path = out / f"p-{p.get('id')}.html"
        write(path, page(f'{p.get("title_es")} — {prog.get("name")}', str(p.get("subtitle_es") or p.get("title_es")), f"{base}/deals/p-{p.get('id')}.html", body, base))
        written.append(path)

    # sitemap
    urls = [f"{base}/deals/"] + [f"{base}/deals/{prog.get('slug')}.html" for prog in programs] + [f"{base}/deals/p-{p.get('id')}.html" for p in products]
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap += [f"  <url><loc>{esc(u)}</loc></url>" for u in urls]
    sitemap.append("</urlset>")
    sm = out / "sitemap.xml"
    write(sm, "\n".join(sitemap) + "\n")
    written.append(sm)
    return written


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Лендинги товарных партнёрок")
    parser.add_argument("--data", default=str(DEFAULT_DATA))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--check", action="store_true", help="только проверить данные, не писать файлы")
    args = parser.parse_args(argv)
    data = yaml.safe_load(Path(args.data).read_text(encoding="utf-8")) or {}
    if args.check:
        print(f"programs: {len(data.get('programs') or [])}, products: {len(data.get('products') or [])}")
        return 0
    files = build(data, Path(args.out))
    print(f"Готово: {len(files)} файлов в {args.out}")
    for f in files:
        print(" -", f.relative_to(ROOT) if f.is_relative_to(ROOT) else f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
