#!/usr/bin/env python3
"""Check that every link in generated pin artifacts is active.

Offline by default: validates scheme/host and rejects placeholder domains
(``is.gd``, ``example.com`` …). With ``--live`` it also performs HTTP requests
and reports the final status, so a batch cannot be uploaded to Pinterest with
dead destinations.

Usage::

    python3 scripts/check_links.py                       # offline: pins-v5 + pins + CSV
    python3 scripts/check_links.py --live                 # + live HTTP check
    python3 scripts/check_links.py docs/assets/pins-v5 --json /tmp/links.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Iterator, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.integrations.partner_links import (  # noqa: E402
    check_links_live,
    validate_link,
)

DEFAULT_TARGETS = [
    ROOT / "docs" / "assets" / "pins-v5",
    ROOT / "docs" / "assets" / "pins",
    ROOT / "docs" / "pinterest-import-v5.csv",
]


def iter_json_urls(path: Path) -> Iterator[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    def walk(node) -> Iterator[str]:
        if isinstance(node, dict):
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for item in node:
                yield from walk(item)
        elif isinstance(node, str) and node.startswith(("http://", "https://")):
            yield node

    yield from walk(data)


def iter_csv_urls(path: Path) -> Iterator[str]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                for key in ("Media URL", "Link", "Thumbnail"):
                    value = str(row.get(key) or "").strip()
                    if value.startswith(("http://", "https://")):
                        yield value
    except OSError:
        return


def collect(targets: List[Path]) -> List[str]:
    urls: List[str] = []
    for target in targets:
        target = Path(target)
        if target.is_dir():
            for path in sorted(target.rglob("*")):
                if path.suffix == ".json" and path.name not in {"index.json", "meta.json", "qa-report.json"}:
                    urls.extend(iter_json_urls(path))
                elif path.suffix == ".csv":
                    urls.extend(iter_csv_urls(path))
        elif target.suffix == ".csv":
            urls.extend(iter_csv_urls(target))
        elif target.suffix == ".json":
            urls.extend(iter_json_urls(target))
    # уникальные, в порядке появления
    return list(dict.fromkeys(urls))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check links in pin artifacts")
    parser.add_argument("targets", nargs="*", help="files/dirs (default: pins-v5, pins, CSV)")
    parser.add_argument("--live", action="store_true", help="perform HTTP checks")
    parser.add_argument("--timeout", type=float, default=12.0, help="HTTP timeout, seconds")
    parser.add_argument("--json", default="", help="write machine-readable report here")
    args = parser.parse_args(argv)

    targets = [Path(item) for item in args.targets] or [item for item in DEFAULT_TARGETS if item.exists()]
    urls = collect(targets)
    if not urls:
        print("no links found in:", ", ".join(str(item) for item in targets))
        return 1

    report = {"targets": [str(item) for item in targets], "links": [], "ok": True}
    placeholder = []
    for url in urls:
        problems = validate_link(url)
        entry = {"url": url, "ok": not problems, "problems": problems}
        if problems:
            placeholder.append(entry)
        report["links"].append(entry)

    live_entries = []
    if args.live:
        for check in check_links_live(urls, timeout=args.timeout):
            entry = {"url": check.url, "ok": check.ok, "status": check.status,
                     "reason": check.reason, "final_url": check.final_url}
            live_entries.append(entry)
        dead = [entry for entry in live_entries if not entry["ok"]]
    else:
        dead = []

    print("targets:", ", ".join(str(item) for item in targets))
    print("unique links:", len(urls), "| offline invalid:", len(placeholder), "| live:", "yes" if args.live else "no")
    if placeholder:
        print("\nНЕАКТИВНЫЕ (offline):")
        for entry in placeholder:
            print("  -", entry["url"], "->", "; ".join(entry["problems"]))
    if args.live:
        print("\nLIVE:")
        for entry in live_entries:
            print("  %-4s %s%s" % (entry["status"] or "ERR", entry["url"],
                                   "" if entry["ok"] else "  <- " + (entry["reason"] or "fail")))
        if dead:
            print("\nМЁРТВЫЕ:", len(dead))
            for entry in dead:
                print("  -", entry["url"], "->", entry["reason"] or entry["status"])

    report["ok"] = not placeholder and not dead
    report["live"] = live_entries
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("report ->", args.json)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
