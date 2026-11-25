#!/usr/bin/env python3
"""Add hreflang pairs (EN/ES) and missing canonicals on the static site.

Idempotent: existing tags are left untouched. Run from content-factory:

    python3 scripts/add_hreflang_pairs.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SITE = "https://valdislavn-spec.github.io/content-factory"
TF = SITE + "/travel-finds"

# EN page -> ES page (relative to docs/)
PAIRS = {
    "travel-finds/blog/flexible-dates-cheaper-flights.html": "travel-finds/es/blog/fechas-flexibles-vuelos-baratos.html",
    "travel-finds/blog/cheap-city-breaks-europe-2026.html": "travel-finds/es/blog/escapadas-economicas-europa-2026.html",
    "travel-finds/blog/index.html": "travel-finds/es/blog/index.html",
    "travel-finds/guides/us-car-rental.html": "travel-finds/es/guias/alquiler-coches-espana.html",
    "travel-finds/guides/us-esim.html": "travel-finds/es/guias/esim-viajar-latam.html",
    "travel-finds/guides/us-airport-transfers.html": "travel-finds/es/guias/traslados-aeropuerto.html",
}

# static pages that had no canonical (self-canonical added, no hreflang)
CANONICALS = {
    "landing/index.html": SITE + "/landing/",
    "partners/ads/index.html": SITE + "/partners/ads/",
}


def url(rel: str) -> str:
    page = rel[:-len("index.html")] if rel.endswith("index.html") else rel
    return SITE + "/" + page


def add_hreflang(html: str, en_url: str, es_url: str) -> str:
    if "hreflang=\"en\"" in html and "hreflang=\"es\"" in html:
        return html
    block = (
        '<link rel="alternate" hreflang="en" href="%s">\n'
        '<link rel="alternate" hreflang="es" href="%s">\n'
        '<link rel="alternate" hreflang="x-default" href="%s">\n'
    ) % (en_url, es_url, en_url)
    return html.replace("</head>", block + "</head>", 1)


def add_canonical(html: str, canonical: str) -> str:
    if 'rel="canonical"' in html:
        return html
    tag = '<link rel="canonical" href="%s">\n' % canonical
    return html.replace("</head>", tag + "</head>", 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    changed = []
    for en_rel, es_rel in PAIRS.items():
        en_file, es_file = DOCS / en_rel, DOCS / es_rel
        if not en_file.exists() or not es_file.exists():
            print("skip missing pair", en_rel, es_rel)
            continue
        en_url, es_url = url(en_rel), url(es_rel)
        for path, source, target in ((en_file, en_url, es_url), (es_file, es_url, en_url)):
            html = path.read_text(encoding="utf-8")
            updated = add_hreflang(html, source, target)
            if updated != html:
                changed.append(str(path.relative_to(DOCS)))
                if not args.dry_run:
                    path.write_text(updated, encoding="utf-8")
    for rel, canonical in CANONICALS.items():
        path = DOCS / rel
        if not path.exists():
            continue
        html = path.read_text(encoding="utf-8")
        updated = add_canonical(html, canonical)
        if updated != html:
            changed.append(str(path.relative_to(DOCS)))
            if not args.dry_run:
                path.write_text(updated, encoding="utf-8")
    print("changed {n} files".format(n=len(changed)))
    for item in changed:
        print(" -", item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
