#!/usr/bin/env python3
"""Бэкап данных контент-завода в папку OneDrive (или локально, если её нет).

Что попадает в архив:
    data/            — SQLite (согласованный снимок через backup API), отчёты,
                       outbox, аналитика, логи, demo
    config/          — настройки каналов (без секретов)
    docs/promo/      — промо-материалы, медиакит, планы
    scripts/         — скрипты завода
    .env.example     — шаблон секретов (сам .env НЕ включается — это секреты)

Куда:
    ~/OneDrive/ContentFactoryBackups/  или
    ~/Library/CloudStorage/OneDrive*/ContentFactoryBackups/
    Если OneDrive не установлен — data/backups/ (локальный фолбэк) с подсказкой.

Запуск:
    python scripts/backup_onedrive.py            # авто-выбор папки
    python scripts/backup_onedrive.py --dry-run  # показать план
    python scripts/backup_onedrive.py --target ~/OneDrive/ContentFactoryBackups
    python scripts/backup_onedrive.py --keep 14  # сколько архивов хранить
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sqlite3
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KEEP = 14
EXCLUDE_DIRS = {
    "__pycache__", ".git", "node_modules", "venv", ".venv", "backups",
    # модели Ollama (7+ ГБ) — скачиваются заново, в облако не нужны
    "ollama",
}
EXCLUDE_FILES = {".env", "llm_cache.sqlite3", "llm_tokens.json", "llm_usage.json"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".swp", ".tmp", ".pma", ".dmp"}

log = logging.getLogger("backup")


def find_onedrive_dir() -> Optional[Path]:
    """Папка синхронизации OneDrive, если приложение установлено и настроено."""
    home = Path.home()
    direct = home / "OneDrive"
    if direct.is_dir():
        return direct
    for candidate in sorted(home.glob("Library/CloudStorage/OneDrive*")):
        if candidate.is_dir():
            return candidate
    for candidate in sorted(home.glob("OneDrive*")):
        if candidate.is_dir():
            return candidate
    return None


def human_size(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return "{:.1f} {}".format(num, unit) if unit != "B" else "{} B".format(num)
        num /= 1024.0
    return "{} B".format(num)


def should_skip(path: Path) -> bool:
    if path.name in EXCLUDE_FILES:
        return True
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return True
    return any(part in EXCLUDE_DIRS for part in path.parts)


def collect_paths() -> List[Path]:
    """Список файлов/каталогов для архива (существующие)."""
    wanted = [
        ROOT / "data",
        ROOT / "config",
        ROOT / "docs" / "promo",
        ROOT / "scripts",
        ROOT / ".env.example",
    ]
    return [path for path in wanted if path.exists()]


def add_tree(tar: tarfile.TarFile, source: Path, staging: Path) -> int:
    """Добавляет файл/каталог в архив, пропуская мусор. Возвращает число файлов."""
    count = 0
    if source.is_file():
        if should_skip(source):
            return 0
        tar.add(source, arcname=str(source.relative_to(ROOT)))
        return 1
    for path in sorted(source.rglob("*")):
        if not path.is_file() or should_skip(path):
            continue
        tar.add(path, arcname=str(path.relative_to(ROOT)))
        count += 1
    return count


def snapshot_sqlite(db_path: Path, staging: Path) -> Optional[Path]:
    """Согласованный снимок SQLite через online backup API (без блокировки)."""
    if not db_path.is_file():
        return None
    destination = staging / db_path.name
    source_conn = sqlite3.connect("file:{}?mode=ro".format(db_path), uri=True)
    try:
        target_conn = sqlite3.connect(str(destination))
        try:
            source_conn.backup(target_conn)
        finally:
            target_conn.close()
    finally:
        source_conn.close()
    return destination


def build_archive(target_dir: Path, keep: int, dry_run: bool = False) -> Optional[Path]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = target_dir / "content-factory-backup-{}.tar.gz".format(stamp)
    sources = collect_paths()
    log.info("Источники: %s", ", ".join(str(p.relative_to(ROOT)) for p in sources))
    if dry_run:
        total = sum(
            1
            for source in sources
            for _ in ([source] if source.is_file() else source.rglob("*"))
            if _.is_file() and not should_skip(_)
        )
        log.info("dry-run: файлов ~%d, архив был бы %s", total, archive)
        return None
    target_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        db_copy = snapshot_sqlite(ROOT / "data" / "factory.sqlite3", staging)
        count = 0
        with tarfile.open(archive, "w:gz") as tar:
            for source in sources:
                if source == ROOT / "data" and db_copy is not None:
                    # data/ без живой БД: вместо неё — согласованный снимок
                    for path in sorted(source.rglob("*")):
                        if not path.is_file() or should_skip(path):
                            continue
                        if path.name == "factory.sqlite3":
                            continue
                        tar.add(path, arcname=str(path.relative_to(ROOT)))
                        count += 1
                    tar.add(db_copy, arcname="data/factory.sqlite3")
                    count += 1
                else:
                    count += add_tree(tar, source, staging)
    size = archive.stat().st_size
    digest = hashlib.sha256()
    with archive.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    (archive.with_suffix(".sha256")).write_text(
        "{}  {}\n".format(digest.hexdigest(), archive.name), encoding="utf-8"
    )
    log.info("Архив: %s (%s, файлов %d)", archive, human_size(size), count)
    prune(target_dir, keep)
    if db_copy is not None:
        db_copy.unlink(missing_ok=True)
    return archive


def prune(target_dir: Path, keep: int) -> None:
    """Удаляет старые архивы, оставляя последние keep штук."""
    archives = sorted(target_dir.glob("content-factory-backup-*.tar.gz"))
    for old in archives[: max(0, len(archives) - keep)]:
        log.info("Удаляю старый архив: %s", old.name)
        old.unlink(missing_ok=True)
        old.with_suffix(".sha256").unlink(missing_ok=True)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Бэкап контент-завода в OneDrive")
    parser.add_argument("--target", default="", help="папка для архивов (по умолчанию — OneDrive)")
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP, help="сколько архивов хранить")
    parser.add_argument("--dry-run", action="store_true", help="только показать план")
    parser.add_argument("--verbose", action="store_true", help="подробный лог")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    one_drive = find_onedrive_dir()
    if args.target:
        target_dir = Path(os.path.expanduser(args.target))
    elif one_drive is not None:
        target_dir = one_drive / "ContentFactoryBackups"
        log.info("OneDrive найден: %s", one_drive)
    else:
        target_dir = ROOT / "data" / "backups"
        log.warning(
            "OneDrive не найден — бэкап локальный (%s). Установите и настройте "
            "OneDrive для Mac, чтобы архивы уезжали в облако.",
            target_dir,
        )
    archive = build_archive(target_dir, max(1, args.keep), dry_run=args.dry_run)
    print("OK", archive if archive else "(dry-run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
