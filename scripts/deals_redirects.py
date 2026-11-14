#!/usr/bin/env python3
"""GitHub Pages: редиректы docs/deals/*.html → нейтральный deed.page.

Реальные страницы лежат в build/deals и публикуются на deed.page; в репозитории
(docs/deals) остаются только редиректы без имени владельца в контенте.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://ofertas-finds.deed.page"
TEMPLATE = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="0; url={target}">
<link rel="canonical" href="{target}">
<meta name="robots" content="noindex">
<title>Ofertas y hallazgos</title>
<style>body{{background:#0b1220;color:#e8eefc;font:16px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}a{{color:#4f8cff}}</style>
</head><body><p>Переадресация… <a href="{target}">Ofertas y hallazgos</a></p>
<script>location.replace({target_js});</script>
</body></html>
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=str(ROOT / "build" / "deals"))
    parser.add_argument("--out", default=str(ROOT / "docs" / "deals"))
    parser.add_argument("--base", default=BASE)
    args = parser.parse_args(argv)
    src, out = Path(args.src), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    wanted = set()
    for path in sorted(src.glob("*.html")):
        name = path.name
        wanted.add(name)
        target = args.base + "/" + ("" if name == "index.html" else name)
        out.joinpath(name).write_text(
            TEMPLATE.format(target=target, target_js=repr(target).replace("'", '"')),
            encoding="utf-8",
        )
    for stale in out.glob("*"):
        if stale.is_file() and stale.name not in wanted:
            stale.unlink()
    print(f"redirects: {len(wanted)} → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
