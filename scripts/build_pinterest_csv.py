#!/usr/bin/env python3
"""Build a Pinterest bulk-upload CSV from generated pin sidecars (validated).

Pinterest Settings → Import content accepts a CSV with columns:
Title (required), Media URL (required), Pinterest board (required),
Thumbnail, Description, Link, Publish date, Keywords.
Boards that do not exist are created automatically.

Validation (``content_factory/brand/design.py``):
* Title required, <= 100 chars;
* Description required, <= 500 chars;
* Media URL absolute http(s) image URL;
* Pinterest board present (warns for non-standard board names);
* Keywords present, no empty values, each <= 64 chars, total <= 320 chars;
* Link must be a live https URL (no is.gd/example.com placeholders; see
  ``content_factory/integrations/partner_links.py``);
* affiliate pins must have an http(s) Link and should mention the disclosure;
* duplicate titles / media URLs are reported.

Usage:
    python scripts/build_pinterest_csv.py --pins docs/assets/pins --out docs/pinterest-import.csv
    python scripts/build_pinterest_csv.py --pins docs/assets/pins-v5 --out /tmp/pins-v5.csv --strict
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.brand.design import (  # noqa: E402
    CSV_COLUMNS,
    build_csv_row,
    validate_csv_rows,
)
from content_factory.integrations.partner_links import (  # noqa: E402
    check_links_live,
    validate_link,
)

HUB = "https://valdislavn-spec.github.io/content-factory/"
SKIP_NAMES = {"index.json", "meta.json"}


def load_sidecars(pins_dir: Path) -> list:
    """Read pin sidecars (dicts with a ``pin`` payload); report skipped files."""
    metas = []
    for path in sorted(pins_dir.rglob("*.json")):
        if path.name in SKIP_NAMES:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print("skip %s: %s" % (path.name, error), file=sys.stderr)
            continue
        if not isinstance(data, dict):
            print("skip %s: not a pin sidecar (expected an object)" % path.name, file=sys.stderr)
            continue
        if not isinstance(data.get("pin"), dict):
            print("skip %s: no 'pin' payload" % path.name, file=sys.stderr)
            continue
        metas.append(data)
    return metas


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build a validated Pinterest import CSV")
    parser.add_argument("--pins", default=str(ROOT / "docs" / "assets" / "pins"))
    parser.add_argument("--out", default=str(ROOT / "docs" / "pinterest-import.csv"))
    parser.add_argument("--link", default=HUB, help="fallback Link for pins without one")
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    parser.add_argument(
        "--check-links",
        action="store_true",
        help="live-check every Link (HTTP 2xx/3xx) before writing the CSV",
    )
    args = parser.parse_args(argv)

    metas = load_sidecars(Path(args.pins))
    if not metas:
        print("no pin sidecars found in %s" % args.pins)
        return 1
    rows = [build_csv_row(meta, default_link=args.link) for meta in metas]
    errors, warnings = validate_csv_rows(rows, metas=metas, strict=args.strict)
    # Ссылки пинов: никаких заглушек и мёртвых доменов.
    for row in rows:
        problems = validate_link(row.get("Link", ""))
        if problems:
            errors.append("%s: неактивная Link (%s)" % (row.get("Title", "?")[:40], "; ".join(problems)))
    if args.check_links:
        links = [row.get("Link", "") for row in rows]
        print("live-check links:")
        for check in check_links_live(links):
            print("  %-4s %s -> %s" % (check.status or "ERR", check.url, check.reason or check.final_url))
            if not check.ok:
                errors.append("мёртвая ссылка: %s (%s)" % (check.url, check.reason))
    for warning in warnings:
        print("WARNING:", warning)
    for error in errors:
        print("ERROR:", error)
    if errors:
        print(
            "validation failed: %d error(s), %d warning(s) - CSV not written"
            % (len(errors), len(warnings))
        )
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
    print("csv rows:", len(rows), "->", out, "| warnings:", len(warnings))
    for row in rows:
        print(" -", row["Pinterest board"], "|", row["Title"], "|", row["Media URL"][:80])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
