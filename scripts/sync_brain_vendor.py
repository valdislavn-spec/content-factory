#!/usr/bin/env python3
"""Обновить vendor/mcp-content-factory из соседнего mcp-content-factory.

Единая структура: content-factory — единственный репозиторий, который
чекаутит GitHub Actions. Чтобы мост «мозга» работал в облаке, mcp_factory
лежит в vendor/ и обновляется этой командой из dev-копии:

    python scripts/sync_brain_vendor.py [--source ../mcp-content-factory]

Копируются только нужные для работы файлы: пакет mcp_factory, config/
(demo/brain/…), pyproject.toml и README.md. .venv, data, out, тесты и
кэши не попадают в репозиторий.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT.parent / "mcp-content-factory"
TARGET = ROOT / "vendor" / "mcp-content-factory"
PACKAGE = "mcp_factory"
CONFIG = "config"
FILES = ("pyproject.toml", "README.md")


def _copy_tree(source: Path, target: Path) -> int:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".pytest_cache", ".venv", "out", "out-*", "data"
        ),
    )
    return sum(1 for _ in target.rglob("*.py"))


def sync(source: Path) -> int:
    source = source.resolve()
    if not (source / PACKAGE).is_dir():
        print("Нет исходника: {}".format(source / PACKAGE), file=sys.stderr)
        return 1
    TARGET.mkdir(parents=True, exist_ok=True)
    py_files = _copy_tree(source / PACKAGE, TARGET / PACKAGE)
    if (source / CONFIG).is_dir():
        _copy_tree(source / CONFIG, TARGET / CONFIG)
    for name in FILES:
        origin = source / name
        if origin.is_file():
            shutil.copy2(origin, TARGET / name)
    print(
        "vendor/mcp-content-factory обновлён: {} .py файлов, config, {}".format(
            py_files, ", ".join(FILES)
        )
    )
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Синхронизировать vendor-мозг")
    parser.add_argument(
        "--source", default=str(DEFAULT_SOURCE), help="откуда копировать mcp-content-factory"
    )
    args = parser.parse_args(argv)
    return sync(Path(args.source))


if __name__ == "__main__":
    raise SystemExit(main())
