#!/usr/bin/env python3
"""Подборки дешёвых билетов: тематические страницы + посты для Telegram.

Читает уже отрендеренные витрины /flights/almaty/ и /flights/minsk/ (их обновляет
flights_digest.py), раскладывает сделки по подборкам и пишет:

    docs/collections/index.html          — хаб подборок
    docs/collections/<slug>/index.html   — страница подборки
    data/outbox/collections/<slug>.html  — готовый пост в Telegram (HTML)
    data/collections/latest.json         — снимок цен
    docs/sitemap.xml                     — дописывает новые адреса

Примеры:
    python scripts/flights_collections.py                # собрать всё и проверить
    python scripts/flights_collections.py --dry-run      # показать, что получится
    python scripts/flights_collections.py --no-sitemap   # без правки sitemap
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory import flights_collections as fc  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Тематические подборки дешёвых билетов")
    parser.add_argument("--docs", default=str(ROOT / "docs"), help="каталог сайта (docs)")
    parser.add_argument("--out", default=str(ROOT / "docs" / "collections"), help="куда писать страницы")
    parser.add_argument("--posts", default=str(ROOT / "data" / "outbox" / "collections"),
                        help="куда писать посты для Telegram")
    parser.add_argument("--snapshot", default=str(ROOT / "data" / "collections" / "latest.json"))
    parser.add_argument("--sitemap", default=str(ROOT / "docs" / "sitemap.xml"))
    parser.add_argument("--min-deals", type=int, default=3, help="минимум сделок в подборке")
    parser.add_argument("--no-sitemap", action="store_true", help="не трогать sitemap.xml")
    parser.add_argument("--dry-run", action="store_true", help="только показать результат")
    args = parser.parse_args(argv)

    docs = Path(args.docs)
    deals = fc.load_deals(docs)
    if not deals:
        print("нет данных: страницы /flights/*/index.html не найдены или пусты")
        return 1

    updated = fc.page_updated(docs)
    cols = fc.build_collections(deals, min_deals=args.min_deals)
    if not cols:
        print("подборки не собрались: слишком мало сделок (%d)" % len(deals))
        return 1

    print("сделок: %d | подборок: %d | обновлено: %s" % (
        len(deals), len(cols), fc.fmt_updated(updated)))
    for col in cols:
        print("  %-22s %s  от %s" % (col.slug, fc.directions(col.count), fc.money(col.cheapest)))

    if args.dry_run:
        print("\n--- пример поста (%s) ---" % cols[0].slug)
        print(fc.render_post(cols[0], updated))
        return 0

    pages = fc.write_site(Path(args.out), cols, updated)
    posts = fc.write_posts(Path(args.posts), cols, updated)
    snapshot = fc.write_snapshot(Path(args.snapshot), cols, updated)
    print("страниц: %d | постов: %d | снимок: %s" % (len(pages), len(posts), snapshot))

    if not args.no_sitemap:
        urls = fc.sitemap_urls(cols)
        added = fc.update_sitemap(Path(args.sitemap), urls,
                                  prune_prefix=fc.PUBLIC + "/collections/")
        print("sitemap: добавлено %d, убрано устаревших" % added)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
