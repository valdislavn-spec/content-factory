#!/usr/bin/env python3
"""Подборки дешёвых билетов: страницы и посты для Telegram (RU и EN наборы).

Источник данных — уже отрендеренные витрины /flights/almaty/ и /flights/minsk/
(их обновляет flights_digest.py). Пишет:

    docs/collections/…          — русский набор (оба города, цены в ₽)
    docs/collections/en/…       — английский набор (только Алматы, цены в $)
    data/outbox/collections/…   — готовые посты (HTML, parse_mode=HTML)
    data/collections/latest*.json — снимки цен
    docs/sitemap.xml            — дописывает новые адреса и убирает исчезнувшие

Примеры:
    python scripts/flights_collections.py                 # только русский набор
    python scripts/flights_collections.py --lang both     # оба набора
    python scripts/flights_collections.py --lang en --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_factory import flights_collections as fc  # noqa: E402
from content_factory import flights_collections_en as en  # noqa: E402


def build_ru(args) -> int:
    docs = Path(args.docs)
    deals = fc.load_deals(docs)
    if not deals:
        print("[ru] нет данных: страницы /flights/*/index.html не найдены или пусты")
        return 1

    updated = fc.page_updated(docs)
    cols = fc.build_collections(deals, min_deals=args.min_deals)
    if not cols:
        print("[ru] подборки не собрались: слишком мало сделок (%d)" % len(deals))
        return 1

    print("[ru] сделок: %d | подборок: %d | обновлено: %s" % (
        len(deals), len(cols), fc.fmt_updated(updated)))
    for col in cols:
        print("     %-22s %s  от %s" % (col.slug, fc.directions(col.count), fc.money(col.cheapest)))

    if args.dry_run:
        print("\n--- пример поста (%s) ---" % cols[0].slug)
        print(fc.render_post(cols[0], updated))
        return 0

    pages = fc.write_site(Path(args.out), cols, updated)
    posts = fc.write_posts(Path(args.posts), cols, updated)
    snapshot = fc.write_snapshot(Path(args.snapshot), cols, updated)
    print("[ru] страниц: %d | постов: %d | снимок: %s" % (len(pages), len(posts), snapshot))

    if not args.no_sitemap:
        urls = fc.sitemap_urls(cols)
        added = fc.update_sitemap(Path(args.sitemap), urls,
                                  prune_prefix=fc.PUBLIC + "/collections/",
                                  protect=[fc.PUBLIC + en.ROOT_PREFIX + "/"])
        print("[ru] sitemap: добавлено %d" % added)
    return 0


def build_en(args) -> int:
    docs = Path(args.docs)
    deals = [d for d in fc.load_deals(docs) if d.origin == "ALA"]
    if not deals:
        print("[en] нет данных по Алматы")
        return 1

    updated = fc.page_updated(docs)
    rate, note = en.fetch_rub_usd()
    cols = en.build(en.convert_to_usd(deals, rate), min_deals=args.min_deals)
    if not cols:
        print("[en] подборки не собрались: слишком мало сделок (%d)" % len(deals))
        return 1

    print("[en] сделок: %d | подборок: %d | курс RUB→USD %.5f (%s)" % (len(deals), len(cols), rate, note))
    for col in cols:
        print("     %-18s %s  from %s" % (col.slug, en.routes(col.count), en.usd(col.cheapest)))

    if args.dry_run:
        print("\n--- sample post (%s) ---" % cols[0].slug)
        print(en.render_post(cols[0], updated))
        return 0

    out = Path(args.docs) / "collections" / "en"
    posts_dir = Path(args.posts) / "en"
    pages = en.write_site(out, cols, updated, rate, note)
    posts = en.write_posts(posts_dir, cols, updated)
    snapshot = Path(args.snapshot).with_name("latest-en.json")
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(
        json.dumps(
            {"updated": updated.isoformat(timespec="minutes") if updated else "",
             "rate_rub_usd": rate, "fx": note,
             "collections": [{"slug": c.slug, "title": c.title, "count": c.count,
                              "cheapest": c.cheapest,
                              "deals": [{"dest": d.dest, "price": d.price,
                                         "dep": d.dep.isoformat() if d.dep else "",
                                         "link": d.link} for d in c.deals]}
                             for c in cols]},
            ensure_ascii=False, indent=2),
        encoding="utf-8")
    print("[en] страниц: %d | постов: %d | снимок: %s" % (len(pages), len(posts), snapshot))

    if not args.no_sitemap:
        urls = en.sitemap_urls(cols)
        added = fc.update_sitemap(Path(args.sitemap), urls,
                                  prune_prefix=fc.PUBLIC + en.ROOT_PREFIX + "/")
        print("[en] sitemap: добавлено %d" % added)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Подборки дешёвых билетов")
    parser.add_argument("--lang", choices=["ru", "en", "both"], default="ru")
    parser.add_argument("--docs", default=str(ROOT / "docs"), help="каталог сайта (docs)")
    parser.add_argument("--out", default=str(ROOT / "docs" / "collections"),
                        help="куда писать русские страницы")
    parser.add_argument("--posts", default=str(ROOT / "data" / "outbox" / "collections"),
                        help="куда писать посты для Telegram")
    parser.add_argument("--snapshot", default=str(ROOT / "data" / "collections" / "latest.json"))
    parser.add_argument("--sitemap", default=str(ROOT / "docs" / "sitemap.xml"))
    parser.add_argument("--min-deals", type=int, default=3, help="минимум сделок в подборке")
    parser.add_argument("--no-sitemap", action="store_true", help="не трогать sitemap.xml")
    parser.add_argument("--dry-run", action="store_true", help="только показать результат")
    args = parser.parse_args(argv)

    code = 0
    if args.lang in ("ru", "both"):
        code |= build_ru(args)
    if args.lang in ("en", "both"):
        code |= build_en(args)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
