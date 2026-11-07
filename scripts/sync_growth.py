#!/usr/bin/env python3
"""Синхронизация growth-отчётов из ветки growth-reports в data/reports/remote/.

Workflow growth-report коммитит свежие отчёты (Markdown + сырой JSON) в ветку
`growth-reports`; этот скрипт забирает их локально, чтобы анализировать без
скачивания артефактов из UI.

Запуск:
    python scripts/sync_growth.py [--branch growth-reports] [--out data/reports/remote]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Скачать growth-отчёты из ветки репозитория")
    parser.add_argument("--branch", default="growth-reports", help="ветка с отчётами")
    parser.add_argument("--out", default="data/reports/remote", help="куда сохранять файлы")
    return parser.parse_args(argv)


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    fetch = git("fetch", "origin", args.branch)
    if fetch.returncode != 0:
        print(
            "Ветка %s ещё не создана (workflow опубликует её после следующего запуска)."
            % args.branch,
            file=sys.stderr,
        )
        return 1

    listing = git("ls-tree", "-r", "--name-only", "origin/%s" % args.branch)
    if listing.returncode != 0:
        print(listing.stderr.strip(), file=sys.stderr)
        return 1
    files = [
        line.strip()
        for line in listing.stdout.splitlines()
        if line.strip().startswith("reports/")
        and line.strip().endswith((".md", ".json"))
    ]
    if not files:
        print("В ветке %s нет отчётов в reports/" % args.branch, file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for path in files:
        blob = git("show", "origin/%s:%s" % (args.branch, path))
        if blob.returncode != 0:
            print("не удалось прочитать %s" % path, file=sys.stderr)
            continue
        (out_dir / Path(path).name).write_text(blob.stdout, encoding="utf-8")
        saved += 1
    print("Сохранено файлов: %d → %s" % (saved, out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
