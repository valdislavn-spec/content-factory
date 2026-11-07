"""Конвертация документов в Markdown для контент-завода.

Позволяет использовать PDF/Word/PowerPoint/Excel/HTML/CSV как источники
наравне с RSS и веб-страницами. Конвертер ``markitdown`` ставится в отдельное
изолированное окружение и вызывается как подпроцесс, поэтому основной пакет
не тянет тяжёлых зависимостей.

Окружение:
    CONTENT_FACTORY_MARKITDOWN_BIN — путь к исполняемому ``markitdown``.
    По умолчанию ищется ``<workspace>/tools/markitdown-venv/bin/markitdown``,
    затем ``markitdown`` в ``PATH``.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .config import project_root

ENV_MARKITDOWN_BIN = "CONTENT_FACTORY_MARKITDOWN_BIN"

#: Файлы, которые читаются как текст без конвертации.
TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}

#: Всё, что умеет markitdown и что имеет смысл отдавать ему.
SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".doc",
    ".pptx",
    ".potx",
    ".xlsx",
    ".xlsm",
    ".xls",
    ".html",
    ".htm",
    ".csv",
    ".json",
    ".xml",
    ".epub",
    ".msg",
    ".rtf",
    ".zip",
} | TEXT_EXTENSIONS


class IngestError(RuntimeError):
    """Ошибка конвертации документа или отсутствия конвертера."""


def markitdown_bin() -> str:
    """Возвращает путь к исполняемому файлу markitdown."""
    override = os.environ.get(ENV_MARKITDOWN_BIN, "").strip()
    if override:
        path = Path(override).expanduser()
        if not path.is_file():
            raise IngestError(f"{ENV_MARKITDOWN_BIN} указывает на несуществующий файл: {path}")
        return str(path)
    candidates = [
        project_root().parent / "tools" / "markitdown-venv" / "bin" / "markitdown",
        Path.cwd() / "tools" / "markitdown-venv" / "bin" / "markitdown",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("markitdown")
    if found:
        return found
    raise IngestError(
        "markitdown не найден. Создайте окружение: "
        "uv venv tools/markitdown-venv && uv pip install --python "
        "tools/markitdown-venv/bin/python 'markitdown[pdf,docx,pptx,xlsx]', "
        f"либо укажите путь в {ENV_MARKITDOWN_BIN}."
    )


def is_supported(path: Path) -> bool:
    """Поддерживается ли расширение файла."""
    return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS


def convert_file(src: Path, out: Optional[Path] = None, timeout: int = 300) -> Path:
    """Конвертирует один документ в Markdown и возвращает путь к результату.

    Текстовые файлы (``.md``/``.txt``) возвращаются как есть.
    """
    src = Path(src).expanduser()
    if not src.is_file():
        raise IngestError(f"Файл не найден: {src}")
    if src.suffix.lower() in TEXT_EXTENSIONS:
        return src
    out_path = Path(out) if out else src.with_suffix(src.suffix + ".md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    command = [markitdown_bin(), str(src), "-o", str(out_path)]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise IngestError(f"markitdown превысил таймаут {timeout}s: {src.name}") from exc
    except OSError as exc:
        raise IngestError(f"Не удалось запустить markitdown: {exc}") from exc
    if proc.returncode != 0 or not out_path.is_file():
        detail = " ".join((proc.stderr or proc.stdout or "").strip().splitlines()[-3:])[:500]
        raise IngestError(f"markitdown не смог обработать {src.name}: {detail}")
    return out_path


def ensure_markdown(src: Path, cache_dir: Path, timeout: int = 300) -> Tuple[Path, bool]:
    """Возвращает Markdown-версию файла, кэшируя результат по mtime.

    Возвращает ``(путь, конвертировано_сейчас)``.
    """
    src = Path(src)
    if src.suffix.lower() in TEXT_EXTENSIONS:
        return src, False
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{src.name}.md"
    if target.is_file() and target.stat().st_mtime >= src.stat().st_mtime:
        return target, False
    return convert_file(src, target, timeout=timeout), True


def convert_many(
    paths: Iterable[Path], out_dir: Path, timeout: int = 300
) -> List[Tuple[Path, Optional[Path], Optional[str]]]:
    """Конвертирует набор файлов.

    Возвращает список ``(источник, markdown, ошибка)``; ошибка не прерывает
    обработку остальных файлов.
    """
    out_dir = Path(out_dir)
    results: List[Tuple[Path, Optional[Path], Optional[str]]] = []
    for raw in paths:
        src = Path(raw).expanduser()
        try:
            md_path = convert_file(src, out_dir / f"{src.name}.md", timeout=timeout)
            results.append((src, md_path, None))
        except IngestError as exc:
            results.append((src, None, str(exc)))
    return results
